"""Class definitions drive routing and extraction, including opt-in forms."""

import json
import sys
from pathlib import Path

import pytest

from kio2json import __main__ as cli
from kio2json import pipeline
from kio2json.class_config import load_classes, route
from kio2json.classify import classify

REGISTRY = Path(__file__).resolve().parents[1] / "config" / "classes"
FORM = "KARTA UCZESTNIKA\nUczestnik: Copper Heron\nData: 19.07.2031\nSygnatura: H-77"


def test_fourth_class_cli_and_jury_default(tmp_path, monkeypatch):
    # An invented one-page text PDF, also exercised through pdfplumber.
    stream = "BT /F1 12 Tf 40 750 Td 16 TL " + " T* ".join(f"({line}) Tj" for line in FORM.splitlines()) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = ["0000000000 65535 f "]
    for number, content in enumerate(objects, 1):
        offsets.append(f"{len(pdf):010d} 00000 n ")
        pdf += f"{number} 0 obj\n{content}\nendobj\n".encode("ascii")
    xref = f"xref\n0 {len(offsets)}\n" + "\n".join(offsets)
    trailer = f"\ntrailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{len(pdf)}\n%%EOF\n"
    (tmp_path / "opaque.pdf").write_bytes(pdf + (xref + trailer).encode("ascii"))
    target = tmp_path / "out" / "opaque.json"
    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    monkeypatch.setattr(sys, "argv", ["app", "--input", str(tmp_path), "--output", str(target.parent)])
    assert cli.main() == 0
    assert target.read_bytes() == b""

    config = tmp_path / "classes"
    config.mkdir()
    original = (REGISTRY / "participation.toml").read_text()
    (config / "participation.toml").write_text(original.replace("enabled = false", "enabled = true"))
    monkeypatch.setenv("KIO_CLASSES_DIR", str(config))
    assert cli.main() == 0
    assert json.loads(target.read_text()) == {"participant": "Copper Heron", "filed": "2031-07-19", "reference": "H-77"}


@pytest.mark.parametrize(
    "change",
    [
        ("labelled_fields", "unknown"),
        ("iso_date", "no_such_normalizer"),
        ('type = "string"', 'type = "unknown"'),
        ("^Karta", "([Karta"),
    ],
)
def test_bad_config_reports_file_even_for_empty_batch(tmp_path, monkeypatch, capsys, change):
    original = (REGISTRY / "participation.toml").read_text()
    changed = original.replace(*change)
    assert changed != original
    (tmp_path / "bad.toml").write_text(changed)
    monkeypatch.setenv("KIO_CLASSES_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["app", "--input", str(tmp_path)])
    assert cli.main() == 1
    assert "bad.toml" in capsys.readouterr().err


ACCOUNTS = "Nadawca: " + "9" * 26 + "\nOdbiorca: " + "4" * 26
CONFIRMATION = "Potwierdzenie przelewu"
TRANSFER = f"{CONFIRMATION}\n{ACCOUNTS}\nKwota: 48,00"


@pytest.mark.parametrize(
    ("pages", "expected"),
    [
        ([TRANSFER + "\nStatus: odrzucony"], None),
        (["Prosimy o zapłatę należności\n" + TRANSFER], None),
        (["WYROK W SPRAWIE\nPrzytoczono pismo:", "ODWOŁANIE\nOdwołujący"], None),
        ([f"{CONFIRMATION}\n{ACCOUNTS}\nOpłata: 17,00"], None),
        ([TRANSFER + "\nStatus: wykonany\nStatus: anulowany"], None),
        (["Faktura VAT\n" + TRANSFER], None),
        ([TRANSFER.replace("4" * 26, "99 " + " ".join(["9999"] * 6))], None),
        ([TRANSFER], "bank_transfer"),
        ([f"Status: wykonano\nPrzelew\n{ACCOUNTS}\nData operacji: 19.07.2031"], "bank_transfer"),
        (["Okładka", "O D W O Ł A N I E\nOdwołujący"], "appeal"),
        (["Okładka", "P E Ł N O M O C N I C T W O"], "power_of_attorney"),
        (["PEŁNOMOCNICTWO WZÓR"], None),
        (["PEŁNOMOCNICTWO", "ODWOŁANIE\nOdwołujący"], "power_of_attorney"),
    ],
)
def test_pipeline_class_matches_base_classifier(monkeypatch, pages, expected):
    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    monkeypatch.setattr(pipeline, "read_pages", lambda path, **kwargs: pages)
    label, record = pipeline.process_pdf(Path("opaque.pdf"))
    assert classify(pages) == expected
    assert label == expected
    if expected is None:
        assert record == {}


def test_distinct_routing_evidence_uses_participating_captures(tmp_path):
    example = (REGISTRY / "participation.toml").read_text()
    path = tmp_path / "participation.toml"
    path.write_text(
        example.replace("enabled = false", "enabled = true")
        + r"""
[routing.evidence]
pattern = 'Code: (\w+)|Tag: (\w+)|Blank(?: (x))?'
minimum = 2
"""
    )
    definitions = load_classes(tmp_path)
    assert route([FORM + "\nTag: Indigo\nCode: INDIGO\nBlank"], definitions) is None
    assert route([FORM + "\nCode: Amber\nTag: Indigo"], definitions).id == "participation"


@pytest.mark.parametrize(
    "routing",
    [
        'classifier = "kio2json.classify.missing"',
        'classifier = "kio2json.classify.classify"\nrequired = ["keyword"]',
    ],
)
def test_invalid_classifier_routing_reports_file(tmp_path, routing):
    original = (REGISTRY / "participation.toml").read_text()
    before, rest = original.split("[routing]", 1)
    path = tmp_path / "form.toml"
    path.write_text(before + "[routing]\n" + routing + "\n[fields." + rest.split("[fields.", 1)[1])
    with pytest.raises(ValueError, match=r"(?s)form\.toml.*routing"):
        load_classes(tmp_path)
