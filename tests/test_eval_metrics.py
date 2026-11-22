import json
from pathlib import Path

import pytest

from evals.metrics import (
    NEGATIVE,
    compare,
    compare_strict,
    doc_class,
    flatten,
    load_prediction,
    normalise,
    score_doc,
    summarise,
)
from evals.run import DATA, GOLD_FOR, load_cases

GOLD = {
    "przelew_bankowy": {
        "data_operacji": "2030-01-15",
        "kwota": 123.45,
        "na_rachunek": "11222233334444555566667777",
        "numer_transakcji": None,
        "tytul": "Wpis testowy",
        "z_rachunku": "99888877776666555544443333",
    }
}


def test_perfect_prediction_scores_one():
    assert compare(GOLD, GOLD).f1 == 1.0


def test_normalisation_ignores_spacing_case_and_number_format():
    pred = json.loads(json.dumps(GOLD))
    pred["przelew_bankowy"].update(
        kwota=123.450, na_rachunek="11 2222 3333 4444 5555 6666 7777", tytul=" WPIS  TESTOWY "
    )
    assert compare(pred, GOLD).f1 == 1.0
    assert normalise(10000.00) == normalise(10000) == "num:10000"
    assert normalise(99422967018, "pesel") == normalise("994 229-67018", "pesel")


def test_types_and_formats_are_not_normalised_away():
    assert normalise("3") != normalise(3)
    assert normalise("2030-01-15") != normalise("20300115")
    assert normalise("123456-2030", "numer_ted") != normalise("1234562030", "numer_ted")
    pred = json.loads(json.dumps(GOLD))
    pred["przelew_bankowy"]["data_operacji"] = "15.01.2030"
    assert compare(pred, GOLD).f1 < 1.0


def test_strict_wrong_and_hallucinated_values_cost_precision_and_recall():
    pred = json.loads(json.dumps(GOLD))
    pred["przelew_bankowy"]["numer_transakcji"] = "INVENTED"
    counts = compare_strict(pred, GOLD)
    assert (counts.tp, counts.fp, counts.fn) == (5, 1, 1)
    non_null = compare_strict(pred, GOLD, skip_gold_nulls=True)
    assert (non_null.tp, non_null.fp, non_null.fn) == (5, 0, 0)


def test_lists_are_order_insensitive():
    gold = {"pelnomocnicy": [{"imie_nazwisko": "A B", "pesel": None}, {"imie_nazwisko": "C D", "pesel": None}]}
    pred = {"pelnomocnicy": list(reversed(gold["pelnomocnicy"]))}
    assert compare(pred, gold).f1 == 1.0
    assert sum(flatten(gold).values()) == 4


def test_negative_document_must_be_empty(tmp_path: Path):
    empty = tmp_path / "neg.json"
    empty.write_text("{}")
    assert load_prediction(empty) == ({}, True)
    assert doc_class({}) == NEGATIVE
    ok = score_doc("negatywne", "x.pdf", empty, {})
    assert (ok.counts.tp, ok.counts.fp, ok.counts.fn) == (0, 0, 0)
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps(GOLD))
    bad = score_doc("negatywne", "x.pdf", wrong, {})
    assert bad.counts.fp == 5 and bad.counts_strict.fp == 6 and bad.pred_class == "przelew"


def test_missing_output_counts_as_all_missed(tmp_path: Path):
    result = score_doc("c", "x.pdf", tmp_path / "missing.json", GOLD)
    assert result.errors and result.counts.fn == 5 and result.counts_strict.fn == 6
    summary = summarise([result])
    assert summary["outputs_complete"] == 0.0 and summary["micro_f1"] == 0.0


@pytest.mark.skipif(not DATA.is_dir(), reason="organizer data not cloned (make data)")
def test_gold_outputs_score_one_on_training_data(tmp_path: Path):
    cases = load_cases(DATA, quick=True)
    docs = []
    for case, items in cases.items():
        for name, gold in items.items():
            out = tmp_path / case / f"{Path(name).stem}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(gold), encoding="utf-8")
            docs.append(score_doc(case, name, out, gold))
    summary = summarise(docs)
    assert summary["micro_f1"] == 1.0
    assert summary["negatives_empty"] == summary["classification_accuracy"] == 1.0
    assert set(GOLD_FOR) <= {name for items in cases.values() for name in items}


def test_macro_f1_units_and_document_boundaries(tmp_path):
    appeal = {"OdwolanieKIO": {"tags": [1, 1, 2]}}
    samples = [
        (appeal, appeal),
        ({"OdwolanieKIO": {"tags": [1]}}, None),
        ({"mocodawca": "left"}, {"mocodawca": "right"}),
        ({"przelew_bankowy": 5}, {"przelew_bankowy": 5}),
        ({}, {"extra": True}),
        ({}, {}),
    ]
    docs = []
    for i, (gold, pred) in enumerate(samples):
        path = tmp_path / f"{i}.json"
        if pred is not None:
            path.write_text(json.dumps(pred))
        docs.append(score_doc("invented", f"{i}.pdf", path, gold))

    scores = summarise(docs)
    assert scores["micro_f1"] == pytest.approx(8 / 11)
    assert scores["micro_f1_strict"] == pytest.approx(8 / 12)
    assert scores["macro_f1_documents"] == pytest.approx(2 / 5)
    assert scores["macro_f1_classes"] == pytest.approx((6 / 7 + 1) / 3)
    assert scores["macro_f1_fields"] == pytest.approx((6 / 7 + 1) / 4)


def test_empty_macro_averages():
    scores = summarise([])
    assert all(scores[key] is None for key in ("micro_f1", "macro_f1_documents", "macro_f1_classes", "macro_f1_fields"))


def test_class_macro_counts_predicted_only_class_and_misrouting(tmp_path):
    out = tmp_path / "doc.json"
    out.write_text(json.dumps({"mocodawca": "invented"}))
    docs = [
        score_doc("one", "right.pdf", out, {"mocodawca": "invented"}),
        score_doc("one", "wrong.pdf", out, {"OdwolanieKIO": "missed"}),
    ]
    out.write_text(json.dumps({"przelew_bankowy": "spurious"}))
    docs.append(score_doc("one", "unrelated.pdf", out, {}))
    scores = summarise(docs)
    assert scores["per_class_f1"] == {"odwolanie": 0, "pelnomocnictwo": 2 / 3, "przelew": 0}
    assert scores["macro_f1_class_count"] == 3
    assert scores["macro_f1_classes"] == pytest.approx(2 / 9)


def test_invalid_utf8_prediction_is_incomplete_and_misses_reference(tmp_path):
    output = tmp_path / "invented.json"
    output.write_bytes(bytes([255]))
    doc = score_doc("invented", "one.pdf", output, {"mocodawca": {"a": 1, "b": 2}})
    summary = summarise([doc])
    assert summary["outputs_complete"] == 0
    assert summary["counts"] == {"tp": 0, "fp": 0, "fn": 2, "tn": 0}


def test_large_integer_prediction_scores_a_mismatch(tmp_path):
    prediction = tmp_path / "number.json"
    prediction.write_text(json.dumps({"amount": 10**399 + 1}))
    result = score_doc("invented", "doc.pdf", prediction, {"amount": 10**399})
    assert (result.counts.tp, result.counts.fp, result.counts.fn) == (0, 1, 0)


@pytest.mark.parametrize(
    ("contents", "complete", "correct"),
    [
        (b"{}", True, True),
        (b"{}\n", True, True),
        (b"{}\r\n", True, True),
        (b"", False, False),
        (b" ", False, False),
        (b"{", False, False),
        (b"[]", False, False),
        (b"null", False, False),
        (b"{ }", True, False),
        (b"{}\n\n", True, False),
        (b'{"field": null}', True, False),
    ],
)
def test_negative_output_contract(tmp_path, contents, complete, correct):
    prediction = tmp_path / "negative.json"
    prediction.write_bytes(contents)
    detail = summarise([score_doc("invented", "unrelated.pdf", prediction, {})])
    assert detail["outputs_complete"] == complete
    assert detail["negatives_empty"] == correct


@pytest.mark.parametrize("key", ["na_rachunek", "z_rachunku"])
def test_account_comparison_removes_only_whitespace(key):
    assert compare({key: 12345}, {key: "12345"}).fp == 1
    assert normalise("DE89 0123\n4567", key) == normalise("DE8901234567", key)
    for altered in ("8901234567", "de8901234567", "DE89-01234567", 8901234567):
        assert normalise(altered, key) != normalise("DE8901234567", key)


def test_training_account_overlay_uses_the_exact_printed_reference(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from evals import run

    sender = "12" + "0" * 18
    recipient = "34" + "5" * 24
    page = SimpleNamespace(
        extract_text=lambda: f"Sender d e12 {sender[2:]}\n1 234,56 PLN\nRecipient PL{recipient} 1234."
    )
    monkeypatch.setattr(run.pdfplumber, "open", lambda _: nullcontext(SimpleNamespace(pages=[page])))
    fields = {"z_rachunku": sender, "na_rachunek": recipient, "tytul": "fee"}
    reference = {"przelew_bankowy": fields}
    assert run.correct_training_accounts(Path("fixture.pdf"), reference) == {
        "przelew_bankowy": {**fields, "z_rachunku": "de" + sender}
    }
    assert fields["z_rachunku"] == sender


def test_uzp_nulls_wrong_values_and_literal_null_text():
    counts = compare(
        {"both": None, "new": "new", "wrong": 12, "hit": "null", "empty": None},
        {"both": None, "miss": "old", "wrong": 3, "hit": "null"},
    )
    assert (counts.tp, counts.fp, counts.fn, counts.tn) == (1, 2, 1, 2)
    assert counts.f1 == 2 / 5
    for malformed in ([], {}, ["wrong"]):
        counts = compare({"kwota": malformed}, {"kwota": 12})
        assert (counts.fp, counts.fn) == (1, 0)
    assert compare({"x": "null"}, {"x": None}).fp == 1
    assert compare({"x": None}, {"x": "null"}).fn == 1
    assert compare({"x": "num:3"}, {"x": 3}).fp == 1
    assert compare({"x": 7.004}, {"x": 7.001}).fp == 1


@pytest.mark.parametrize(
    "root,key",
    [
        ("Odwolujacy", "nazwa"),
        ("Odwolujacy", "pelnomocnik"),
        ("Zamawiajacy", "nazwa"),
        ("ZamowieniePubliczne", "tytul"),
        ("przelew_bankowy", "tytul"),
    ],
)
def test_uzp_80_percent_inclusive_on_five_fields(root, key):
    def doc(value):
        item = {key: {"nazwa": value} if key == "pelnomocnik" else value}
        return {root: [item] if root in {"Odwolujacy", "Zamawiajacy"} else item}

    assert compare(doc("abcde"), doc("abcdx")).tp == 1
    assert compare(doc("abcde"), doc("abcxx")).fp == 1
    assert compare({"other": {"tytul": "abcde"}}, {"other": {"tytul": "abcdx"}}).fp == 1


def test_uzp_identifier_preserves_print_except_whitespace():
    assert compare({"na_rachunek": "PL 01\t23"}, {"na_rachunek": "PL0123"}).tp == 1
    for printed in ("0123", "pl0123", "PL01-23"):
        assert compare({"na_rachunek": printed}, {"na_rachunek": "PL0123"}).fp == 1
    assert compare({"pesel": 123}, {"pesel": "1 23"}).tp == 1
    assert compare({"pesel": 123.0}, {"pesel": 123}).fp == 1


def test_uzp_list_matching_handles_fuzzy_collisions_and_duplicate_values():
    def parties(names):
        return {"Zamawiajacy": [{"nazwa": n} for n in names]}

    # First candidate matches either reference. Second candidate matches only the first.
    gold = parties(["abcde", "abcdx"])
    for names in (["abcde", "abzde", "abzde"], ["abzde", "abzde", "abcde"]):
        counts = compare(parties(names), gold)
        assert (counts.tp, counts.fp, counts.fn) == (2, 1, 0)


def test_uzp_list_matching_keeps_fields_with_their_record():
    gold = {"party": [{"id": "A", "signer": "S"}, {"id": "B", "signer": "T"}]}
    pred = {"party": [{"id": "B", "signer": "S"}, {"id": "A", "signer": "T"}]}
    counts = compare(pred, gold)
    assert (counts.tp, counts.fp, counts.fn) == (2, 2, 0)


def test_quick_target_uses_uzp_and_reports_strict(tmp_path):
    from evals.run import F1_TARGET, build_results

    gold = {"przelew_bankowy": {"tytul": "abcde"}}
    path = tmp_path / "pay.json"
    path.write_text(json.dumps({"przelew_bankowy": {"tytul": "abcdf"}}))
    negative = tmp_path / "empty.json"
    negative.write_text("{}")
    docs = [score_doc("x", "pay.pdf", path, gold), score_doc("x", "empty.pdf", negative, {})]
    result = build_results(docs, "quick", 0.01, {"x": {}})
    assert result["metrics"]["micro_f1"] == {"value": 1.0, "target": F1_TARGET, "pass": True}
    assert result["metrics"]["micro_f1_strict"] == {"value": 0.0, "target": None, "pass": None}
    assert result["overall_pass"]


def test_jury_batch_counts_corrected_transfers_and_empty_objects(tmp_path, monkeypatch):
    from snapshots.generate_native import write_native_pdf

    from evals.jury_batch import exact_output

    monkeypatch.chdir(tmp_path)
    case = Path("data/uzp/dane/case")
    case.mkdir(parents=True)
    account = "12" + "0" * 24
    write_native_pdf(case / "potwierdzenie_przelewu.pdf", [f"Account: PL{account}"])
    reference = {"przelew_bankowy": {"z_rachunku": account}}
    (case / "przelew.json").write_text(json.dumps(reference), encoding="utf-8-sig")
    prediction = tmp_path / "prediction.json"
    transfer = Path("training/case/potwierdzenie_przelewu.json")
    prediction.write_text(json.dumps(reference))
    assert not exact_output(transfer, prediction)
    scan = Path("scan1/case/potwierdzenie_przelewu.json")
    assert exact_output(scan, prediction)
    reference["przelew_bankowy"]["z_rachunku"] = "PL" + account
    prediction.write_text(json.dumps(reference))
    assert exact_output(transfer, prediction)
    assert not exact_output(scan, prediction)
    negative = Path("training/case/unrelated.json")
    prediction.write_bytes(b"")
    assert not exact_output(negative, prediction)
    prediction.write_bytes(b"{}\n")
    assert exact_output(negative, prediction)
