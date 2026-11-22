"""Generate case siblings, matched image-only renditions and a separate evidence manifest."""

import hashlib
import json
import random
import tempfile
from datetime import date, timedelta
from pathlib import Path

from evals.case_canvas import Page
from evals.case_facts import make_case
from evals.case_pleadings import APPEALS, MANDATES, render_appeal, render_mandate
from evals.case_receipts import RECEIPTS, render_receipt
from evals.case_scans import scan_pdf

SEED = 92026
NEGATIVES = ("request-for-authority", "payment-advice", "decision-extract")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def families(index):
    # Keep every receipt layout and both pleading families on only one side.
    # Native / scan siblings of a fact record always travel together.
    cycle, slot = divmod(index, len(RECEIPTS))
    if slot < 7:
        return "development", APPEALS[0], MANDATES[(slot + cycle) % 6], RECEIPTS[slot], NEGATIVES[(slot + cycle) % 2]
    return "reserved", APPEALS[1], MANDATES[6 + (slot - 7 + cycle) % 3], RECEIPTS[slot], NEGATIVES[2]


def scan_settings(seed, index, split):
    # Cycle DPI and codec separately from families across repeated case panels.
    cycle, slot = divmod(index, len(RECEIPTS))
    dpi = (150, 200, 300)[(slot + cycle) % 3]
    codecs = ("jpeg-rgb", "jpeg-gray") if split == "development" else ("ccitt", "jpeg-rgb", "ccitt", "jpeg-gray")
    codec = codecs[(slot + cycle) % len(codecs)]
    rng = random.Random(f"{seed}/render/{index}")
    return {
        "dpi": dpi,
        "codec": codec,
        "quality": rng.choice((35, 45, 55, 65, 75, 80)),
        "angle": round(rng.uniform(-2.65, 2.60), 2),
    }


def render_negative(page, case, family):
    appellant = case["appeal"]["Odwolujacy"][0]
    proc = case["appeal"]["ZamowieniePubliczne"]["numer_postepowania"]
    tx = case["receipt"]["przelew_bankowy"]
    page.section("heading")
    y = (
        page.text(
            58,
            62,
            {
                NEGATIVES[0]: "WEZWANIE DO UZUPEŁNIENIA DOKUMENTÓW",
                NEGATIVES[1]: "INFORMACJA O OPŁACIE",
                NEGATIVES[2]: "WYCIĄG Z UZASADNIENIA ORZECZENIA",
            }[family],
            size=16,
            bold=True,
        )
        + 22
    )
    page.section("addressee-and-case")
    y = page.text(58, y, appellant["nazwa"], role="addressee") + 4
    y = page.text(58, y, f"Dotyczy postępowania {proc}", role="procedure") + 18
    page.section("notice")
    if family == NEGATIVES[0]:
        body = (
            "W złożonej ofercie brakuje dokumentu potwierdzającego zakres reprezentacji. "
            "Prosimy przedłożyć pełnomocnictwo, które wskaże osobę udzielającą umocowania "
            "oraz dane osoby uprawnionej do podpisania oferty."
        )
    elif family == NEGATIVES[1]:
        body = (
            f"Prosimy wpłacić kwotę {tx['kwota']:.2f} PLN na rachunek {tx['na_rachunek']}. "
            "W tytule przelewu należy wskazać numer postępowania. "
            "Po zaksięgowaniu należności prześlemy odrębne potwierdzenie."
        )
    else:
        body = (
            "Izba po rozpoznaniu odwołania uznała zarzut dotyczący dokumentacji za zasadny. "
            "Zamawiający w odpowiedzi na odwołanie wniósł o jego oddalenie. "
            "Rozstrzygnięcie o kosztach uwzględnia wpis oraz wynagrodzenie pełnomocnika."
        )
    y = page.text(58, y, body, size=11) + 26
    day = date.fromisoformat(case["issue_date"]) + timedelta(days=3)
    page.text(58, y, f"Data sporządzenia pisma: {day:%d.%m.%Y}", role="notice-date")


def generate(root: Path, count: int, seed: int = SEED, split: str = "all"):
    """Write only to a new directory. References and metadata live outside input/."""
    indices = [i for i in range(count) if split in ("all", families(i)[0])]
    if not indices:
        raise ValueError("the requested prefix contains no cases from this split")
    if root.exists() or root.is_symlink():
        raise FileExistsError(f"dataset destination already exists: {root}")
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root.parent, prefix=".case-build-") as tmp:
        staged = Path(tmp) / "dataset"
        result = _generate(staged, indices, seed)
        staged.rename(root)
    return result


def _generate(root, indices, seed):
    records = []
    digest = hashlib.sha256()
    for index in indices:
        part, appeal, mandate, receipt, negative = families(index)
        case = make_case(seed, index, mandate)
        case_id = hashlib.sha256(f"{seed}/case/{index}".encode()).hexdigest()[:16]
        settings = scan_settings(seed, index, part)
        for folder in ("native", "scan"):
            (root / "input" / f"{case_id}-{folder}").mkdir(parents=True)
        for category, family, render in (
            ("appeal", appeal, render_appeal),
            ("mandate", mandate, render_mandate),
            ("receipt", receipt, render_receipt),
            ("negative", negative, render_negative),
        ):
            stem = hashlib.sha256(f"{case_id}/{category}".encode()).hexdigest()[:16]
            native = Path(f"{case_id}-native", f"{stem}.pdf")
            scan = Path(f"{case_id}-scan", f"{stem}.pdf")
            page = Page(root / "input" / native)
            render(page, case, family)
            evidence = page.finish()
            scan_seed = int(stem, 16)
            scan_pdf(root / "input" / native, root / "input" / scan, **settings, seed=scan_seed)
            gold_path = Path("gold", case_id, stem + ".json")
            write_json(root / gold_path, case.get(category, {}))
            digest.update(hashlib.sha256((root / gold_path).read_bytes()).digest())
            for name in (native, scan):
                digest.update(hashlib.sha256((root / "input" / name).read_bytes()).digest())
            records.append(
                {
                    "case": case_id,
                    "split": part,
                    "family": family,
                    "gold": gold_path.as_posix(),
                    "native": native.as_posix(),
                    "scan": scan.as_posix(),
                    "rendering": {**settings, "seed": scan_seed},
                    "evidence": evidence,
                }
            )
    result = {"seed": seed, "cases": len(indices), "dataset_sha256": digest.hexdigest(), "documents": records}
    write_json(root / "manifest.json", result)
    return result
