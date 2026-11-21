import json
import subprocess
import sys

import pytest

from evals import field_report, run


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "corpus"
    for tree in ["cases", "gold"]:
        (root / tree).mkdir(parents=True)
    return root


def add_document(corpus, case, name, gold):
    for tree, extension, content in [
        ("cases", ".pdf", "invented PDF"),
        ("gold", ".json", json.dumps(gold) if gold else ""),
    ]:
        path = corpus / tree / case / (name + extension)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", root], check=True)
    result = root / "evals/results/latest.json"
    result.parent.mkdir(parents=True)
    result.write_text("training")
    (root / ".git/eval-latest.json").write_text("gate")
    monkeypatch.setattr(run, "ROOT", root)
    monkeypatch.setattr(run, "RESULTS", result)
    return root


def test_corpus_staging_aggregation_and_private_detail(corpus, repo, monkeypatch, tmp_path):
    case = "private-case"
    add_document(corpus, case, "private-file", {"mocodawca": "private-value"})
    add_document(corpus, "second", "private-file", {})
    detail = tmp_path / "private" / "report.json"

    def failed_app(cmd, inputs, outputs):
        assert sorted(p.relative_to(inputs).as_posix() for p in inputs.rglob("*.pdf")) == [
            "private-case/dokument_01.pdf",
            "second/dokument_01.pdf",
        ]
        for directory in inputs.iterdir():
            (outputs / directory.name).mkdir()
            data = {"private-key": "private-value"} if directory.name == case else {}
            (outputs / directory.name / "dokument_01.json").write_text(json.dumps(data))
        return 1.0, "private-error"

    monkeypatch.setattr(run, "run_app", failed_app)
    monkeypatch.setattr(sys, "argv", ["eval", "--corpus", str(corpus), "--detail-out", str(detail)])
    assert run.main() == 1
    public = (repo / "evals/results/corpus-latest.json").read_text()
    assert "private" not in public
    aggregate = json.loads(public)
    assert "docs" not in aggregate
    assert aggregate["n_cases"] == aggregate["n_docs"] == 2
    assert aggregate["detail"]["counts"] == {"tp": 0, "fp": 1, "fn": 1}
    assert len(json.loads(detail.read_text())["docs"]) == 2
    assert (repo / "evals/results/latest.json").read_text() == "training"
    assert (repo / ".git/eval-latest.json").read_text() == "gate"


def test_missing_prediction_in_corpus(corpus, repo, monkeypatch, tmp_path):
    add_document(corpus, "negatywne", "two.parts", {"OdwolanieKIO": {"field": 42}})
    monkeypatch.setattr(sys, "argv", ["eval", "--corpus", str(corpus), "--pred", str(tmp_path / "absent")])
    assert run.main() == 1
    report = json.loads((repo / "evals/results/corpus-latest.json").read_text())
    assert report["n_cases"] == 1
    assert report["detail"]["counts"] == {"tp": 0, "fp": 0, "fn": 1}
    assert report["detail"]["macro_f1_documents"] == report["detail"]["macro_f1_fields"] == 0
    assert report["detail"]["macro_f1_classes"] == 0
    assert report["detail"]["macro_f1_class_count"] == 1


def test_empty_corpus(corpus, repo, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["eval", "--corpus", str(corpus), "--pred", str(corpus)])
    assert run.main() == 1
    summary = json.loads((repo / "evals/results/corpus-latest.json").read_text())
    assert summary["n_docs"] == 0 and summary["detail"]["macro_f1_documents"] is None
    monkeypatch.setattr(sys, "argv", ["report", "--corpus", str(corpus)])
    field_report.main()
    assert "documents=0" in capsys.readouterr().out


def test_private_detail_must_be_outside_repo(corpus, repo, tmp_path, monkeypatch):
    link = tmp_path / "link"
    link.symlink_to(repo, target_is_directory=True)
    monkeypatch.setattr(sys, "argv", ["eval", "--corpus", str(corpus), "--detail-out", str(link / "private.json")])
    with pytest.raises(SystemExit) as error:
        run.main()
    assert error.value.code == 2 and not (repo / "private.json").exists()


@pytest.mark.parametrize("bad", ["missing-gold", "bad-gold", "orphan-gold"])
def test_unpaired_or_invalid_reference(corpus, bad):
    add_document(corpus, "one", "doc", {})
    if bad == "missing-gold":
        (corpus / "gold/one/doc.json").unlink()
    elif bad == "bad-gold":
        (corpus / "gold/one/doc.json").write_text("[invalid")
    else:
        (corpus / "cases/one/doc.pdf").unlink()
    with pytest.raises(ValueError):
        run.load_corpus(corpus)


def test_field_report_forces_ocr_on_corpus_pdf(corpus, monkeypatch, capsys):
    add_document(corpus, "one", "doc", {"mocodawca": "invented"})

    def process(path, *, force_ocr):
        assert path == corpus / "cases/one/doc.pdf" and force_ocr
        return "", {"mocodawca": "different"}

    monkeypatch.setattr(field_report, "process_pdf", process)
    monkeypatch.setattr(sys, "argv", ["report", "--corpus", str(corpus), "--force-ocr", "--errors"])
    field_report.main()
    assert "one/doc.pdf | mocodawca | wrong" in capsys.readouterr().out


def test_scores_matching_predictions_for_single_class_corpus(corpus, repo, monkeypatch):
    for case in ("first", "second"):
        add_document(corpus, case, "one.document", {"mocodawca": case})
    monkeypatch.setattr(sys, "argv", ["eval", "--corpus", str(corpus), "--pred", str(corpus / "gold")])
    assert run.main() == 0
    report = json.loads((repo / "evals/results/corpus-latest.json").read_text())
    assert report["detail"]["per_class_f1"] == {"pelnomocnictwo": 1}
    assert report["detail"]["macro_f1_class_count"] == 1
    assert report["detail"]["macro_f1_classes"] == report["detail"]["micro_f1"] == 1


def test_split_selects_whole_cases_and_skips_other_gold(corpus, repo, monkeypatch):
    add_document(corpus, "alpha", "one", {"mocodawca": 1})
    add_document(corpus, "alpha", "two", {})
    add_document(corpus, "beta", "three", {"mocodawca": 2})
    (corpus / "SPLIT.json").write_text(json.dumps({"dev": ["alpha"], "test": ["beta"]}))
    assert len(run.load_corpus(corpus, "all")) == 2
    (corpus / "gold/beta/three.json").write_text("invalid")
    monkeypatch.setattr(
        sys, "argv", ["eval", "--corpus", str(corpus), "--split", "dev", "--pred", str(corpus / "gold")]
    )
    assert run.main() == 0
    report = json.loads((repo / "evals/results/corpus-latest.json").read_text())
    assert (report["split"], report["n_cases"], report["n_docs"]) == ("dev", 1, 2)


@pytest.mark.parametrize(
    "manifest", [None, {"dev": ["one"], "test": ["one"]}, {"dev": [], "test": []}, {"dev": "one", "test": []}]
)
def test_explicit_split_needs_valid_partition(corpus, manifest):
    add_document(corpus, "one", "doc", {})
    if manifest is not None:
        (corpus / "SPLIT.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        run.load_corpus(corpus, "dev")


@pytest.mark.parametrize("split", ["all", "test"])
def test_field_report_protects_test_diagnostics(corpus, tmp_path, monkeypatch, capsys, split):
    add_document(corpus, "secret-case", "secret-name", {"mocodawca": "secret-value"})
    (corpus / "SPLIT.json").write_text(json.dumps({"dev": [], "test": ["secret-case"]}))

    def damaged(*args, **kwargs):
        raise ValueError("secret-error")

    monkeypatch.setattr(field_report, "process_pdf", damaged)
    argv = ["report", "--corpus", str(corpus), "--split", split]
    monkeypatch.setattr(sys, "argv", argv)
    field_report.main()
    captured = capsys.readouterr()
    assert "documents=1" in captured.out and "secret" not in captured.out + captured.err
    monkeypatch.setattr(sys, "argv", argv + ["--errors"])
    with pytest.raises(SystemExit) as error:
        field_report.main()
    assert error.value.code == 2
    capsys.readouterr()
    dest = tmp_path / "details.txt"
    monkeypatch.setattr(sys, "argv", argv + ["--errors", "--detail-out", str(dest)])
    field_report.main()
    captured = capsys.readouterr()
    assert "secret" not in captured.out + captured.err
    assert "secret-value" in dest.read_text() and "secret-error" in dest.read_text()
