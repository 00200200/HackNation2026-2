"""The scan stress eval: its variants, the rendering, the loss split and a run against a stub app."""

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pytest
from PIL import Image, ImageDraw

from evals import scan_stress as stress
from evals.metrics import NEGATIVE, Counts, DocResult, summarise


def make_scan(folder: Path, name: str = "scan.pdf", pages: int = 2, dpi: int = 200) -> Path:
    """A synthetic image-only A4 scan: a row of black bars on white."""
    images = []
    for _ in range(pages):
        image = Image.new("L", (round(8.27 * dpi), round(11.69 * dpi)), 255)
        draw = ImageDraw.Draw(image)
        for row in range(10):
            draw.rectangle((150, 200 + row * 120, 1200, 230 + row * 120), fill=0)
        images.append(image)
    path = folder / name
    images[0].save(path, "PDF", save_all=True, append_images=images[1:], resolution=dpi)
    return path


def first_page(pdf_bytes: bytes, scale: float = 200 / 72) -> np.ndarray:
    with pdfium.PdfDocument(pdf_bytes) as pdf:
        return np.asarray(pdf[0].render(scale=scale, grayscale=True).to_pil())


def result(case: str, gold: str, routed: str | None, tp=0, fp=0, fn=0, fields=None, errors=None) -> DocResult:
    """What `score_doc` returns: `{}` is the class `negatywny` (routed=None); a missing JSON has no class and an error."""
    counts = Counts(tp=tp, fp=fp, fn=fn)
    pred = None if errors else routed or NEGATIVE
    return DocResult(case, "x.pdf", gold, pred, counts, counts, counts, pred == NEGATIVE, errors or [], fields or {})


def test_variants_cover_the_issue_matrix():
    found = stress.variants()
    skews = {name for name in found if name.startswith("skew")}
    assert skews == {"skew-3", "skew-2", "skew-1", "skew+1", "skew+2", "skew+3"}
    assert {"delivered", "rerender", "dpi-150", "dpi-300", "bw-200", "bw-300", "noise"} <= found.keys()
    assert [name for name in found if found[name].mixed] == ["mixed-1", "mixed-2", "mixed-3"]
    assert found["delivered"].dpi is None
    assert {found[name].encoding for name in ("bw-200", "bw-300")} == {"ccitt"}
    assert {found[name].skew for name in skews} == {-3.0, -2.0, -1.0, 1.0, 2.0, 3.0}
    assert all(spec.describe() for spec in found.values())


def test_the_delivered_variant_is_the_file_itself(tmp_path):
    path = make_scan(tmp_path)
    assert stress.render_pdf(path, stress.Spec(), "k") == path.read_bytes()


def test_rendering_is_deterministic_and_keeps_the_pages_image_only(tmp_path):
    path = make_scan(tmp_path, pages=3)
    spec = stress.Spec(dpi=150, skew=2.0, noise=stress.NOISE_SIGMA)
    first, again = stress.render_pdf(path, spec, "k"), stress.render_pdf(path, spec, "k")
    assert first == again
    assert (
        b"D:19700101000000Z" in first
    )  # Pillow would stamp the current time, and a second tick would change the bytes
    assert stress.render_pdf(path, spec, "other") != first  # the noise comes from the key
    with pdfium.PdfDocument(first) as pdf:
        assert len(pdf) == 3
        assert all(not page.get_textpage().get_text_range().strip() for page in pdf)
        assert all(len(list(page.get_objects(filter=[3]))) == 1 for page in pdf)  # one image per page, like the scans
        size = pdf[0].get_size()
    assert size == pytest.approx((8.27 * 72, 11.69 * 72), abs=2)  # the page size survives the resolution change


def test_the_one_bit_variant_is_a_ccitt_page(tmp_path):
    pdf = stress.render_pdf(make_scan(tmp_path), stress.Spec(dpi=200, encoding="ccitt"), "k")
    assert b"CCITTFaxDecode" in pdf
    with pdfium.PdfDocument(pdf) as document:
        (image,) = document[0].get_objects(filter=[3])
        assert image.get_metadata().bits_per_pixel == 1
    page = first_page(pdf)
    assert np.mean((page < 20) | (page > 235)) > 0.99  # black and white, bar the edges that the renderer smooths


def test_a_positive_skew_turns_the_page_counter_clockwise_by_that_angle(tmp_path):
    image = Image.new("L", (1654, 2339), 255)
    ImageDraw.Draw(image).rectangle((100, 1170, 1550, 1176), fill=0)  # one long horizontal rule
    path = tmp_path / "rule.pdf"
    image.save(path, "PDF", resolution=200)

    def rule_rows(skew: float) -> tuple[float, float]:
        page = first_page(stress.render_pdf(path, stress.Spec(dpi=200, skew=skew), "k"))
        return tuple(float(np.nonzero(page[:, side] < 128)[0].mean()) for side in (slice(200, 400), slice(1300, 1500)))

    left, right = rule_rows(3.0)
    assert left - right == pytest.approx(1100 * math.tan(math.radians(3.0)), abs=6)  # counter-clockwise: right end up
    left, right = rule_rows(0.0)
    assert left == pytest.approx(right, abs=1)


def test_mixed_variants_draw_their_settings_per_document_from_the_key(tmp_path):
    path = make_scan(tmp_path, pages=1)
    mixed = stress.Spec(mixed=True)
    outputs = {key: stress.render_pdf(path, mixed, key) for key in (f"2026/mixed-1/doc{n}" for n in range(12))}
    assert outputs == {key: stress.render_pdf(path, mixed, key) for key in outputs}
    sizes, ccitt = set(), set()
    for pdf in outputs.values():
        ccitt.add(b"CCITTFaxDecode" in pdf)
        with pdfium.PdfDocument(pdf) as document:
            (image,) = document[0].get_objects(filter=[3])
            sizes.add(round(image.get_metadata().horizontal_dpi))
    assert sizes <= set(stress.MIXED_DPI) and len(sizes) >= 2
    assert ccitt == {True, False}


def test_variants_are_cached_and_rebuilt_when_a_source_changes(tmp_path):
    source = stress.Source("skany/a/0001", "0001.pdf", make_scan(tmp_path, pages=1), {})
    cache, spec = tmp_path / "cache", stress.Spec(dpi=150)
    root = stress.build([source], "dpi-150", spec, 2026, cache, workers=1)
    built = root / source.case / source.name
    stamp = built.stat().st_mtime_ns
    assert stress.build([source], "dpi-150", spec, 2026, cache, workers=1) == root
    assert built.stat().st_mtime_ns == stamp  # a cached PDF is not rendered again
    assert not list(root.rglob("*.partial"))
    assert stress.build([source], "dpi-150", spec, 2027, cache, workers=1) != root  # another seed, another folder
    make_scan(tmp_path, pages=2)  # the same path now holds another scan
    assert stress.build([source], "dpi-150", spec, 2026, cache, workers=1) != root


def test_two_writers_of_one_variant_do_not_share_a_temporary_file(tmp_path, monkeypatch):
    target = tmp_path / "cache" / "case" / "0001.pdf"
    monkeypatch.setattr(stress, "render_pdf", lambda *args: b"%PDF rendered")
    job = (tmp_path / "source.pdf", stress.Spec(), "key", target)
    real_replace, published = os.replace, []

    def replace(source, destination):
        published.append(Path(source).name)
        if len(published) == 1:  # another run builds the same variant just before this one publishes it
            stress.write_variant(job)
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", replace)
    stress.write_variant(job)
    assert len(set(published)) == 2  # a temporary file of its own for each writer
    assert target.read_bytes() == b"%PDF rendered"
    assert list(target.parent.iterdir()) == [target]


def test_a_variant_that_cannot_be_published_leaves_no_temporary_file(tmp_path, monkeypatch):
    target = tmp_path / "cache" / "case" / "0001.pdf"
    monkeypatch.setattr(stress, "render_pdf", lambda *args: b"%PDF rendered")

    def refuse(source, destination):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(OSError, match="disk full"):
        stress.write_variant((tmp_path / "source.pdf", stress.Spec(), "key", target))
    assert list(target.parent.iterdir()) == []


def test_the_loss_split_adds_up_to_one_minus_the_micro_f1():
    routed_right = result("a", "odwolanie", "odwolanie", tp=7, fp=1, fn=2)
    misrouted = result("b", "przelew", None, fn=5)
    docs = [routed_right, misrouted, result("c", "przelew", "przelew", tp=6)]
    split = stress.loss_split(docs)
    assert (split["routing_errors"], split["field_errors"]) == (5, 3)
    assert split["routing"] + split["fields"] == pytest.approx(1 - summarise(docs)["micro_f1"])
    assert stress.loss_split([])["routing"] is None


def test_the_report_names_misrouted_documents_and_the_failing_fields_of_the_rest():
    wrong = Counts(fp=1, fn=2)
    docs = [
        result("v/skany/x/0001", "odwolanie", "odwolanie", tp=4, fp=1, fn=2, fields={"OdwolanieKIO.data": wrong}),
        result("v/skany/x/0002", "przelew", None, fn=5, fields={"przelew_bankowy.kwota": Counts(fn=1)}),
        result("v/skany/x/0003", "przelew", "przelew", tp=5),
    ]
    report = stress.variant_report(docs)
    assert report["misrouted"] == [{"doc": "v/skany/x/0002", "class": "przelew", "routed_as": "negatywny"}]
    assert report["routing"] == {"odwolanie": {"odwolanie": 1}, "przelew": {"negatywny": 1, "przelew": 1}}
    assert report["failing_fields"] == [
        {"path": "OdwolanieKIO.data", "tp": 0, "fp": 1, "fn": 2}
    ]  # not the misrouted one
    assert report["loss"]["routing_errors"] == 5


def test_a_document_without_output_is_not_reported_as_routed_to_a_negative():
    docs = [
        result("v/skany/x/0001", "przelew", None, fn=5),  # `{}`: the app decided it is unrelated
        result("v/skany/x/0002", "przelew", None, fn=5, errors=["missing or invalid JSON"]),
        result("v/skany/x/0003", "przelew", "przelew", tp=5),
    ]
    report = stress.variant_report(docs)
    assert report["no_output"] == 1
    assert report["routing"] == {"przelew": {"negatywny": 1, "no output": 1, "przelew": 1}}
    assert [row["routed_as"] for row in report["misrouted"]] == ["negatywny", "no output"]
    assert report["loss"]["routing_errors"] == 10  # both count as lost documents


def test_the_organizer_scans_load_as_thirty_sources():
    sources = stress.load_sources(stress.DATA)
    assert len(sources) == 30
    assert {s.case.split("/")[1] for s in sources} == {"odwolania", "pelnomocnictwa", "potwierdzenia"}
    assert all(s.path.is_file() and s.gold for s in sources)


STUB = """
import os
import sys
from pathlib import Path

source, target, answers = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
for pdf in source.rglob("*.pdf"):
    if "skew-3" in str(pdf):
        sys.exit("crashed on purpose")  # writes nothing for this variant
    answer = (answers / f"{pdf.parent.name}.json").read_text(encoding="utf-8")
    with (answers / "seen.txt").open("a", encoding="utf-8") as seen:
        seen.write(f"{pdf.relative_to(source)} {sorted(key for key, value in os.environ.items() if key.upper().startswith('KIO_') and value)}\\n")
    out = target / pdf.parent.relative_to(source) / (pdf.stem + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("{}" if any(name in str(pdf) for name in ("skew+3", "dpi-150")) else answer, encoding="utf-8")
"""


def stub_app(folder: Path, sources: list) -> str:
    """The command of an app that returns the reference of every document, `{}` for some variants and crashes on one."""
    answers = folder / "answers"
    answers.mkdir()
    for number, source in enumerate(sources, 1):  # the app sees przyklad_01, przyklad_02, ... in this order
        (answers / f"przyklad_{number:02d}.json").write_text(json.dumps(source.gold), encoding="utf-8")
    stub = folder / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    return f"{sys.executable} {stub} {{input}} {{output}} {answers}"


def test_a_run_scores_each_variant_apart_and_a_crash_in_one_leaves_the_others_alone(tmp_path):
    gold = {"przelew_bankowy": {"kwota": 100.0, "tytul": "x"}}
    sources = [
        stress.Source(f"skany/potwierdzenia/000{n}", f"000{n}.pdf", make_scan(tmp_path, f"s{n}.pdf", pages=1), gold)
        for n in (1, 2)
    ]
    cmd = stub_app(tmp_path, sources)
    roots = {
        name: stress.build(sources, name, spec, 2026, tmp_path / "cache", workers=1)
        for name, spec in stress.variants().items()
        if name in {"delivered", "skew+3", "skew-3"}
    }
    runs = {name: stress.score(sources, name, root, cmd) for name, root in roots.items()}
    assert {name: len(run.docs) for name, run in runs.items()} == {"delivered": 2, "skew+3": 2, "skew-3": 2}
    assert {name for name, run in runs.items() if run.error} == {"skew-3"}
    report = {name: stress.variant_report(run.docs) for name, run in runs.items()}
    assert report["delivered"]["micro_f1"] == 1.0 and report["delivered"]["misrouted"] == []
    assert report["skew+3"]["routing"] == {"przelew": {"negatywny": 2}}  # `{}` is a decision of the app
    assert report["skew+3"]["no_output"] == 0 and report["skew+3"]["loss"]["routing"] == 1.0
    assert report["skew-3"]["routing"] == {"przelew": {"no output": 2}}  # a crash is not
    assert report["skew-3"]["no_output"] == 2


def test_the_app_sees_neutral_folders_and_no_model_endpoint(tmp_path, monkeypatch):
    for name in [name for name in os.environ if name.upper().startswith("KIO_")]:
        monkeypatch.delenv(name)  # the stub reports every KIO_ variable with a value, so start from none
    monkeypatch.setenv("KIO_LLM_API_KEY", "not-a-real-key")
    monkeypatch.setenv("KIO_OCR_ENGINE", "not-the-default")
    gold = {"przelew_bankowy": {"kwota": 100.0, "tytul": "x"}}
    sources = [
        stress.Source("skany/potwierdzenia/0001", "0001.pdf", make_scan(tmp_path, "s1.pdf", pages=1), gold),
        stress.Source("skany/odwolania/0002", "0002.pdf", make_scan(tmp_path, "s2.pdf", pages=1), gold),
    ]
    cmd = stub_app(tmp_path, sources)
    root = stress.build(sources, "delivered", stress.Spec(), 2026, tmp_path / "cache", workers=1)
    run = stress.score(sources, "delivered", root, cmd)
    assert run.error is None and [d.counts.fn for d in run.docs] == [0, 0]
    seen = (tmp_path / "answers" / "seen.txt").read_text(encoding="utf-8").splitlines()
    assert sorted(line.split(" ")[0] for line in seen) == [
        "delivered/przyklad_01/dokument_01.pdf",
        "delivered/przyklad_02/dokument_01.pdf",
    ]  # no class, group or organizer scan id in a path
    assert all(line.endswith(" []") for line in seen)  # neither KIO_ variable of the shell reached the app with a value


def test_the_app_environment_drops_the_switches_the_jury_does_not_set(monkeypatch):
    for name in (
        "KIO_LLM_API_KEY",
        "kio_llm_model",
        "KIO_LLM_MODE",
        "KIO_OCR_ENGINE",
        "KIO_CLASSES_DIR",
        "KIO_CASE_REPAIR",
        "UV_ENV_FILE",
    ):
        monkeypatch.setenv(name, "1")
    monkeypatch.setenv("KIO_WEB_PORT", "8000")
    env = stress.app_env()
    assert {k: v for k, v in env.items() if k.upper().startswith("KIO_LLM_")} == stress.KEYLESS
    assert not {"KIO_OCR_ENGINE", "KIO_CLASSES_DIR", "KIO_CASE_REPAIR", "UV_ENV_FILE"} & env.keys()
    assert env["KIO_WEB_PORT"] == "8000" and env["PATH"] == os.environ["PATH"]  # the rest is untouched


def test_an_empty_endpoint_in_the_environment_beats_a_keyed_env_file(tmp_path):
    (tmp_path / ".env").write_text(
        "KIO_LLM_BASE_URL=http://example.invalid/v1\nKIO_LLM_MODEL=m\nKIO_LLM_API_KEY=k\n", encoding="utf-8"
    )
    code = "from kio2json.model_profile import ProfileSettings; print(ProfileSettings().profile().keyed)"

    def keyed(env: dict[str, str]) -> str:
        run = subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=env | {"PYTHONPATH": str(stress.ROOT)},
        )
        return run.stdout.strip()

    plain = {k: v for k, v in os.environ.items() if not k.upper().startswith("KIO_LLM_")}
    assert keyed(plain) == "True"  # control: the app does read this `.env` from its working folder
    assert keyed(stress.app_env()) == "False"


def test_a_relative_cache_path_scores_like_an_absolute_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    gold = {"przelew_bankowy": {"kwota": 100.0, "tytul": "x"}}
    sources = [stress.Source("skany/potwierdzenia/0001", "0001.pdf", make_scan(tmp_path, "s1.pdf", pages=1), gold)]
    cmd = stub_app(tmp_path, sources)
    root = stress.build(sources, "delivered", stress.Spec(), 2026, Path("cache"), workers=1)
    run = stress.score(sources, "delivered", root, cmd)
    assert run.error is None and run.docs[0].counts.fn == 0


def test_the_command_line_runs_every_variant_once_and_writes_the_report(tmp_path):
    cmd = stub_app(tmp_path, stress.load_sources(stress.DATA))
    out = tmp_path / "report.json"
    argv = ["--variants", "delivered,dpi-150,mixed-1,mixed-1", "--cache", str(tmp_path / "cache"), "--out", str(out)]
    assert stress.main([*argv, "--cmd", cmd]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert list(report["variants"]) == ["delivered", "dpi-150", "mixed-1"]  # a repeated name runs once
    assert {"commit", "dirty", "seed", "seconds_per_doc", "cmd", "environment"} <= report.keys()
    delivered, dropped = report["variants"]["delivered"], report["variants"]["dpi-150"]
    assert delivered["docs"] == 30 and delivered["micro_f1"] == 1.0 and delivered["app_error"] is None
    assert len(dropped["misrouted"]) == 30 and dropped["loss"]["routing"] == 1.0 and dropped["no_output"] == 0
    assert report["groups"]["mixed"]["docs"] == 30  # one mixed variant, not counted twice


def test_a_crashing_variant_fails_the_run_but_keeps_the_report_and_all_of_them_stop_it(tmp_path, capsys):
    cmd = stub_app(tmp_path, stress.load_sources(stress.DATA))
    out = tmp_path / "report.json"
    argv = ["--cache", str(tmp_path / "cache"), "--out", str(out), "--cmd", cmd]
    assert stress.main(["--variants", "skew-3", *argv]) == 2  # every variant wrote nothing
    assert "the app wrote no output" in capsys.readouterr().err and not out.exists()
    # a partial extraction fails the run, and the report is still written
    assert stress.main(["--variants", "delivered,skew-3", *argv]) == 1
    assert "30 documents had no output" in capsys.readouterr().err
    variants = json.loads(out.read_text(encoding="utf-8"))["variants"]
    assert variants["delivered"]["micro_f1"] == 1.0 and variants["delivered"]["app_error"] is None
    assert variants["skew-3"]["no_output"] == 30 and "crashed on purpose" in variants["skew-3"]["app_error"]


def test_an_app_that_exits_zero_and_writes_nothing_stops_the_run(tmp_path, capsys):
    out = tmp_path / "report.json"
    cmd = f"{sys.executable} -c pass {{input}} {{output}}"
    argv = ["--variants", "delivered", "--cache", str(tmp_path / "cache"), "--out", str(out), "--cmd", cmd]
    assert stress.main(argv) == 2
    assert "it exited 0" in capsys.readouterr().err and not out.exists()


def test_the_command_line_lists_variants_and_rejects_unknown_ones(capsys):
    assert stress.main(["--list"]) == 0
    assert "skew+3" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        stress.main(["--variants", "skew+9"])
