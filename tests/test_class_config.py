"""Class definitions drive routing and extraction, including opt-in forms."""

import json
import sys
from pathlib import Path

import pytest

from kio2json import __main__ as cli

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


def test_config_routing_scopes_and_distinct_evidence():
    from kio2json.class_config import load_classes, route

    definitions = load_classes(REGISTRY)

    def label(*pages):
        config = route(pages, definitions)
        return config.id if config else None

    assert label("A cover", "O D W O Ł A N I E\nOdwołujący") == "appeal"
    assert label("WYROK", "ODWOŁANIE\nOdwołujący") is None
    assert label("A cover", "PEŁNOMOCNICTWO") is None
    assert label("P E Ł N O M O C N I C T W O") == "power_of_attorney"
    account = "9" * 26
    title = "Potwierdzenie przelewu\n"
    assert label(title + account + "\n" + " ".join([account[:2]] + [account[2:6]] * 6)) is None
    assert label(title + account + "\n" + "4" * 26) == "bank_transfer"
    assert label("Faktura VAT\n" + title + account + "\n" + "4" * 26) is None
