import json
from pathlib import Path

import pytest

from evals.metrics import NEGATIVE, compare, doc_class, flatten, load_json, normalise, score_doc, summarise
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


def test_wrong_and_hallucinated_values_cost_precision_and_recall():
    pred = json.loads(json.dumps(GOLD))
    pred["przelew_bankowy"]["numer_transakcji"] = "INVENTED"
    counts = compare(pred, GOLD)
    assert (counts.tp, counts.fp, counts.fn) == (5, 1, 1)
    non_null = compare(pred, GOLD, skip_gold_nulls=True)
    assert (non_null.tp, non_null.fp, non_null.fn) == (5, 0, 0)


def test_lists_are_order_insensitive():
    gold = {"pelnomocnicy": [{"imie_nazwisko": "A B", "pesel": None}, {"imie_nazwisko": "C D", "pesel": None}]}
    pred = {"pelnomocnicy": list(reversed(gold["pelnomocnicy"]))}
    assert compare(pred, gold).f1 == 1.0
    assert sum(flatten(gold).values()) == 4


def test_negative_document_must_be_empty(tmp_path: Path):
    empty = tmp_path / "neg.json"
    empty.write_text("")
    assert load_json(empty) == {}
    assert doc_class({}) == NEGATIVE
    ok = score_doc("negatywne", "x.pdf", empty, {})
    assert (ok.counts.tp, ok.counts.fp, ok.counts.fn) == (0, 0, 0)
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps(GOLD))
    bad = score_doc("negatywne", "x.pdf", wrong, {})
    assert bad.counts.fp == 6 and bad.pred_class == "przelew"


def test_missing_output_counts_as_all_missed(tmp_path: Path):
    result = score_doc("c", "x.pdf", tmp_path / "missing.json", GOLD)
    assert result.errors and result.counts.fn == 6
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
            out.write_text(json.dumps(gold) if gold else "", encoding="utf-8")
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
    assert scores["micro_f1"] == pytest.approx(8 / 12)
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
