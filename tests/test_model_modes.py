"""Organizer profiles run through the same document path as CLI and GUI batches."""

from pathlib import Path

import pytest

from kio2json import llm, pipeline
from kio2json.class_config import DEFAULT_DIR, load_classes, route


@pytest.fixture
def keyed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for key in ("BASE_URL", "MODEL", "API_KEY", "MODE", "ROUTING"):
        monkeypatch.delenv(f"KIO_LLM_{key}", raising=False)
    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    (tmp_path / ".env").write_text(
        "KIO_LLM_BASE_URL=http://127.0.0.1:8090/v1\nKIO_LLM_MODEL=offline\nKIO_LLM_API_KEY=fake\n"
        "KIO_LLM_MODE=L\nKIO_LLM_ROUTING=rules\n"
    )


@pytest.mark.parametrize(
    ("mode", "amount", "reference", "title"),
    [
        ("R", 12.0, None, "Wpis do KIO"),
        ("L", 99.0, "ABC", None),
        ("RL", 12.0, "ABC", "Wpis do KIO"),
        ("LR", 99.0, "ABC", "Wpis do KIO"),
    ],
)
def test_profile_extraction_order(keyed, monkeypatch, mode, amount, reference, title):
    if mode != "L":
        monkeypatch.setenv("KIO_LLM_MODE", mode)
    pages = ["Potwierdzenie przelewu\n" + "3" * 26 + "\n" + "4" * 26 + "\nKwota: 12,00\nTytuł: Wpis do KIO"]
    monkeypatch.setattr(pipeline, "read_pages", lambda *args, **kwargs: pages)

    def extract_model(definition, text, model=None):
        values = dict.fromkeys(definition.fields["przelew_bankowy"].fields)
        values.update(kwota=99, numer_transakcji="ABC")
        return {"przelew_bankowy": values}

    monkeypatch.setattr(llm, "extract_llm", extract_model)
    label, data = pipeline.process_pdf(Path("opaque.pdf"))
    assert label == "bank_transfer"
    transfer = data["przelew_bankowy"]
    assert (transfer["kwota"], transfer["numer_transakcji"], transfer["tytul"]) == (amount, reference, title)


@pytest.mark.parametrize(
    ("policy", "first", "expected", "calls"),
    [
        ("rules", "no heading", None, []),
        ("fallback", "no heading", "bank_transfer", ["no heading"]),
        ("fallback", "PEŁNOMOCNICTWO", "power_of_attorney", []),
        ("model", "PEŁNOMOCNICTWO", "bank_transfer", ["PEŁNOMOCNICTWO"]),
    ],
)
def test_routing_policy_uses_only_first_page(keyed, monkeypatch, policy, first, expected, calls):
    monkeypatch.setenv("KIO_LLM_ROUTING", policy)
    seen = []

    def classify(first_page):
        seen.append(first_page)
        return "bank_transfer"

    monkeypatch.setattr(llm, "classify_llm", classify, raising=False)
    definition = route([first, "other page"], load_classes())
    assert (definition.id if definition else None) == expected
    assert seen == calls


def test_hybrid_supplies_rows_for_absent_organizer_list(keyed, monkeypatch):
    monkeypatch.setenv("KIO_LLM_MODE", "RL")
    monkeypatch.setattr(pipeline, "read_pages", lambda *args, **kwargs: ["PEŁNOMOCNICTWO"])
    rows = [{"imie_nazwisko": "Iga Wymyślna", "pesel": None}]
    monkeypatch.setattr(llm, "extract_llm", lambda *a, **kw: {"mocodawca": [], "pelnomocnicy": rows})
    _, data = pipeline.process_pdf(Path("opaque.pdf"))
    assert data["pelnomocnicy"] == rows


def test_missing_endpoint_credential_retains_configured_rules(keyed):
    Path(".env").write_text("KIO_LLM_BASE_URL=http://127.0.0.1:8090/v1\nKIO_LLM_MODEL=offline\nKIO_LLM_MODE=L\n")
    assert all(c.engines == ["python"] for c in load_classes() if c.enabled)


def test_custom_registry_retains_explicit_engines_and_routing(keyed, monkeypatch, tmp_path):
    (tmp_path / "transfer.toml").write_bytes((DEFAULT_DIR / "bank_transfer.toml").read_bytes())
    monkeypatch.setenv("KIO_CLASSES_DIR", str(tmp_path))
    monkeypatch.setenv("KIO_LLM_ROUTING", "model")
    definitions = load_classes()
    assert definitions[0].engines == ["python"]
    assert route(["Unknown"], definitions) is None


def test_v_rejects_malformed_account_from_model(keyed, monkeypatch):
    monkeypatch.setenv("KIO_LLM_MODE", "V")
    monkeypatch.setenv("KIO_LLM_ROUTING", "fallback")
    monkeypatch.setattr(pipeline, "read_pages", lambda *a, **kw: ["unknown layout"])
    monkeypatch.setattr(llm, "classify_llm", lambda page: "bank_transfer", raising=False)

    def extract_model(definition, text, model=None):
        record = dict.fromkeys(definition.fields["przelew_bankowy"].fields)
        record.update(na_rachunek="7" * 26, numer_transakcji="ABC")
        return {"przelew_bankowy": record}

    monkeypatch.setattr(llm, "extract_llm", extract_model)
    _, data = pipeline.process_pdf(Path("opaque.pdf"))
    assert data.get("przelew_bankowy", {}).get("numer_transakcji") == "ABC"
    assert data["przelew_bankowy"]["na_rachunek"] is None


@pytest.mark.parametrize(
    ("first", "model_label", "expected", "model_calls"),
    [
        ("Krajowa Izba Odwoławcza\nPrzesyłamy kopię odwołania.", "appeal", None, 0),
        ("Wyciąg z rachunku\nSzczegóły transakcji\nKwota: 125 PLN", "bank_transfer", None, 0),
        ("Odwołujący wnosi niniejsze odwołanie wobec czynności.", "appeal", "appeal", 1),
        ("Odwołujący wnosi niniejsze odwołanie wobec czynności.", "bank_transfer", None, 1),
        ("Pełnomocnictwo do reprezentacji", "power_of_attorney", "power_of_attorney", 1),
        ("Szczegóły transakcji\nKwota: 9 PLN", "power_of_attorney", None, 1),
        ("Szczegóły transakcji\nKwota: 9 PLN\nRachunek: " + "7" * 26, "power_of_attorney", "bank_transfer", 1),
        (
            "Szczegóły transakcji\nKwota: 9 PLN\nNadawca: Firma A\nOdbiorca: Firma B",
            "power_of_attorney",
            "bank_transfer",
            1,
        ),
        ("Szczegóły transakcji\nRachunek: " + "7" * 26, "power_of_attorney", None, 1),
        ("Szczegóły transakcji\nKwota: 9 PLN", "appeal", None, 1),
        ("Szczegóły transakcji\nStatus: odrzucony\nKwota: 9 PLN", "bank_transfer", None, 0),
        ("Szczegóły transakcji", "power_of_attorney", None, 0),
        ("Szczegóły transakcji\nKwota: ........", "power_of_attorney", None, 0),
        ("Załącznik: Potwierdzenie przelewu\nKwota: 9 PLN", "bank_transfer", None, 0),
        ("Załącznik: Potwierdzenie przelewu\nRachunek: " + "7" * 26, "bank_transfer", None, 0),
        ("Pismo przewodnie\nPotwierdzenie przelewu przesyłamy w załączeniu.\nKwota: 99 PLN", "bank_transfer", None, 0),
        (
            "Pismo przewodnie\nPotwierdzenie przelewu przesyłamy w załączeniu.\nKwota: 99 PLN",
            "power_of_attorney",
            None,
            0,
        ),
        ("Szczegóły transakcji przesyłamy w załączeniu.\nKwota: 99 PLN", "power_of_attorney", None, 0),
        (
            "Szanowni Państwo,\nW załączeniu przesyłamy:\nPotwierdzenie przelewu\nKwota: 99 PLN",
            "bank_transfer",
            None,
            0,
        ),
        (
            "Załączniki:\n1. Odpis dokumentu\n\n2) Potwierdzenie przelewu\nKwota: 99 PLN\nRachunek: " + "7" * 26,
            "power_of_attorney",
            None,
            0,
        ),
        ("2. Potwierdzenie przelewu\nRachunek: " + "7" * 26 + "\nKwota: 99 PLN", "bank_transfer", None, 0),
        ("2.\nPotwierdzenie przelewu\nRachunek: " + "7" * 26 + "\nKwota: 99 PLN", "bank_transfer", None, 0),
        ("Potwierdzenie przelewu\nprzesyłamy w załączeniu.\nKwota: 99 PLN", "bank_transfer", None, 0),
        ("Informacje o rachunku | Szczegóły transakcji\nRachunek: " + "7" * 26, "bank_transfer", "bank_transfer", 1),
        (
            "Pełnomocnictwo do reprezentacji\nSzczegóły transakcji\nKwota: 9 PLN",
            "power_of_attorney",
            "power_of_attorney",
            1,
        ),
        ("PEŁNOMOCNICTWO", "unrelated", "power_of_attorney", 0),
    ],
)
def test_supported_routing_through_document_pipeline(keyed, monkeypatch, first, model_label, expected, model_calls):
    monkeypatch.setenv("KIO_LLM_ROUTING", "supported")
    monkeypatch.setenv("KIO_LLM_MODE", "R")
    monkeypatch.setattr(pipeline, "read_pages", lambda *a, **kw: [first, "Wnoszę odwołanie od czynności."])
    seen = []

    def classify(page):
        seen.append(page)
        return model_label

    monkeypatch.setattr(llm, "classify_llm", classify)
    label, _ = pipeline.process_pdf(Path("invented.pdf"))
    assert label == expected
    assert seen == [first] * model_calls


@pytest.mark.parametrize(
    ("recognized", "scanned", "expected_calls"), [(True, False, 0), (False, False, 1), (True, True, 1)]
)
def test_incomplete_gap_scope(keyed, monkeypatch, recognized, scanned, expected_calls):
    monkeypatch.setenv("KIO_LLM_MODE", "RL")
    monkeypatch.setenv("KIO_LLM_GAP_SCOPE", "incomplete")
    monkeypatch.setenv("KIO_LLM_ROUTING", "fallback")
    monkeypatch.setenv("KIO_LLM_DUAL_OCR", "false")

    def read(*args, **kwargs):
        if scanned and (pages := kwargs.get("ocr_pages")) is not None:
            pages.append(1)
        return [
            "PEŁNOMOCNICTWO\nMocodawca: Przykładowa sp. z o.o.\nUdziela pełnomocnictwa Pani Idzie Zimowej."
            if recognized
            else "Instrument appointing a representative"
        ]

    monkeypatch.setattr(pipeline, "read_pages", read)
    monkeypatch.setattr(llm, "classify_llm", lambda text: "power_of_attorney")
    calls = []

    def infer(definition, text, model=None):
        calls.append(definition.id)
        return {"pelnomocnicy": [], "mocodawca": []}

    monkeypatch.setattr(llm, "extract_llm", infer)
    label, _ = pipeline.process_pdf(Path("opaque.pdf"))
    assert label == "power_of_attorney"
    assert len(calls) == expected_calls


def test_rules_first_keeps_verified_receipt_title_before_model_gap_fill(keyed, monkeypatch):
    monkeypatch.setenv("KIO_LLM_MODE", "RL")
    monkeypatch.setenv("KIO_LLM_DUAL_OCR", "false")
    receipt = "Potwierdzenie przelewu\n" + "3" * 26 + "\n" + "4" * 26 + "\nKwota: 12,00"

    def read(*args, ocr_pages, ocr_word_boxes, **kwargs):
        ocr_pages.append(1)
        ocr_word_boxes.append(pipeline.WordBox(1, "Tytuł", 10, 10, 30, 20))
        return [receipt]

    monkeypatch.setattr(pipeline, "read_pages", read)
    monkeypatch.setattr(pipeline, "recover_account_crops", lambda path, pages, boxes: pages)
    monkeypatch.setattr(pipeline, "reread_title", lambda path, boxes, title: "Druk katalogu")

    def model(definition, text, model=None):
        values = dict.fromkeys(definition.fields["przelew_bankowy"].fields)
        values.update(tytul="Opis zastępczy", numer_transakcji="KAT-42")
        return {"przelew_bankowy": values}

    monkeypatch.setattr(llm, "extract_llm", model)
    label, record = pipeline.process_pdf(Path("opaque.pdf"))
    assert label == "bank_transfer"
    assert record["przelew_bankowy"]["tytul"] == "Druk katalogu"
    assert record["przelew_bankowy"]["numer_transakcji"] == "KAT-42"


def test_incomplete_scope_keeps_absent_reference_on_complete_scanned_payment(keyed, monkeypatch):
    monkeypatch.setenv("KIO_LLM_MODE", "RL")
    monkeypatch.setenv("KIO_LLM_GAP_SCOPE", "incomplete")
    monkeypatch.setenv("KIO_LLM_DUAL_OCR", "false")
    sender = "46137900000000000000471362"
    receipt = (
        f"Potwierdzenie przelewu\nZ rachunku: {sender}\nNa rachunek: 97298300000000000000836412\n"
        "Kwota: 12,00\nData operacji: 2030-01-06\nTytuł: Druk katalogu"
    )

    def read(*args, ocr_pages=None, **kwargs):
        if ocr_pages is not None:
            ocr_pages.append(1)
        return [receipt]

    def model(definition, text, model=None):
        values = dict.fromkeys(definition.fields["przelew_bankowy"].fields)
        return {"przelew_bankowy": dict(values, numer_transakcji=sender)}

    monkeypatch.setattr(pipeline, "read_pages", read)
    monkeypatch.setattr(llm, "extract_llm", model)
    label, result = pipeline.process_pdf(Path("opaque.pdf"))
    assert label == "bank_transfer"
    fields = result["przelew_bankowy"]
    assert fields["z_rachunku"] == sender
    assert fields["numer_transakcji"] is None


@pytest.mark.parametrize(
    ("opening", "accepted"),
    [
        ("Przelew krajowy\nStatus: wykonany", True),
        ("Potwierdzenie płatności\nBank potwierdza wykonanie przelewu.", True),
        ("Kopia potwierdzenia przelewu\nStatus: wykonany", True),
        ("Potwierdzenie przelewu\nWniosek nr Z/19\nStatus: wykonany", True),
        ("Kopia potwierdzenia przelewu\nStatus: oczekujący", False),
        ("W załączeniu przesyłamy:\nKopia potwierdzenia przelewu\nStatus: wykonany", False),
        ("1.\nKopia potwierdzenia przelewu\nStatus: wykonany", False),
        ("Wniosek nr Z/19\nPotwierdzenie przelewu\nStatus: wykonany", False),
        ("Potwierdzenie przelewu\nWniosek o wypłatę\nStatus: wykonany", False),
        ("Faktura\nPrzelew krajowy\nStatus: wykonany", False),
        ("Potwierdzenie płatności\nBank nie potwierdza wykonania przelewu.", False),
        ("Przelew krajowy\nStatus: oczekujący", False),
        ("Przelew krajowy", False),
    ],
)
def test_supported_routing_of_completed_native_receipts(keyed, monkeypatch, tmp_path, opening, accepted):
    from tests.snapshots.generate_native import write_native_pdf

    monkeypatch.setenv("KIO_LLM_ROUTING", "supported")
    monkeypatch.setenv("KIO_LLM_MODE", "R")
    monkeypatch.setattr(llm, "classify_llm", lambda text: "bank_transfer")
    path = tmp_path / "document.pdf"
    write_native_pdf(
        path,
        [
            opening + "\nNadawca: Studio Planu\nOdbiorca: Rada Projektu\nData operacji: 04.05.2026"
            "\nKwota: 163,41 PLN\nTytuł: Opłata rezerwacyjna\nNumer transakcji: TK-903"
        ],
    )
    label, data = pipeline.process_pdf(path)
    if accepted:
        assert label == "bank_transfer"
        payment = data["przelew_bankowy"]
        assert (payment["kwota"], payment["data_operacji"], payment["numer_transakcji"], payment["tytul"]) == (
            163.41,
            "2026-05-04",
            "TK-903",
            "Opłata rezerwacyjna",
        )
    else:
        assert (label, data) == (None, {})
