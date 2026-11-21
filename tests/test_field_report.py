from evals.field_report import compare, f1


def statuses(records):
    return sorted((r["field"], r["status"]) for r in records)


def test_identical_documents_score_one():
    gold = {"a": {"x": "1", "y": None}, "items": [{"n": "A"}, {"n": "B"}]}
    records = compare(gold, gold)
    assert all(r["status"] == "ok" for r in records)
    assert f1(records) == (1.0, 1.0, 1.0)


def test_list_order_does_not_matter():
    gold = {"items": [{"n": "A", "p": None}, {"n": "B", "p": None}]}
    predicted = {"items": [{"n": "B", "p": None}, {"n": "A", "p": None}]}
    assert all(r["status"] == "ok" for r in compare(gold, predicted))


def test_wrong_value_costs_precision_and_recall():
    records = compare({"a": "x", "b": "y"}, {"a": "x", "b": "z"})
    assert statuses(records) == [("a", "ok"), ("b", "wrong")]
    assert f1(records) == (0.5, 0.5, 0.5)


def test_missing_and_spurious_list_items():
    gold = {"items": [{"n": "A"}, {"n": "B"}]}
    assert statuses(compare(gold, {"items": [{"n": "A"}]})) == [("items.n", "missing"), ("items.n", "ok")]
    predicted = {"items": [{"n": "A"}, {"n": "B"}, {"n": "C"}]}
    assert statuses(compare(gold, predicted)).count(("items.n", "spurious")) == 1


def test_signer_under_the_wrong_principal_is_an_error():
    gold = {
        "mocodawca": [
            {"data": {"nazwa": "X"}, "podpisujacy": [{"imie_nazwisko": "Anna Nowak"}]},
            {"data": {"nazwa": "Y"}, "podpisujacy": [{"imie_nazwisko": "Jan Kowalski"}]},
        ]
    }
    swapped = {
        "mocodawca": [
            {"data": {"nazwa": "X"}, "podpisujacy": [{"imie_nazwisko": "Jan Kowalski"}]},
            {"data": {"nazwa": "Y"}, "podpisujacy": [{"imie_nazwisko": "Anna Nowak"}]},
        ]
    }
    records = compare(gold, swapped)
    assert sum(r["status"] == "ok" for r in records) == 2  # only the two principal names
    assert f1(records)[2] < 1.0


def test_null_is_a_value_and_numbers_compare_by_value():
    assert statuses(compare({"a": None, "k": 200.0}, {"a": None, "k": 200})) == [("a", "ok"), ("k", "ok")]
    assert statuses(compare({"a": None}, {"a": "x"})) == [("a", "wrong")]
    assert statuses(compare({"a": "123"}, {"a": 123})) == [("a", "wrong")]


def test_misrouted_document_loses_all_reference_fields():
    assert statuses(compare({"a": "x", "b": {"c": 1}}, {})) == [("a", "missing"), ("b.c", "missing")]


def test_list_matching_finds_the_best_assignment():
    gold = {"l": [{"n": "A", "p": None}, {"n": "B", "p": "x"}]}
    predicted = {"l": [{"n": "A", "p": "x"}, {"n": "Z", "p": None}]}
    assert sum(r["status"] == "ok" for r in compare(gold, predicted)) == 2


def test_container_type_mismatch_counts_both_sides():
    assert statuses(compare({"a": [{"x": 1}]}, {"a": {"x": 1}})) == [("a.x", "missing"), ("a.x", "spurious")]
