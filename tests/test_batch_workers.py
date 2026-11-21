import os
import subprocess
import sys
from pathlib import Path

from snapshots.generate_native import write_native_pdf


def test_parallel_cli_preserves_outputs_and_failure_status(tmp_path, monkeypatch):
    monkeypatch.setenv("KIO_LLM_API_KEY", "")
    inputs = tmp_path / "input"
    (inputs / "a").mkdir(parents=True)
    (inputs / "b").mkdir()
    write_native_pdf(inputs / "a" / "document.pdf", ["POTWIERDZENIE PRZELEWU", "Kwota: 1500 PLN"])
    (inputs / "b" / "document.pdf").write_bytes(b"not a PDF")
    results = []
    for workers in (1, 2):
        target = tmp_path / f"output-{workers}"
        cmd = [
            sys.executable,
            "-m",
            "kio2json",
            "--input",
            str(inputs),
            "--output",
            str(target),
            "--jobs",
            str(workers),
        ]
        run = subprocess.run(cmd, capture_output=True, timeout=90, check=False)
        assert run.returncode == 1, run.stderr
        results.append({p.relative_to(target): p.read_bytes() for p in target.rglob("*.json")})
    assert results[0] == results[1]
    assert results[0][Path("b/document.json")] == b"{}" + os.linesep.encode()
    assert Path("a/document.json") in results[0]
