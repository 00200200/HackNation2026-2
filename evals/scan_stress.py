"""Scan stress eval (issue #81): score the app on fresh renders of the organizer's 30 scans.

The organizer's scans score 1.000 and the app was tuned on those exact files. This re-renders every page from a
fixed seed with another resolution, encoding, skew and noise, runs the app on the result as a black box (the jury's
contract, through `evals.run`) and reports, per variant, the UZP micro F1, the routing per class, how much of the loss is
routing and how much is fields, and the fields that fail. A re-render also loses detail to resampling and JPEG, which
the delivered file does not, so the drop measures how the app copes with another copy of a page, not how much of it is
tuning.

    uv run python -m evals.scan_stress                          # every variant
    uv run python -m evals.scan_stress --variants delivered,skew+3,mixed-1 --out /tmp/scan-stress-part.json
    uv run python -m evals.scan_stress --list                   # the variants and what each changes
    uv run python -m evals.scan_stress --build-only             # only write the PDFs, to look at them

The variants are built into `.cache/scan-stress` (ignored by git) and rebuilt only when the generator, the seed or a
source file changes. Nothing but the report is committed. A variant skews the page on top of the scan's own skew
(median 1.53 degrees and maximum 2.59 over the organizer's pages, issue #81), so `skew+3` is up to 5.6 degrees in all.
The app runs as the jury's default run does (no model endpoint, even when a `.env` holds one; default OCR engine and
classes) and sees neutral case folders.
A diagnostic, not a gate: compare two reports to see whether a change helps. A partial run (`--variants`) writes the
same report path as a full one, so give it another `--out` to keep the full report.
"""

import argparse
import hashlib
import io
import json
import os
import random
import sys
import tempfile
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
from PIL import Image

from evals.metrics import NEGATIVE, Counts, DocResult, score_doc, summarise
from evals.run import DATA, DEFAULT_CMD, ROOT, git_state, load_organizer_scans, run_app, stage

CACHE = ROOT / ".cache" / "scan-stress"
RESULTS = ROOT / "evals" / "results" / "scan-stress.json"
VERSION = 2  # bump when the rendering changes, so that cached variants are rebuilt
PDF_DATE = time.gmtime(0)  # Pillow stamps the current time into a PDF; a fixed date keeps the same seed byte-identical
JPEG_QUALITY = 80
NOISE_SIGMA = 6.0  # grey levels of Gaussian noise: visible in the grain, not in the text
SKEW_LIMIT = 2.6  # the organizer's pages: median 1.53 degrees, maximum 2.59
MIXED_DPI = (150, 200, 300)  # the resolutions of the organizer's pages
NO_OUTPUT = "no output"  # a document whose JSON the app did not write, unlike `{}`, which is a decision


@dataclass(frozen=True)
class Spec:
    """How a variant re-renders a page. `dpi=None` is the file as delivered."""

    dpi: int | None = None
    encoding: str = "jpeg"  # grey JPEG, or "ccitt" for a one-bit page like the scanner's black and white mode
    skew: float = 0.0  # degrees added to every page
    noise: float = 0.0  # standard deviation of Gaussian noise, in grey levels
    mixed: bool = False  # dpi, encoding and noise are drawn per document and the skew per page, within the limits above

    def describe(self) -> str:
        if self.dpi is None and not self.mixed:
            return "the file as delivered"
        if self.mixed:
            return f"per document dpi {MIXED_DPI}, grey JPEG or one-bit, noise or none; per page skew within ±{SKEW_LIMIT}°"
        kind = "one-bit" if self.encoding == "ccitt" else "grey JPEG"
        extra = f", skew {self.skew:+g}°" * bool(self.skew) + f", noise {self.noise:g}" * bool(self.noise)
        return f"{self.dpi} dpi {kind}{extra}"


def variants() -> dict[str, Spec]:
    """One factor at a time around `rerender`, then three mixed sets that stand in for scans from another scanner."""
    reference = Spec(dpi=200)
    found = {"delivered": Spec(), "rerender": reference}
    for dpi in (150, 300):
        found[f"dpi-{dpi}"] = replace(reference, dpi=dpi)
    for dpi in (200, 300):
        found[f"bw-{dpi}"] = Spec(dpi=dpi, encoding="ccitt")
    for skew in (-3, -2, -1, 1, 2, 3):
        found[f"skew{skew:+d}"] = replace(reference, skew=float(skew))
    found["noise"] = replace(reference, noise=NOISE_SIGMA)
    for number in (1, 2, 3):
        found[f"mixed-{number}"] = Spec(mixed=True)
    return found


@dataclass(frozen=True)
class Source:
    case: str  # skany/<group>/<id>, as `evals.run --organizer-scans` names it
    name: str
    path: Path
    gold: dict


def load_sources(data: Path) -> list[Source]:
    return [
        Source(case, name, data / case / name, gold)
        for case, docs in sorted(load_organizer_scans(data).items())
        for name, gold in docs.items()
    ]


def seeded(key: str) -> int:
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")


def distort(image: Image.Image, skew: float, spec: Spec, rng: np.random.Generator) -> Image.Image:
    if skew:
        image = image.rotate(skew, resample=Image.Resampling.BICUBIC, fillcolor=255)
    if spec.noise:
        grain = np.asarray(image, dtype=np.float32) + rng.normal(0.0, spec.noise, image.size[::-1])
        image = Image.fromarray(grain.clip(0, 255).astype(np.uint8))
    if spec.encoding == "ccitt":
        _, black_and_white = cv2.threshold(np.asarray(image), 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        image = Image.fromarray(black_and_white).convert("1", dither=Image.Dither.NONE)
    return image


def render_pdf(source: Path, spec: Spec, key: str) -> bytes:
    """The scan as an image-only PDF again: every page rendered at the variant's resolution, then distorted."""
    if spec.dpi is None and not spec.mixed:
        return source.read_bytes()
    rng = random.Random(f"{key}/document")
    if spec.mixed:
        spec = Spec(
            dpi=rng.choice(MIXED_DPI),
            encoding=rng.choice(("jpeg", "ccitt")),
            noise=rng.choice((0.0, NOISE_SIGMA)),
            mixed=True,
        )
    pages = []
    with pdfium.PdfDocument(source) as pdf:
        for number, page in enumerate(pdf):
            skew = random.Random(f"{key}/{number}").uniform(-SKEW_LIMIT, SKEW_LIMIT) if spec.mixed else spec.skew
            image = page.render(scale=spec.dpi / 72, grayscale=True).to_pil().convert("L")
            pages.append(distort(image, skew, spec, np.random.default_rng(seeded(f"{key}/{number}/noise"))))
    out = io.BytesIO()
    quality = {"quality": JPEG_QUALITY} if spec.encoding == "jpeg" else {}  # Pillow rejects a quality for CCITT
    pages[0].save(
        out,
        "PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=spec.dpi,
        creationDate=PDF_DATE,
        modDate=PDF_DATE,
        **quality,
    )
    return out.getvalue()


def write_variant(job: tuple[Path, Spec, str, Path]) -> None:
    source, spec, key, target = job
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".partial")
    partial.write_bytes(render_pdf(source, spec, key))
    partial.replace(target)  # an interrupted build never leaves a half-written PDF in the cache


def build(sources: list[Source], name: str, spec: Spec, seed: int, cache: Path, workers: int) -> Path:
    """Write one variant of every source into the cache and return its folder. Cached files are reused."""
    fingerprint = hashlib.sha256()
    for source in sources:
        fingerprint.update(hashlib.sha256(source.path.read_bytes()).digest())
    settings = f"{VERSION}|{JPEG_QUALITY}|{NOISE_SIGMA}|{SKEW_LIMIT}|{MIXED_DPI}|{seed}|{name}|{spec}"
    digest = hashlib.sha256(f"{settings}|{fingerprint.hexdigest()}".encode()).hexdigest()[:12]
    root = cache / f"{name}-{digest}"
    jobs = [
        (s.path, spec, f"{seed}/{name}/{s.case}", root / s.case / s.name)
        for s in sources
        if not (root / s.case / s.name).exists()
    ]
    if workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            list(pool.map(write_variant, jobs))
    else:
        for job in jobs:
            write_variant(job)
    return root


def routed_as(d: DocResult) -> str:
    """The class the app gave a document, `negatywny` for `{}`, or `no output` when its JSON is missing or invalid."""
    return NO_OUTPUT if d.errors else d.pred_class or NEGATIVE


def loss_split(docs: list[DocResult]) -> dict:
    """1 - micro F1 is (FP + FN) / (2 TP + FP + FN): split the numerator into misrouted documents and the rest."""
    total = Counts()
    for d in docs:
        total.add(d.counts)
    denominator = 2 * total.tp + total.fp + total.fn
    routing = sum(d.counts.fp + d.counts.fn for d in docs if routed_as(d) != d.gold_class)
    fields = sum(d.counts.fp + d.counts.fn for d in docs if routed_as(d) == d.gold_class)
    share = (lambda errors: None) if denominator == 0 else (lambda errors: errors / denominator)
    return {"routing": share(routing), "fields": share(fields), "routing_errors": routing, "field_errors": fields}


def failing_fields(docs: list[DocResult], top: int = 8) -> list[dict]:
    """Fields of correctly routed documents with the most errors."""
    pooled: defaultdict[str, Counts] = defaultdict(Counts)
    for d in docs:
        if routed_as(d) == d.gold_class:
            for path, counts in d.by_field.items():
                pooled[path].add(counts)
    worst = sorted(pooled.items(), key=lambda item: item[1].fp + item[1].fn, reverse=True)[:top]
    return [{"path": p, "tp": c.tp, "fp": c.fp, "fn": c.fn} for p, c in worst if c.fp + c.fn]


def variant_report(docs: list[DocResult]) -> dict:
    summary = summarise(docs)
    routing: defaultdict[str, Counter] = defaultdict(Counter)
    for d in docs:
        routing[d.gold_class][routed_as(d)] += 1
    return {
        "docs": len(docs),
        "no_output": sum(1 for d in docs if d.errors),
        "micro_f1": summary["micro_f1"],
        "micro_f1_strict": summary["micro_f1_strict"],
        "per_class_f1": summary["per_class_f1"],
        "loss": loss_split(docs),
        "routing": {gold: dict(row) for gold, row in routing.items()},
        "misrouted": [
            {"doc": d.case, "class": d.gold_class, "routed_as": routed_as(d)}
            for d in docs
            if routed_as(d) != d.gold_class
        ],
        "failing_fields": failing_fields(docs),
    }


@dataclass
class Run:
    docs: list[DocResult]
    seconds: float
    error: str | None


# The environment wins over the app's `.env`, so empty values keep a keyed `.env` from giving it a model (as in evals/variants.py).
KEYLESS = {"KIO_LLM_BASE_URL": "", "KIO_LLM_MODEL": "", "KIO_LLM_API_KEY": ""}
# `uv run` loads a variable that is not set from the file `UV_ENV_FILE` names, so that is dropped too.
NOT_SET_BY_THE_JURY = {"KIO_OCR_ENGINE", "KIO_CLASSES_DIR", "KIO_CASE_REPAIR", "UV_ENV_FILE"}


def app_env() -> dict[str, str]:
    """The environment of the jury's default run, whatever the caller's shell or `.env` holds."""
    kept = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("KIO_LLM_") and key.upper() not in NOT_SET_BY_THE_JURY
    }
    return kept | KEYLESS


def score(sources: list[Source], name: str, root: Path, cmd: str) -> Run:
    """Run the app on one variant and score it. A document the app left without JSON scores as all misses.

    The app sees `<variant>/przyklad_NN/dokument_01.pdf`: no class, group or organizer scan id in a folder or file name.
    NN is the position in the sorted sources, so it still follows the class order; nothing in the app reads it.
    """
    with tempfile.TemporaryDirectory(prefix="odw-scan-stress-") as tmp:
        data, input_dir, output_dir = Path(tmp) / "data", Path(tmp) / "input", Path(tmp) / "output"
        cases = {}
        for number, source in enumerate(sources, 1):
            case = f"{name}/przyklad_{number:02d}"
            (data / case).mkdir(parents=True)
            target = (root / source.case / source.name).resolve()  # the link is read from another folder
            (data / case / source.name).symlink_to(target)
            cases[case] = {source.name: source.gold}
        input_dir.mkdir()
        output_dir.mkdir()
        staged = stage(cases, data, input_dir)
        seconds, error = run_app(cmd, input_dir, output_dir, env=app_env())
        docs = [
            score_doc(
                f"{name}/{source.case}",
                source.name,
                output_dir / case / f"{staged[(case, source.name)]}.json",
                source.gold,
            )
            for case, source in zip(cases, sources, strict=True)
        ]
    return Run(docs, seconds, error)


def num(value: float | None) -> str:
    return "  n/a" if value is None else f"{value:5.3f}"


def show(results: dict) -> None:
    print(
        f"scan stress: {results['documents']} documents x {len(results['variants'])} variants, commit {results['commit'][:9]}"
    )
    header = f"  {'variant':10} {'F1':>5} {'strict':>6} {'routing loss':>12} {'field loss':>10}  misrouted   appeal power  transfer"
    print(header)
    rows = {**results["variants"], **{f"[{k}]": v for k, v in results["groups"].items()}}
    for name, row in rows.items():
        per_class = row["per_class_f1"]
        print(
            f"  {name:10} {num(row['micro_f1'])} {num(row['micro_f1_strict']):>6} {num(row['loss']['routing']):>12} "
            f"{num(row['loss']['fields']):>10}  {len(row['misrouted']):>9}   "
            f"{num(per_class.get('odwolanie'))} {num(per_class.get('pelnomocnictwo'))} {num(per_class.get('przelew'))}"
        )
    for name, row in results["variants"].items():
        if row["app_error"] or row["no_output"]:
            print(f"  {name}: {row['no_output']} documents without output; the app said: {row['app_error']}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--variants", help="comma-separated names (default: all, see --list); pass --out too")
    p.add_argument("--list", action="store_true", help="print the variants and exit")
    p.add_argument("--build-only", action="store_true", help="write the PDFs into the cache and exit")
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--data", type=Path, default=DATA, help="organizer data folder holding skany/")
    p.add_argument("--cache", type=Path, default=CACHE)
    p.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1), help="processes that render the PDFs")
    p.add_argument("--cmd", default=os.environ.get("ODW_CMD", DEFAULT_CMD), help="the app, with {input} and {output}")
    p.add_argument("--out", type=Path, default=RESULTS)
    return p


def main(argv: list[str] | None = None) -> int:
    p = parser()
    args = p.parse_args(argv)
    every = variants()
    if args.list:
        for name, spec in every.items():
            print(f"{name:10} {spec.describe()}")
        return 0
    names = list(dict.fromkeys(n.strip() for n in args.variants.split(","))) if args.variants else list(every)
    if unknown := [n for n in names if n not in every]:
        p.error(f"unknown variant {', '.join(unknown)}; see --list")
    sources = load_sources(args.data)
    roots = {name: build(sources, name, every[name], args.seed, args.cache, args.workers) for name in names}
    if args.build_only:
        for name, root in roots.items():
            print(f"{name:10} {root}")
        return 0
    runs = {}
    for name in names:
        runs[name] = score(sources, name, roots[name], args.cmd)
        print(f"  {name:10} {num(summarise(runs[name].docs)['micro_f1'])}  {runs[name].seconds:.0f} s", flush=True)
    if all(d.errors for run in runs.values() for d in run.docs):
        why = next((run.error for run in runs.values() if run.error), "it exited 0")
        print(f"the app wrote no output: {why}", file=sys.stderr)
        return 2
    commit, dirty = git_state()
    results = {
        "commit": commit,
        "dirty": dirty,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed": args.seed,
        "documents": len(sources),
        "seconds_per_doc": sum(run.seconds for run in runs.values()) / sum(len(run.docs) for run in runs.values()),
        "cmd": args.cmd,
        "environment": (
            "no model endpoint (KIO_LLM_BASE_URL, KIO_LLM_MODEL and KIO_LLM_API_KEY empty, even if a .env holds them); "
            "KIO_OCR_ENGINE, KIO_CLASSES_DIR, KIO_CASE_REPAIR and UV_ENV_FILE not set; neutral case folders"
        ),
        "metric": "micro_f1 is the organizer formula of evals/metrics.py (UZP #59); loss.routing + loss.fields = 1 - micro_f1",
        "variants": {
            name: {
                "spec": asdict(every[name]),
                "seconds": round(runs[name].seconds, 1),
                "app_error": runs[name].error and runs[name].error[-600:],
                **variant_report(runs[name].docs),
            }
            for name in names
        },
        "groups": {},
    }
    mixed = [name for name in names if every[name].mixed]
    if mixed:
        results["groups"]["mixed"] = variant_report([d for name in mixed for d in runs[name].docs])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    show(results)
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
