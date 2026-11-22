"""Invented CLI regressions from PR #25. Expected issuer fields were captured on eabbb31."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from snapshots.generate_native import write_native_pdf

SIGNATURE = """PEŁNOMOCNICTWO
Jodła S.A. udziela pełnomocnictwa radcy prawnemu Igorowi Rudemu do reprezentowania spółki.
W imieniu Jodła S.A.
....................
"""
NATIVE = {
    "joint": """Mocodawca: Zorza S.A.
PEŁNOMOCNICTWO
Mocodawca: Sopel S.A.
Wspólnie udzielają pełnomocnictwa radcy prawnemu Igorowi Rudemu do reprezentowania obu spółek.""",
    "officer": """Wrzos S.A., reprezentowana przez: Ewa Portowa - Prezes Zarządu
PEŁNOMOCNICTWO
Niniejszym udziela pełnomocnictwa Janowi Polnemu.""",
    "signature": SIGNATURE + "Ewa Letnia (ewa@example.org)",
    "comma": SIGNATURE.replace("Jodła", "Sopel") + "Ewa Letnia, ewa@example.org",
    "semicolon": """PEŁNOMOCNICTWO
Mak S.A. upoważnia adwokata Roberta Polnego do reprezentowania spółki.
W imieniu Mak S.A.
....................
Maria Wysoka; biuro@example.org""",
    "repeated": """Mocodawca: Zorza S.A., NIP: 111-222-33-44
PEŁNOMOCNICTWO
Sopel S.A. i Zorza S.A. wspólnie udzielają pełnomocnictwa adwokatowi Janowi Polnemu.""",
}


@pytest.fixture(scope="module")
def grant_outputs(tmp_path_factory):
    root = tmp_path_factory.mktemp("grants")
    source, output = root / "input", root / "output"
    source.mkdir()
    for name, text in NATIVE.items():
        write_native_pdf(source / f"{name}.pdf", [text])
    # These invented PDFs exercise the real detached CMS byte range and the image-only OCR path.
    for path in (Path(__file__).parent / "snapshots" / "grants").glob("*.pdf"):
        shutil.copyfile(path, source / path.name)
    subprocess.run(
        [sys.executable, "-m", "kio2json", "--input", source, "--output", output],
        env={key: os.environ[key] for key in ("HOME", "PATH", "SYSTEMROOT") if key in os.environ},
        cwd=Path(__file__).resolve().parents[1],
        check=True,
    )
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in output.glob("*.json")}


BASE_OUTPUTS = Path(__file__).parent / "snapshots" / "grants" / "base-outputs.json"


@pytest.mark.parametrize("case", sorted(json.loads(BASE_OUTPUTS.read_text(encoding="utf-8"))))
def test_grant_fields_match_pre_scan_base(grant_outputs, case):
    expected = json.loads(BASE_OUTPUTS.read_text(encoding="utf-8"))[case]
    # Preserve #25's separately supported improvements to these base outputs.
    if case in {"comma", "signature", "joint"}:
        expected["pelnomocnicy"][0]["imie_nazwisko"] = "Igor Rudy"
    elif case == "repeated":
        expected["pelnomocnicy"][0]["imie_nazwisko"] = "Jan Polny"
    elif case == "sole-trader-scan":
        expected["mocodawca"][0]["podpisujacy"] = [{"imie_nazwisko": "Leon Polny"}]
    assert grant_outputs[case] == expected


def test_signature_email_requires_a_separate_printed_name():
    from kio2json.power_of_attorney import extract

    for contact, expected in [
        ("Maria Wysoka; ewa@example.org", [{"imie_nazwisko": "Maria Wysoka"}]),
        ("Maria Wysoka@example.org", []),
        ("biuro@example.org", []),
        (
            "Ewa Letnia (ewa@example.org)\nMaria Wysoka (maria@example.org)",
            [{"imie_nazwisko": "Ewa Letnia"}, {"imie_nazwisko": "Maria Wysoka"}],
        ),
        (
            "Ewa Letnia (ewa@example.org)\n....................\nMaria Wysoka (maria@example.org)",
            [{"imie_nazwisko": "Ewa Letnia"}, {"imie_nazwisko": "Maria Wysoka"}],
        ),
    ]:
        record = extract(SIGNATURE + contact + "\nAdam Portowy")
        assert record["mocodawca"][0]["podpisujacy"] == expected


def test_certificate_requires_issuer_evidence(monkeypatch, tmp_path):
    from kio2json import grant_certificates
    from kio2json.power_of_attorney import extract

    for declaration, approvals, expected in [
        ("Wrzos S.A. upoważnia", ["Ewa Letnia"], []),
        ("W imieniu Wrzos S.A. upoważniam", ["Robert Polny"], []),
        ("W imieniu Wrzos S.A. upoważniam", ["Ewa Letnia"], ["Ewa Letnia"]),
        ("W imieniu Wrzos S.A. upoważniam", ["Ewa Letnia", "Adam Portowy"], []),
    ]:
        monkeypatch.setattr(grant_certificates, "signed_names", lambda _, names=approvals: names)
        text = (
            f"PEŁNOMOCNICTWO\n{declaration} adwokata Roberta Polnego do poświadczania kopii za zgodność z oryginałem."
        )
        record = extract(text)
        grant_certificates.add_certificate_signers(tmp_path / "grant.pdf", record, text)
        assert [s["imie_nazwisko"] for s in record["mocodawca"][0]["podpisujacy"]] == expected


@pytest.mark.parametrize(
    "caption",
    ["Świadek: Ewa Letnia", "Podpis świadka: Ewa Letnia", "W charakterze świadka dokument podpisała Ewa Letnia."],
)
def test_sole_certificate_of_a_named_witness(monkeypatch, tmp_path, caption):
    from kio2json import grant_certificates
    from kio2json.power_of_attorney import extract

    text = (
        "PEŁNOMOCNICTWO\nW imieniu Wrzos S.A. upoważniam adwokata Roberta Polnego do reprezentowania spółki."
        f"\n{caption}"
    )
    record = extract(text)
    monkeypatch.setattr(grant_certificates, "signed_names", lambda _: ["Ewa Letnia"])
    grant_certificates.add_certificate_signers(tmp_path / "grant.pdf", record, text)
    assert record["mocodawca"][0]["podpisujacy"] == []


def test_pre_title_representative_and_second_issuer():
    from kio2json.power_of_attorney import extract

    first = "Wrzos S.A., reprezentowana przez: Ewa Portowa - Prezes Zarządu"
    rest = "\nPEŁNOMOCNICTWO\nMocodawca: Sopel S.A.\nWspólnie udzielają pełnomocnictwa adwokatowi Igorowi Rudemu."
    for label, expected in [
        ("", [("Wrzos S.A.", ["Ewa Portowa"]), ("Sopel S.A.", [])]),
        ("Zamawiający: ", [("Sopel S.A.", [])]),
    ]:
        record = extract(label + first + rest)
        assert [
            (p["data"]["nazwa"], [s["imie_nazwisko"] for s in p["podpisujacy"]]) for p in record["mocodawca"]
        ] == expected


def test_separate_issuer_signature_slots_exclude_witness_row(tmp_path):
    import pdfplumber

    from kio2json.grant_certificates import _issuer_rules

    path = tmp_path / "grant.pdf"
    write_native_pdf(
        path,
        [
            (
                "PEŁNOMOCNICTWO\nWrzos S.A. upoważnia adwokata Roberta Polnego do reprezentowania spółki.\n"
                "....................           ....................\nŚwiadek:\n...................."
            )
        ],
    )
    with pdfplumber.open(path) as doc:
        left, right = _issuer_rules(doc.pages[0], "Wrzos S.A.")
    assert left[2] < right[0]
    assert left[1] == right[1]


@pytest.mark.parametrize("reason", ["Witness", "Signed as a witness", "Podpis świadka", "Certification of a true copy"])
def test_non_issuer_pdf_signature_reason_is_excluded(monkeypatch, reason):
    import ctypes

    from kio2json import grant_certificates

    raw = (reason + "\x00").encode("utf-16-le")

    def get_reason(obj, buffer, size):
        if buffer is not None:
            assert size == len(raw)
            ctypes.memmove(buffer, raw, size)
        return len(raw)

    monkeypatch.setattr(grant_certificates.pdfium.raw, "FPDFSignatureObj_GetReason", get_reason)
    assert grant_certificates._non_issuer_approval(None)


@pytest.mark.parametrize("gap", [" ", "\n"])
def test_authority_to_question_a_witness_preserves_grant_approval(monkeypatch, tmp_path, gap):
    from kio2json import grant_certificates
    from kio2json.power_of_attorney import extract

    text = f"PEŁNOMOCNICTWO\nW imieniu Wrzos S.A. upoważniam adwokata Roberta Polnego do udziału w przesłuchaniu{gap}świadka."
    record = extract(text)
    monkeypatch.setattr(grant_certificates, "signed_names", lambda _: ["Ewa Letnia"])
    grant_certificates.add_certificate_signers(tmp_path / "grant.pdf", record, text)
    assert record["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": "Ewa Letnia"}]


@pytest.mark.parametrize(
    ("caption", "expected"),
    [("Podpis mocodawcy:", ["Mira Jasna"]), ("Podpis świadka:", []), ("Podpis pełnomocnika:", [])],
)
def test_printed_name_then_position_belongs_to_the_caption(tmp_path, caption, expected):
    from kio2json.pipeline import process_pdf

    path = tmp_path / "document.pdf"
    write_native_pdf(
        path,
        [
            f"PEŁNOMOCNICTWO\nSrebrny Buk S.A. udziela pełnomocnictwa adw. Izie Polnej.\n{caption}\nMira Jasna\nPrezes Zarządu"
        ],
    )
    label, record = process_pdf(path)
    assert label == "power_of_attorney"
    assert record["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": name} for name in expected]
