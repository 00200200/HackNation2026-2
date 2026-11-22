import io
import json
import random
import re
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

import pdfplumber
import pytest
from stdnum import iban as stdnum_iban

from evals.document_variants import appeal, attorney, facts, gold, negatives, scan, transfer
from evals.document_variants.corpus import SOURCES, build_cases, build_negatives, rng_for
from evals.document_variants.report import build_report, confusion, field_diffs, slices
from evals.document_variants.run import main, parse_cases
from evals.document_variants.vocab import AMOUNT_STYLES, Pick, fmt_account, fmt_amount, fmt_date
from evals.metrics import Counts, DocResult, score_doc

SEEDS = range(12)


def text_of(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return "\n".join(page.extract_text() or "" for page in doc.pages)


def squeeze(value: str) -> str:
    return "".join(value.split()).lower()


def leaves(data, key=""):
    """(key, value) of every non-null scalar in a reference."""
    if isinstance(data, dict):
        for k, v in data.items():
            yield from leaves(v, k)
    elif isinstance(data, list):
        for item in data:
            yield from leaves(item, key)
    elif data is not None:
        yield key, data


def case_for(source: str, seed: int) -> facts.Case:
    return facts.build_case(source, random.Random(seed), seed)


DATE_STYLES = ["iso", "dot", "dot_r", "dash", "slash", "long", "long_r", "long_roku"]
DATE_KEYS = {"data", "czynnosc_dzien", "data_operacji"}
ID_KEYS = {"krs", "nip", "regon", "pesel", "numer_bzp"}  # printed with or without separators, compared as digits
TEXT_KEYS = {"nazwa", "imie_nazwisko", "tytul", "numer_postepowania", "numer_transakcji", "mail", "miejscowosc"}


def prints(key: str, value, text: str) -> bool:
    """Whether the document text holds this reference value, in whichever of the printed forms the renderers use."""
    flat, digits = squeeze(text), re.sub(r"\D", "", text)
    if key in DATE_KEYS:
        return any(squeeze(fmt_date(date.fromisoformat(value), style)) in flat for style in DATE_STYLES)
    if key == "kwota":
        return any(squeeze(fmt_amount(value, style)) in flat for style in AMOUNT_STYLES)
    if key == "numer_ted":  # printed as NNNNNN-YYYY or as the Official Journal reference YYYY/S NNN-NNNNNN
        number, year = value.split("-")
        pattern = rf"(?<!\d){number}-{year}(?!\d)|(?<!\d){year}/S\s*\d{{3}}-{number}(?!\d)"
        return re.search(pattern, text) is not None
    if key in ID_KEYS:
        return re.sub(r"\D", "", str(value)) in digits
    if key in {"na_rachunek", "z_rachunku"}:  # as printed: the country code only when it is on the page
        return re.search(r"(?<![0-9A-Za-z])" + r"\s*".join(map(re.escape, value)) + r"(?![0-9])", text) is not None
    if squeeze(str(value)) in flat:
        return True
    words = str(value).lower().split()  # a name wrapped inside a table cell is interleaved with the next column
    return re.search(r".*?".join(map(re.escape, words)), text.lower(), re.DOTALL) is not None


def missing(rendered, keys: set[str]) -> list:
    """The reference leaves of the given keys that the document does not print."""
    text = text_of(rendered.pdf)
    return [(k, v) for k, v in leaves(rendered.gold) if k in keys and not prints(k, v, text)]


def test_gold_builders_reproduce_every_training_reference():
    for source in SOURCES:
        case = facts.from_training(source, random.Random(1), 0)
        training_appeal, training_poa, _ = facts.load_gold(source)
        assert json.loads(json.dumps(gold.appeal_gold(case))) == training_appeal, source
        assert json.loads(json.dumps(gold.poa_gold(case))) == training_poa, source


@pytest.mark.parametrize("module", [appeal, attorney, transfer])
def test_same_seed_gives_the_same_bytes(module, monkeypatch):
    case = case_for("przyklad_03", 5)
    first = module.render(case, random.Random(9)).pdf
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "2026")
    assert first == module.render(case, random.Random(9)).pdf


def test_negatives_and_scans_are_reproducible():
    one, two = negatives.render("ruling", random.Random(4)), negatives.render("ruling", random.Random(4))
    assert one.pdf == two.pdf
    assert scan.scan(one.pdf, random.Random(4)) == scan.scan(one.pdf, random.Random(4))


@pytest.mark.parametrize("seed", SEEDS)
def test_appeal_text_carries_the_reference_facts(seed):
    rendered = appeal.render(case_for(SOURCES[seed * 5], seed), random.Random(seed))
    keys = TEXT_KEYS | DATE_KEYS | ID_KEYS | {"numer_ted"}
    assert missing(rendered, keys) == [], rendered.tags


@pytest.mark.parametrize("seed", SEEDS)
def test_power_of_attorney_text_carries_the_reference_facts(seed):
    rendered = attorney.render(case_for(SOURCES[seed * 5], seed), random.Random(seed))
    assert missing(rendered, {"nazwa", "imie_nazwisko", "pesel", "krs", "nip"}) == [], rendered.tags


@pytest.mark.parametrize("seed", SEEDS)
def test_transfer_text_carries_the_reference_facts(seed):
    rendered = transfer.render(case_for(SOURCES[seed * 5], seed), random.Random(seed))
    keys = {"tytul", "numer_transakcji", "data_operacji", "kwota", "na_rachunek", "z_rachunku"}
    assert missing(rendered, keys) == [], rendered.tags


def test_the_fact_check_notices_a_value_the_document_does_not_print():
    rendered = transfer.render(case_for("przyklad_01", 1), random.Random(1))
    wrong = {"przelew_bankowy": {**rendered.gold["przelew_bankowy"], "tytul": "Zupełnie inny tytuł", "kwota": 1.23}}
    swapped = type(rendered)(rendered.pdf, wrong, rendered.tags)
    assert {k for k, _ in missing(swapped, {"tytul", "kwota"})} == {"tytul", "kwota"}


@pytest.mark.parametrize("country", ["PL", "DE", "CZ", "LT"])
def test_invented_iban_is_valid(country):
    account = facts.iban(random.Random(7), country)
    assert account.startswith(country)
    assert stdnum_iban.validate(account) == account


def test_appeal_fee_uses_seeded_invented_accounts():
    case = case_for("przyklad_01", 1)
    accounts = set()
    for seed in range(20):
        pick = Pick(random.Random(seed))
        _, _, _, account, _ = transfer.payment(case, pick)
        if pick.tags["title"].startswith("wpis"):
            assert stdnum_iban.validate(account) == account
            accounts.add(account)
    assert len(accounts) > 1


def test_the_account_check_wants_the_country_code_exactly_as_printed():
    printed_with_code = "Rachunek: PL02 1363 3085 1109 0631 1138 8206"
    assert prints("z_rachunku", "PL02136330851109063111388206", printed_with_code)
    assert not prints("z_rachunku", "02136330851109063111388206", printed_with_code)
    assert prints("z_rachunku", "02136330851109063111388206", "Rachunek: 02 1363 3085 1109 0631 1138 8206")
    assert not prints("z_rachunku", "PL02136330851109063111388206", "Rachunek: 02 1363 3085 1109 0631 1138 8206")
    assert not prints("z_rachunku", "PL0213633085110906311138820", printed_with_code)  # a truncated reference


def test_account_number_keeps_the_printed_country_code():
    printed, reference = fmt_account("PL02136330851109063111388206", "code_grouped")
    assert printed.startswith("PL02 1363") and reference == "PL02136330851109063111388206"
    printed, reference = fmt_account("PL02136330851109063111388206", "bare")
    assert reference == "02136330851109063111388206" and "PL" not in printed
    assert fmt_account("DE89370400440532013000", "code_space_grouped")[1] == "DE89370400440532013000"


def test_formats():
    assert fmt_amount(12345.6, "space_comma_zl") == "12 345,60 zł"
    assert fmt_amount(7500, "debit_sign") == "-7 500,00 PLN"
    assert fmt_date(facts.date(2026, 3, 2), "long_roku") == "2 marca 2026 roku"


def test_pick_counts_drift_from_the_default_and_buckets_it():
    pick = Pick(random.Random(0))
    for _ in range(20):
        pick("a", ["first", "second"])
    assert 0 < pick.deviations < 20
    assert pick.result()["variation"] in {"<25%", "25-40%", "40-55%", ">55%"}


def test_faithful_pick_takes_every_default_and_reports_no_variation():
    pick = Pick(random.Random(0), faithful=True)
    assert [pick("a", ["first", "second"]) for _ in range(5)] == ["first"] * 5
    assert pick("b", [("tag", "value"), ("other", "x")]) == "value"
    assert not pick.chance("c", 1.0) and pick.rng.choice([7, 8]) == 7 and pick.rng.sample([1, 2, 3], 2) == [1, 2]
    assert pick.result()["variation"] == "none" and pick.deviations == 0


@pytest.mark.parametrize("module", [appeal, attorney, transfer])
def test_faithful_documents_are_identical_for_any_seed(module):
    case = case_for("przyklad_03", 5)
    assert module.render(case, random.Random(1), True).pdf == module.render(case, random.Random(2), True).pdf


def test_faithful_appeal_copies_the_training_wording():
    rendered = appeal.render(case_for("przyklad_03", 5), random.Random(1), True)
    flat = " ".join(text_of(rendered.pdf).split())
    assert rendered.tags["variation"] == "none" and rendered.tags["family"] == "lap"
    assert (
        "wnoszę o: " in flat and "„Prawo zamówień publicznych” lub „Pzp”" in flat and "1.1) wnoszę o zasądzenie" in flat
    )


def test_faithful_sole_trader_power_of_attorney_copies_the_training_wording():
    rendered = attorney.render(case_for("przyklad_44", 1), random.Random(1), True)
    printed = " ".join(text_of(rendered.pdf).split())
    assert "Ja, niżej podpisany" in printed and "Działając" not in printed
    assert rendered.tags["variation"] == "none" and rendered.tags["grantor_quotes"] in {"yes", "no"}


def test_power_of_attorney_tags_grantor_names_that_hold_quotation_marks():
    case = case_for("przyklad_01", 1)
    quoted = replace(
        case, grantors=[replace(g, org=replace(g.org, name="Firma „Alfa” sp. z o.o.")) for g in case.grantors]
    )
    assert attorney.render(quoted, random.Random(1)).tags["grantor_quotes"] == "yes"
    plain = replace(
        case, grantors=[replace(g, org=replace(g.org, name="Firma Alfa sp. z o.o.")) for g in case.grantors]
    )
    assert attorney.render(plain, random.Random(1)).tags["grantor_quotes"] == "no"


def test_power_of_attorney_tags_the_counts_and_title_style_taken_from_the_facts():
    case = case_for("przyklad_42", 3)
    for titles, expected in ((("r. pr.", "adw."), "abbreviated"), (("radca prawny", "adwokat"), "spelled_out")):
        attorneys = [replace(a, title=t) for a, t in zip(case.attorneys, titles, strict=False)]
        tags = attorney.render(replace(case, attorneys=attorneys), random.Random(1)).tags
        assert tags["attorney_titles"] == expected
        assert tags["grantors"] == str(len(case.grantors)) and tags["attorneys"] == str(len(attorneys))


def test_a_two_authority_case_prints_the_leader_and_gold_marks_it():
    case = case_for("przyklad_42", 3)
    assert len(case.authorities) == 2
    rendered = appeal.render(case, random.Random(1))
    printed = " ".join(text_of(rendered.pdf).split())
    assert f"Lider, prowadzący postępowanie: {case.authorities[case.lead].name}" in printed
    flags = {row["nazwa"]: row["prowadzacy_postepowanie"] for row in rendered.gold["Zamawiajacy"]}
    assert flags == {a.name: int(i == case.lead) for i, a in enumerate(case.authorities)}


def test_each_scan_mode_writes_the_image_type_the_organizer_scans_use():
    pdf = negatives.render("ruling", random.Random(4)).pdf
    seen = {}
    for seed in (0, 1, 5):  # one grayscale, RGB and one-bit scan
        scanned, tags = scan.scan(pdf, random.Random(seed))
        seen[tags["scan_mode"]] = (b"/DeviceRGB" in scanned, b"/DCTDecode" in scanned, b"/CCITTFaxDecode" in scanned)
    assert seen == {"rgb": (True, True, False), "gray": (False, True, False), "bw": (False, False, True)}


def test_scans_are_image_only_with_the_same_page_count():
    rendered = appeal.render(case_for("przyklad_01", 2), random.Random(2))
    scanned, tags = scan.scan(rendered.pdf, random.Random(2))
    with pdfplumber.open(io.BytesIO(scanned)) as doc, pdfplumber.open(io.BytesIO(rendered.pdf)) as original:
        assert len(doc.pages) == len(original.pages)
        assert sum(len(page.chars) for page in doc.pages) == 0
    assert tags["scan_dpi"] in {"150", "200", "300"}


@pytest.mark.parametrize("kind", negatives.KINDS)
def test_negatives_have_text_and_an_empty_reference(kind):
    rendered = negatives.render(kind, random.Random(3))
    assert rendered.gold == {} and len(text_of(rendered.pdf)) > 80
    assert rendered.tags["class"] == "negatywny" and rendered.tags["neg_kind"] == kind


def test_corpus_has_the_three_documents_per_case_and_the_requested_negatives():
    items = build_cases(["przyklad_01", "przyklad_02"], 2, seed=1, scan_share=0.5) + build_negatives(2, 1, 0.0)
    positives = [i for i in items if i.gold]
    assert len(positives) == 2 * 2 * 3 and len(items) - len(positives) == 2 * len(negatives.KINDS)
    assert {i.name for i in positives} == {"odwolanie.pdf", "pelnomocnictwo.pdf", "potwierdzenie_przelewu.pdf"}
    assert {i.tags["medium"] for i in items} <= {"text", "scan"}
    assert rng_for(1, "a").random() == rng_for(1, "a").random() != rng_for(2, "a").random()


def test_control_set_has_its_own_cases_and_the_same_facts_as_the_variants():
    control = build_cases(["przyklad_01"], 1, seed=1, scan_share=0.0, faithful=True)
    drifted = build_cases(["przyklad_01"], 1, seed=1, scan_share=0.0)
    assert {i.case for i in control} == {"przyklad_01-c0"} and {i.tags["set"] for i in control} == {"control"}
    assert {i.tags[f"{i.tags['class']}.variation"] for i in control} == {"none"}
    assert {i.tags["set"] for i in drifted} == {"variants"} and {i.case for i in drifted} == {"przyklad_01-v0"}
    same = {"odwolanie.pdf", "pelnomocnictwo.pdf"}  # a transfer may pay for another purpose than the training one
    assert {i.name: i.gold for i in control if i.name in same} == {i.name: i.gold for i in drifted if i.name in same}


def doc(case: str, name: str, cls: str, tp: int, fp: int, fn: int, by_field=None) -> DocResult:
    counts = Counts(tp, fp, fn)
    return DocResult(
        case,
        name,
        cls,
        cls,
        counts,
        counts_strict=counts,
        counts_non_null=counts,
        empty_output=False,
        by_field=by_field or {},
    )


def test_slices_split_media_and_rank_the_weakest_first():
    docs = [doc("c1", f"d{i}", "odwolanie", 4, 0, 0) for i in range(5)] + [
        doc("c2", f"s{i}", "odwolanie", 1, 3, 3) for i in range(5)
    ]
    tags = {(d.case, d.file): {"medium": "text" if d.case == "c1" else "scan", "odwolanie.family": "lap"} for d in docs}
    rows = slices(docs, tags)
    assert [(r["medium"], r["micro_f1"]) for r in rows] == [("scan", 0.25), ("text", 1.0)]
    assert slices(docs[:3], tags) == []  # fewer than five documents: not reported


def test_missing_negative_output_is_reported_without_a_field_penalty(tmp_path):
    output = tmp_path / "present.json"
    output.write_text("{}\n")
    docs = [score_doc("case", name, tmp_path / name, {}) for name in ("absent.json", "present.json")]
    tags = {(d.case, d.file): {"medium": "text", "neg_kind": "ruling"} for d in docs}
    preds = {("case", "absent.json"): None, ("case", "present.json"): {}}
    report = build_report(docs, tags, dict.fromkeys(tags, {}), preds, min_docs=1)
    row = report["slices"][0]
    assert (row["perfect_docs"], row["fp"], row["fn"]) == (1, 0, 0)
    assert [(d["file"], d["errors"]) for d in report["worst_docs"]] == [("absent.json", 1)]


def test_confusion_counts_where_each_class_was_routed():
    docs = [
        doc("c1", "a", "odwolanie", 4, 0, 0),
        replace(doc("c1", "b", "odwolanie", 0, 0, 4), pred_class="negatywny"),
        replace(doc("c1", "c", "przelew", 0, 0, 4), pred_class=None),
        doc("c2", "d", "negatywny", 0, 0, 0),
    ]
    assert confusion(docs) == {
        "negatywny": {"negatywny": 1},
        "odwolanie": {"negatywny": 1, "odwolanie": 1},
        "przelew": {"None": 1},
    }


def test_misrouted_lists_the_wrongly_routed_documents_with_their_tags():
    wrong = replace(doc("c1", "b", "przelew", 0, 0, 4), pred_class="negatywny")
    docs = [
        doc("c1", "a", "odwolanie", 4, 0, 0),
        wrong,
        replace(doc("c2", "c", "negatywny", 0, 2, 0), pred_class="przelew"),
    ]
    tags = {(d.case, d.file): {"medium": "scan" if d.file == "b" else "text", "przelew.layout": "ledger"} for d in docs}
    rows = build_report(docs, tags, {(d.case, d.file): {} for d in docs}, {(d.case, d.file): None for d in docs})
    assert [(r["case"], r["file"], r["class"], r["predicted_class"]) for r in rows["misrouted"]] == [
        ("c1", "b", "przelew", "negatywny"),
        ("c2", "c", "negatywny", "przelew"),
    ]
    assert rows["misrouted"][0]["tags"] == {"medium": "scan", "przelew.layout": "ledger"}


def test_field_diffs_show_expected_and_predicted_values():
    reference = {"a": {"nazwa": "Alfa sp. z o.o.", "nip": "1234563218"}}
    prediction = {"a": {"nazwa": "Beta", "nip": "123-456-32-18"}}
    assert field_diffs(reference, prediction) == [{"field": "a.nazwa", "expected": "alfa sp. z o.o.", "got": ["beta"]}]


def test_report_lists_fields_weakest_first_and_worst_documents():
    docs = [doc("c1", "a", "odwolanie", 2, 1, 1, {"x.krs": Counts(0, 1, 1), "x.nip": Counts(2, 0, 0)})]
    tags = {("c1", "a"): {"medium": "text"}}
    report = build_report(docs, tags, {("c1", "a"): {"x": {"krs": "1", "nip": "2"}}}, {("c1", "a"): None})
    assert list(report["by_field"]) == ["x.krs", "x.nip"]
    assert report["worst_docs"][0]["errors"] == 2 and report["by_medium"]["text"]["docs"] == 1


def test_parse_cases():
    assert parse_cases("1-3,7") == ["przyklad_01", "przyklad_02", "przyklad_03", "przyklad_07"]
    for bad in ("61", "5-3", "5-3,7", ""):
        with pytest.raises(ValueError):
            parse_cases(bad)


def test_dump_without_running_the_app(tmp_path: Path):
    assert main(["--cases", "1", "--negatives", "1", "--scan-share", "0", "--no-run", "--dump", str(tmp_path)]) == 0
    index = json.loads((tmp_path / "tags.json").read_text(encoding="utf-8"))
    assert "przyklad_01-v0/odwolanie.pdf" in index and (tmp_path / "przyklad_01-v0" / "odwolanie.gold.json").is_file()


def test_end_to_end_with_a_stub_app_that_answers_nothing(tmp_path: Path):
    stub = tmp_path / "stub.py"
    stub.write_text(
        "import sys, pathlib\n"
        "src, dst = map(pathlib.Path, sys.argv[1:3])\n"
        "for pdf in src.rglob('*.pdf'):\n"
        "    out = dst / pdf.relative_to(src).with_suffix('.json')\n"
        "    out.parent.mkdir(parents=True, exist_ok=True)\n"
        "    out.write_text('{}')\n",
        encoding="utf-8",
    )
    report = tmp_path / "variants.json"
    code = main(
        [
            "--cases",
            "1",
            "--negatives",
            "1",
            "--scan-share",
            "0",
            "--cmd",
            f"{sys.executable} {stub} {{input}} {{output}}",
        ]
        + ["--out", str(report)]
    )
    results = json.loads(report.read_text(encoding="utf-8"))
    assert code == 0 and results["n_docs"] == 3 + len(negatives.KINDS) + 3
    assert results["summary"]["counts"]["fp"] == 0 and results["summary"]["micro_f1"] == 0.0
    assert results["negative_families"] == {kind: {"docs": 1, "empty": 1} for kind in negatives.KINDS}
    assert results["worst_docs"] and "differences" in results["worst_docs"][0]
    assert results["control"]["summary"]["micro_f1"] == 0.0 and results["control"]["by_medium"]["text"]["docs"] == 3


def stub_app(tmp_path: Path, body: str) -> Path:
    stub = tmp_path / "stub.py"
    stub.write_text(
        "import sys, pathlib\nsrc, dst = map(pathlib.Path, sys.argv[1:3])\npdfs = sorted(src.rglob('*.pdf'))\n" + body,
        encoding="utf-8",
    )
    return stub


def test_a_partial_app_failure_is_scored_and_reported(tmp_path: Path):
    stub = stub_app(
        tmp_path,
        "for pdf in pdfs[1:]:\n"
        "    out = dst / pdf.relative_to(src).with_suffix('.json')\n"
        "    out.parent.mkdir(parents=True, exist_ok=True)\n"
        "    out.write_text('{}')\n"
        "print('doc not processed', file=sys.stderr)\n"
        "sys.exit(1)\n",
    )
    report = tmp_path / "variants.json"
    args = [
        "--cases",
        "1",
        "--negatives",
        "1",
        "--scan-share",
        "0",
        "--cmd",
        f"{sys.executable} {stub} {{input}} {{output}}",
    ]
    assert main([*args, "--out", str(report)]) == 1
    results = json.loads(report.read_text(encoding="utf-8"))
    assert "doc not processed" in results["app_error"] and results["summary"]["outputs_complete"] < 1


def test_an_app_that_writes_nothing_is_an_error(tmp_path: Path):
    stub = stub_app(tmp_path, "sys.exit(3)\n")
    args = [
        "--cases",
        "1",
        "--negatives",
        "1",
        "--scan-share",
        "0",
        "--cmd",
        f"{sys.executable} {stub} {{input}} {{output}}",
    ]
    assert main([*args, "--out", str(tmp_path / "variants.json")]) == 2
    assert not (tmp_path / "variants.json").exists()


def test_a_run_without_negatives_or_variants_still_prints_a_summary(tmp_path: Path, capsys):
    stub = stub_app(
        tmp_path,
        "for pdf in pdfs:\n"
        "    out = dst / pdf.relative_to(src).with_suffix('.json')\n"
        "    out.parent.mkdir(parents=True, exist_ok=True)\n"
        "    out.write_text('{}')\n",
    )
    args = ["--cases", "1", "--scan-share", "0", "--cmd", f"{sys.executable} {stub} {{input}} {{output}}"]
    assert main([*args, "--negatives", "0", "--out", str(tmp_path / "no-negatives.json")]) == 0
    assert main([*args, "--n", "0", "--negatives", "0", "--out", str(tmp_path / "control-only.json")]) == 0
    assert "n/a" in capsys.readouterr().out
    control_only = json.loads((tmp_path / "control-only.json").read_text(encoding="utf-8"))
    assert control_only["n_docs"] == 3 and control_only["summary"]["micro_f1"] is None


def test_an_empty_corpus_is_refused(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--n", "0", "--control", "0", "--negatives", "0"])
    assert exit_info.value.code == 2 and "nothing to generate" in capsys.readouterr().err


def test_family_benchmark_has_a_separate_default_report():
    from evals.document_variants.run import parser
    from evals.variants import evaluate_variants

    assert callable(evaluate_variants)
    assert parser().parse_args([]).out.name == "document-variants.json"


@pytest.mark.parametrize(
    "option,value", [("--n", "-1"), ("--control", "-1"), ("--negatives", "-1"), ("--scan-share", "1.1")]
)
def test_invalid_corpus_sizes_fail_before_generation(option, value):
    with pytest.raises(SystemExit) as exc:
        main([option, value])
    assert exc.value.code == 2
