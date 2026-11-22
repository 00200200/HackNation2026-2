import hashlib
import json
from pathlib import Path

import pdfplumber
import pytest
from pdfminer.pdftypes import resolve1
from stdnum import iban
from stdnum.pl import nip, regon

from evals.case_dataset import SEED, families, generate, scan_settings
from evals.case_facts import make_case
from evals.case_pleadings import APPEALS, MANDATES
from evals.case_receipts import RECEIPTS
from evals.cases import exact_json, score
from evals.metrics import load_reference


def test_family_split_and_linked_facts():
    by_split = {}
    seen = set()
    for index in range(26):
        split, appeal, mandate, receipt, negative = families(index)
        by_split.setdefault(split, set()).update((appeal, mandate, receipt, negative))
        case = make_case(SEED, index, mandate)
        party = case["appeal"]["Odwolujacy"][0]
        grant = case["mandate"]
        payment = case["receipt"]["przelew_bankowy"]
        assert (case["payment_purpose"] == "appeal") == payment["tytul"].startswith("Wpis")
        assert grant["mocodawca"][0]["data"]["nip"] == party["nip"]
        assert party["pelnomocnik"]["imie_nazwisko"] in {p["imie_nazwisko"] for p in grant["pelnomocnicy"]}
        assert (len(grant["mocodawca"]) == 2) == (mandate == "late-consortium")
        assert ("osoba_fizyczna" == grant["mocodawca"][0]["data"]["typ"]) == (mandate == "late-trader")
        proc = case["appeal"]["ZamowieniePubliczne"]["numer_postepowania"]
        assert proc in payment["tytul"] and proc not in seen
        seen.add(proc)
        for entity in (party, *case["appeal"]["Zamawiajacy"]):
            assert nip.is_valid(entity["nip"]) and regon.is_valid(entity["regon"])
        for key in ("na_rachunek", "z_rachunku"):
            assert iban.is_valid("PL" + payment[key].removeprefix("PL"))
        if split == "development":
            assert scan_settings(SEED, index, split)["codec"] != "ccitt"
    assert by_split["development"].isdisjoint(by_split["reserved"])
    assert set(APPEALS + MANDATES + RECEIPTS) <= set.union(*by_split.values())


def test_matched_documents_and_scoring(tmp_path, monkeypatch):
    root = tmp_path / "dataset"
    manifest = generate(root, 1)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    second = tmp_path / "again"
    assert generate(second, 1) == manifest
    assert len(manifest["documents"]) == 4
    assert len(list((root / "input").rglob("*.pdf"))) == 8
    assert not list((root / "input").rglob("*.json"))
    output = tmp_path / "output"
    for item in manifest["documents"]:
        gold = load_reference(root / item["gold"])
        assert item["evidence"]["value_boxes"]
        for view in ("native", "scan"):
            path = Path(item[view])
            data = root / "input" / path
            assert (
                hashlib.sha256(data.read_bytes()).digest()
                == hashlib.sha256((second / "input" / path).read_bytes()).digest()
            )
            with pdfplumber.open(data) as pdf:
                assert len(pdf.pages) == item["evidence"]["page_count"]
                for page in pdf.pages:
                    if view == "native":
                        assert page.chars
                    else:
                        assert not page.chars and len(page.images) == 1
                        image = page.images[0]
                        assert any(f.name == "DCTDecode" for f, _ in resolve1(image["stream"]).get_filters())
            pred = output / path.with_suffix(".json")
            pred.parent.mkdir(parents=True, exist_ok=True)
            pred.write_text(json.dumps(gold, ensure_ascii=False) + "\n", encoding="utf-8")
    report = score(root, manifest, output)
    assert report["overall"]["exact"] == 8
    assert report["overall"]["uzp_f1"] == report["overall"]["strict_f1"] == 1
    assert report["overall"]["rejected"] == 2
    assert report["overall"]["uzp_ci95"] is None
    appeal = next(item for item in manifest["documents"] if item["family"] in APPEALS)
    typed = output / Path(appeal["native"]).with_suffix(".json")
    wrong_type = load_reference(typed)
    assert wrong_type["Odwolujacy"][0]["przez-pelnomocnika"] == 1
    wrong_type["Odwolujacy"][0]["przez-pelnomocnika"] = True
    typed.write_text(json.dumps(wrong_type), encoding="utf-8")
    assert score(root, manifest, output)["overall"]["exact"] == 7
    pred.unlink()
    assert score(root, manifest, output)["missing_or_invalid"] == 1
    with pytest.raises(FileExistsError):
        generate(root, 1)


def test_reserved_scan_is_group4_at_native_page_size(tmp_path):
    from evals.case_canvas import Page
    from evals.case_scans import scan_pdf

    native, scan = tmp_path / "native.pdf", tmp_path / "scan.pdf"
    page = Page(native)
    page.section("register")
    page.text(90, 98, "Zażółć gęślą jaźń", role="caption")
    page.finish()
    scan_pdf(native, scan, dpi=200, codec="ccitt", quality=35, angle=1.6, seed=11)
    with pdfplumber.open(native) as source, pdfplumber.open(scan) as rendered:
        page = rendered.pages[0]
        assert page.width == pytest.approx(source.pages[0].width, abs=0.001)
        assert page.height == pytest.approx(source.pages[0].height, abs=0.001)
        assert page.chars == []
        (image,) = page.images
        assert image["bits"] == 1
        assert image["srcsize"][0] * 72 / page.width == pytest.approx(200, abs=1)
        assert any(f.name == "CCITTFaxDecode" and params["K"] == -1 for f, params in image["stream"].get_filters())


def test_exact_amount_accepts_equivalent_json_numbers():
    assert exact_json({"kwota": 7500}, {"kwota": 7500.0})
    assert not exact_json({"kwota": True}, {"kwota": 1.0})
