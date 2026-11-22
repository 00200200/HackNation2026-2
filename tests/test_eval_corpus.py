import io
import json
import os
import re
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest
from PIL import Image

from evals import field_report, run
from evals.metrics import CLASSES


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "corpus"
    for tree in ["cases", "gold"]:
        (root / tree).mkdir(parents=True)
    return root


@cache
def invented_pdf():
    stream = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(stream, format="PDF")
    return stream.getvalue()


def add_document(corpus, case, name, gold):
    for tree, extension, content in [
        ("cases", ".pdf", invented_pdf()),
        ("gold", ".json", json.dumps(gold) if gold else ""),
    ]:
        path = corpus / tree / case / (name + extension)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for key in os.environ.copy():
        if key.startswith("GIT_"):
            monkeypatch.delenv(key)
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

    def app(cmd, inputs, outputs):
        assert sorted(p.relative_to(inputs).as_posix() for p in inputs.rglob("*.pdf")) == [
            "private-case/dokument_01.pdf",
            "second/dokument_01.pdf",
        ]
        for directory in inputs.iterdir():
            (outputs / directory.name).mkdir()
            data = {"private-key": "private-value"} if directory.name == case else {}
            (outputs / directory.name / "dokument_01.json").write_text(json.dumps(data))
        return 1.0, None

    monkeypatch.setattr(run, "run_app", app)
    monkeypatch.setattr(sys, "argv", ["eval", "--corpus", str(corpus), "--detail-out", str(detail)])
    assert run.main() == 1
    public = (repo / "evals/results/corpus-latest.json").read_text()
    assert "private" not in public
    aggregate = json.loads(public)
    assert "docs" not in aggregate
    assert aggregate["n_cases"] == aggregate["n_docs"] == 2
    assert aggregate["detail"]["counts"] == {"tp": 0, "fp": 1, "fn": 1, "tn": 0}
    assert aggregate["detail"]["routing_by_class"]["pelnomocnictwo"] == {"correct": 0, "total": 1}
    assert aggregate["detail"]["routing_by_class"]["negatywny"] == {"correct": 1, "total": 1}
    assert len(json.loads(detail.read_text())["docs"]) == 2
    assert (repo / "evals/results/latest.json").read_text() == "training"
    assert (repo / ".git/eval-latest.json").read_text() == "gate"


def test_missing_prediction_in_corpus(corpus, repo, monkeypatch, tmp_path):
    add_document(corpus, "negatywne", "two.parts", {"OdwolanieKIO": {"field": 42}})
    monkeypatch.setattr(sys, "argv", ["eval", "--corpus", str(corpus), "--pred", str(tmp_path / "absent")])
    assert run.main() == 1
    report = json.loads((repo / "evals/results/corpus-latest.json").read_text())
    assert report["n_cases"] == 1
    assert report["detail"]["counts"] == {"tp": 0, "fp": 0, "fn": 1, "tn": 0}
    assert report["detail"]["macro_f1_documents"] == report["detail"]["macro_f1_fields"] == 0
    assert report["detail"]["macro_f1_classes"] == 0
    assert report["detail"]["macro_f1_class_count"] == 1


@pytest.mark.parametrize("command", [run, field_report])
def test_empty_corpus(corpus, repo, monkeypatch, capsys, command):
    assert_input_abort(command, ["--corpus", corpus], repo, monkeypatch, capsys)


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
    predictions = corpus / "pred"
    (predictions / "alpha").mkdir(parents=True)
    (predictions / "alpha/one.json").write_text('{"mocodawca": 1}')
    (predictions / "alpha/two.json").write_text("{}\n")
    monkeypatch.setattr(sys, "argv", ["eval", "--corpus", str(corpus), "--split", "dev", "--pred", str(predictions)])
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
    with pytest.raises(SystemExit, match="2"):
        field_report.main()
    captured = capsys.readouterr()
    assert "secret" not in captured.out + captured.err
    monkeypatch.setattr(sys, "argv", argv + ["--errors"])
    with pytest.raises(SystemExit) as error:
        field_report.main()
    assert error.value.code == 2
    capsys.readouterr()
    dest = tmp_path / "details.txt"
    monkeypatch.setattr(sys, "argv", argv + ["--errors", "--detail-out", str(dest)])
    with pytest.raises(SystemExit, match="2"):
        field_report.main()
    captured = capsys.readouterr()
    assert "secret" not in captured.out + captured.err
    assert not dest.exists()


@pytest.mark.parametrize("command", [run, field_report])
def test_private_report_rejects_all_worktrees_and_git_dirs(corpus, repo, tmp_path, monkeypatch, command):
    def git(*args, cwd=repo):
        return subprocess.check_output(["git", *args], cwd=cwd)

    git("-c", "user.name=Tester", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-m", "test")
    active, sibling = tmp_path / "active", tmp_path / "other checkout"
    for checkout in (active, sibling):
        git("worktree", "add", "--detach", str(checkout))
    monkeypatch.setattr(run, "ROOT", active)
    alias = tmp_path / "alias"
    alias.symlink_to(sibling, target_is_directory=True)
    git_dir = Path(git("rev-parse", "--absolute-git-dir", cwd=active).decode().strip())
    unrelated = tmp_path / "unrelated"
    git("init", "--bare", "-q", str(unrelated))
    monkeypatch.setenv("GIT_DIR", str(unrelated))
    for directory in (repo, alias, repo / ".git", git_dir):
        destination = directory / "missing" / "details.json"
        monkeypatch.setattr(sys, "argv", ["eval", "--corpus", str(corpus), "--detail-out", str(destination)])
        # The command must reject the argument before it can touch corpus data.
        monkeypatch.setattr(command, "load_corpus", lambda *args: pytest.fail("accepted repository destination"))
        with pytest.raises(SystemExit) as error:
            command.main()
        assert error.value.code == 2
        assert not destination.parent.exists()


@pytest.mark.parametrize("command", [run, field_report])
@pytest.mark.parametrize("source", ["manifest", "gold", "pdf"])
def test_test_split_io_errors_report_only_type_and_count(corpus, repo, monkeypatch, capsys, command, source):
    add_document(corpus, "private-case", "private-doc", {})
    manifest = corpus / "SPLIT.json"
    manifest.write_text(json.dumps({"dev": [], "test": ["private-case"]}))

    def denied(*args, **kwargs):
        raise PermissionError(13, "private-message", "private-path")

    if source == "pdf":
        if command is run:
            monkeypatch.setattr(run.shutil, "copy", denied)
        else:
            monkeypatch.setattr(field_report, "process_pdf", denied)
    else:
        target = manifest if source == "manifest" else corpus / "gold/private-case/private-doc.json"
        read_text = Path.read_text

        def read(path, *args, **kwargs):
            if path == target:
                denied()
            return read_text(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", read)

    monkeypatch.setattr(sys, "argv", ["eval", "--corpus", str(corpus), "--split", "test"])
    with pytest.raises(SystemExit) as error:
        command.main()
    assert error.value.code == 2
    captured = capsys.readouterr()
    console = captured.out + captured.err
    assert "PermissionError" in console and "1" in console
    assert "private" not in console and str(corpus) not in console


def assert_input_abort(command, args, repo, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["eval", *map(str, args)])
    with pytest.raises(SystemExit) as error:
        command.main()
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.err
    if "--corpus" in args:
        assert "private" not in captured.out + captured.err
    assert not (repo / "evals/results/corpus-latest.json").exists()
    assert (repo / "evals/results/latest.json").read_text() == "training"
    assert (repo / ".git/eval-latest.json").read_text() == "gate"


@pytest.mark.parametrize("command", [run, field_report])
@pytest.mark.parametrize(
    "fault",
    [
        "both-dirs",
        "empty-case",
        "no-gold-dir",
        "missing-pdf",
        "invalid-pdf",
        "damaged-lzw",
        "damaged-flate",
        "unreadable-pdf",
        "invalid-utf8",
        "invalid-json",
        "non-object",
        "unreadable-reference",
        "invalid-manifest",
        "missing-manifest-case",
        "directory-manifest",
    ],
)
def test_selected_inputs_abort_before_publication(corpus, repo, monkeypatch, capsys, command, fault):
    case = "private-case"
    add_document(corpus, case, "private-doc", {"mocodawca": 1})
    add_document(corpus, "second", "other", {"mocodawca": 2})
    manifest = corpus / "SPLIT.json"
    manifest.write_text(json.dumps({"dev": [], "test": [case, "second"]}))
    pdf = corpus / "cases" / case / "private-doc.pdf"
    ref = corpus / "gold" / case / "private-doc.json"
    if fault == "both-dirs":
        iterdir = Path.iterdir

        def restricted(path):
            if path.name == case:
                raise PermissionError("private-path")
            return iterdir(path)

        monkeypatch.setattr(Path, "iterdir", restricted)
    elif fault == "empty-case":
        pdf.unlink()
        ref.unlink()
    elif fault == "no-gold-dir":
        ref.unlink()
        ref.parent.rmdir()
    elif fault == "missing-pdf":
        pdf.unlink()
    elif fault in {"damaged-lzw", "damaged-flate"}:
        # Keep the page tree intact and make its content stream undecodable.
        data = invented_pdf()
        contents = re.search(rb"/Contents (\d+) 0 R", data)[1]
        stream = re.compile(rb"(?m)^" + contents + rb" 0 obj.*?endstream", re.DOTALL)
        encoding = b"LZWDecode" if fault == "damaged-lzw" else b"FlateDecode"
        data, count = stream.subn(
            contents
            + b" 0 obj\n<< /Length 3 /Filter /"
            + encoding
            + b" >>\nstream\n"
            + bytes([255]) * 3
            + b"\nendstream",
            data,
        )
        assert count == 1
        pdf.write_bytes(data)
    elif fault == "invalid-pdf":
        pdf.write_bytes(b"private undecodable PDF")
    elif fault in {"unreadable-pdf", "unreadable-reference"}:
        original = Path.open

        def restricted_open(path, *args, **kwargs):
            if path == (pdf if fault == "unreadable-pdf" else ref):
                raise PermissionError("private-path")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", restricted_open)
    elif fault == "invalid-manifest":
        manifest.write_bytes(b"\xff")
    elif fault == "missing-manifest-case":
        manifest.write_text(json.dumps({"dev": [], "test": ["second", "absent"]}))
    elif fault == "directory-manifest":
        manifest.unlink()
        manifest.mkdir()
    else:
        ref.write_bytes({"invalid-utf8": b"\xff", "invalid-json": b"{", "non-object": b"[]"}[fault])
    args = ["--corpus", corpus, "--split", "test"]
    if command is run:
        args.extend(["--pred", corpus / "gold"])
    assert_input_abort(command, args, repo, monkeypatch, capsys)


@pytest.fixture
def training_tree(repo):
    data = repo / "data/uzp/dane"
    for case in run.QUICK:
        folder = data / case
        folder.mkdir(parents=True)
        if case == "negatywne":
            for i in range(4):
                (folder / f"negative_{i}.pdf").write_bytes(invented_pdf())
        else:
            for pdf, ref in run.GOLD_FOR.items():
                (folder / pdf).write_bytes(invented_pdf())
                (folder / ref).write_text(json.dumps({CLASSES[Path(ref).stem]: 1}))
    subprocess.run(["git", "add", "data"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Tester",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Invented organizer inventory",
        ],
        cwd=repo,
        check=True,
    )
    return data


@pytest.mark.parametrize(
    "fault",
    [
        "control",
        "invalid-utf8",
        "invalid-json",
        "non-object",
        "missing-ref",
        "missing-pair",
        "quick-case",
        "quick-negative",
        "extra-negative-gold",
        "uppercase-negative-gold",
        "full-coverage",
        "empty-positive",
        "wrong-class",
        "no-leaves",
        "mixed-class",
        "extra-pdf",
        "corrupt-pdf",
    ],
)
def test_training_inventory_and_references(training_tree, repo, monkeypatch, capsys, fault):
    case = training_tree / "przyklad_01"
    pdf = case / "odwolanie.pdf"
    ref = case / "odwolanie.json"
    args = ["--pred", training_tree, "--data", training_tree]
    if fault != "full-coverage":
        args.append("--quick")
    if fault == "control":
        monkeypatch.setattr(sys, "argv", ["eval", *map(str, args)])
        assert run.main() == 1  # Missing predictions still produce a score.
        assert json.loads((repo / ".git/eval-latest.json").read_text())["n_docs"] == 21
        return
    if fault in {"invalid-utf8", "invalid-json", "non-object"}:
        ref.write_bytes({"invalid-utf8": b"\xff", "invalid-json": b"{", "non-object": b"[]"}[fault])
    elif fault in {"empty-positive", "wrong-class", "no-leaves", "mixed-class"}:
        ref.write_bytes(
            {
                "empty-positive": b"",
                "wrong-class": b'{"mocodawca":1}',
                "no-leaves": b'{"OdwolanieKIO":{}}',
                "mixed-class": b'{"OdwolanieKIO":{},"przelew_bankowy":{"kwota":100}}',
            }[fault]
        )
    elif fault in {"missing-ref", "missing-pair"}:
        ref.unlink()
        if fault == "missing-pair":
            pdf.unlink()
    elif fault == "quick-case":
        case.rename(training_tree / "replacement")
    elif fault in {"extra-negative-gold", "uppercase-negative-gold"}:
        suffix = ".JSON" if fault == "uppercase-negative-gold" else ".json"
        (training_tree / "negatywne" / ("negative_0" + suffix)).write_text('{"mocodawca": 1}')
    elif fault == "quick-negative":
        (training_tree / "negatywne/negative_0.pdf").unlink()
    elif fault == "extra-pdf":
        (case / "unexpected.pdf").write_bytes(invented_pdf())
    elif fault == "corrupt-pdf":
        pdf.write_bytes(b"invalid")
    assert_input_abort(run, args, repo, monkeypatch, capsys)


@pytest.mark.parametrize(
    ("payload", "valid"),
    [
        (b"{}", True),
        (b"", False),
        (None, False),
        (b"\xff", False),
        (b"\xef\xbb\xbf{}", False),
        (b"[1]", False),
        (b"{", False),
        ("unreadable", False),
    ],
)
def test_prediction_faults_still_score(corpus, repo, monkeypatch, payload, valid):
    add_document(corpus, "one", "doc", {"mocodawca": 1})
    pred = corpus / "pred/one/doc.json"
    pred.parent.mkdir(parents=True)
    if payload == "unreadable":
        pred.mkdir()
    elif payload is not None:
        pred.write_bytes(payload)
    monkeypatch.setattr(sys, "argv", ["eval", "--corpus", str(corpus), "--pred", str(corpus / "pred")])
    assert run.main() == 1
    detail = json.loads((repo / "evals/results/corpus-latest.json").read_text())["detail"]
    assert detail["counts"] == {"tp": 0, "fp": 0, "fn": 1, "tn": 0}
    assert detail["outputs_complete"] == int(valid)


def test_extractor_failure_cannot_publish_partial_results(corpus, repo, monkeypatch, capsys):
    add_document(corpus, "private-case", "private-doc", {})
    monkeypatch.setattr(run, "run_app", lambda *args: (1, "private failure"))
    assert_input_abort(run, ["--corpus", corpus], repo, monkeypatch, capsys)


@pytest.mark.parametrize("readable", [True, False])
def test_empty_pdfminer_page_tree_requires_an_independent_decode(tmp_path, monkeypatch, readable):
    from contextlib import nullcontext
    from types import SimpleNamespace

    path = tmp_path / "fixture.pdf"
    path.write_bytes(invented_pdf() if readable else b"%PDF-1.7\nundecryptable")
    monkeypatch.setattr(run.pdfplumber, "open", lambda _: nullcontext(SimpleNamespace(pages=[])))
    if readable:
        run.check_pdf(path)
    else:
        with pytest.raises(ValueError, match="could not be decoded"):
            run.check_pdf(path)


def test_organizer_scan_predictions_preserve_nested_paths_and_training_gate(repo, monkeypatch):
    data = repo / "data/uzp/dane"
    for group, marker in [("odwolania", "OdwolanieKIO"), ("potwierdzenia", "przelew_bankowy")]:
        folder = data / "skany" / group / "0001"
        folder.mkdir(parents=True)
        (folder / "0001.pdf").write_bytes(invented_pdf())
        (folder / "0001.json").write_text(json.dumps({marker: {"field": 1}}))
    subprocess.run(["git", "add", "data"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Tester",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-qm",
            "Invented scan inventory",
        ],
        cwd=repo,
        check=True,
    )
    monkeypatch.setattr(sys, "argv", ["eval", "--organizer-scans", "--data", str(data), "--pred", str(data)])
    assert run.main() == 0
    report = json.loads((repo / "evals/results/organizer-scans.json").read_text())
    assert report["n_docs"] == 2 and report["detail"]["micro_f1"] == 1
    assert report["detail"]["routing_by_class"]["przelew"]["correct"] == 1
    assert "docs" not in report and (repo / ".git/eval-latest.json").read_text() == "gate"
