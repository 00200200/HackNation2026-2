"""Measure the jury CLI on two copies of the 30 scans and 90 native training PDFs."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def make_mix(folder):
    data = Path("data/uzp/dane")
    scans = sorted((data / "skany").rglob("*.pdf"))
    training = sorted(data.glob("przyklad_*/*.pdf"))[:90]
    if len(scans) != 30 or len(training) != 90:
        raise ValueError("Expected 30 scans and 90 training PDFs")
    paths = []
    for group, sources in [("scan1", scans), ("scan2", scans), ("training", training)]:
        for source in sources:
            rel = Path(group) / source.relative_to(data)
            (folder / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, folder / rel)
            paths.append(rel.with_suffix(".json"))
    return paths


def peak_memory(process):
    """Sample summed RSS (working set on Windows) of the CLI and its descendants."""
    if os.name == "nt":
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            'Get-CimInstance Win32_Process | ForEach-Object { "$($_.ProcessId) $($_.ParentProcessId) $($_.WorkingSetSize)" }',
        ]
        scale = 1
    else:
        cmd, scale = ["ps", "-axo", "pid=,ppid=,rss="], 1024
    peak = 0
    while process.poll() is None:
        children = {}
        sizes = {}
        for row in subprocess.check_output(cmd, text=True, timeout=30).splitlines():
            pid, parent, rss = map(int, row.split())
            children.setdefault(parent, []).append(pid)
            sizes[pid] = rss * scale
        pending = [process.pid]
        total = 0
        while pending:
            pid = pending.pop()
            total += sizes.get(pid, 0)
            pending.extend(children.get(pid, []))
        peak = max(peak, total)
        time.sleep(0.5)
    return round(peak / 2**20, 1)


def exact_output(rel, prediction):
    # The cross-platform report comparison runs with only the standard library installed.
    from evals.metrics import load_prediction
    from evals.run import correct_training_accounts

    group, *parts = rel.parts
    gold = Path("data/uzp/dane", *parts)
    source = gold.with_suffix(".pdf")
    if gold.name == "potwierdzenie_przelewu.json":
        gold = gold.with_name("przelew.json")
    raw = gold.read_text(encoding="utf-8-sig") if gold.exists() else ""
    reference = json.loads(raw) if raw else {}
    data, empty_object = load_prediction(prediction)
    if not reference:
        return empty_object
    if group == "training":
        reference = correct_training_accounts(source, reference)
    return data == reference


def measure(inputs, output, expected, flags):
    cmd = [sys.executable, "-u", "-m", "kio2json", "--input", str(inputs), "--output", str(output), *flags]
    start = previous = time.monotonic()
    longest = 0
    with (
        subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, encoding="utf-8") as proc,
        ThreadPoolExecutor(1) as pool,
    ):
        peak = pool.submit(peak_memory, proc)
        for line in proc.stdout:
            if line.rstrip().endswith(".json"):
                now = time.monotonic()
                longest = max(longest, now - previous)
                previous = now
        if proc.wait():
            raise RuntimeError(f"CLI exited with {proc.returncode}")
        wall = time.monotonic() - start
        rss = peak.result()
    if set(output.rglob("*.json")) != {output / rel for rel in expected}:
        raise RuntimeError("Output paths differ from the 150 input paths")
    hashes = {rel.as_posix(): hashlib.sha256((output / rel).read_bytes()).hexdigest() for rel in expected}
    gold_exact = dict.fromkeys(("training", "scan1", "scan2"), 0)
    for rel in expected:
        gold_exact[rel.parts[0]] += int(exact_output(rel, output / rel))
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return {
        "gold_exact": gold_exact,
        "wall_s": round(wall, 2),
        "peak_sampled_tree_mib": rss,
        "max_serial_completion_gap_s": round(longest, 2) if flags else None,
        "sha256": digest,
        "files": hashes,
    }


def compare(folder):
    reports = sorted(folder.glob("*/jury-timing.json"))
    if len(reports) != 3:
        raise ValueError("Expected all three platform reports")
    reference = json.loads(next(folder.glob("*macos*/jury-timing.json")).read_text())["default"]["files"]
    failed = False
    for report in reports:
        data = json.loads(report.read_text())
        for mode in ("default", "serial"):
            result = data[mode]
            differences = [p for p in reference if result["files"].get(p) != reference[p]]
            print(data["platform"], mode, result["wall_s"], result["sha256"], "differences:", differences)
            exact = result["gold_exact"]
            failed |= bool(differences) or result["wall_s"] > 2700
            failed |= exact["training"] != 90 or min(exact["scan1"], exact["scan2"]) < 29
    return int(failed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    if args.compare:
        return compare(args.compare)
    report = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "default_workers": min(4, os.process_cpu_count() or 1),
    }
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        inputs = root / "input"
        expected = make_mix(inputs)
        for mode, flags in [("default", []), ("serial", ["--jobs", "1"])]:
            report[mode] = measure(inputs, root / mode, expected, flags)
    Path("jury-timing.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
