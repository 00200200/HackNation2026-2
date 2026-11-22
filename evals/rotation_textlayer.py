"""Score organizer-derived image orientation and misleading text layers with the keyless CLI.

All PDFs and predictions live in a temporary directory. The report contains only aggregates
and a digest of the generated PDFs and organizer gold, for paired runs across checkouts.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from contextlib import closing
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from evals.cases import exact_json
from evals.document_variants.pdfkit import register_fonts
from evals.metrics import Counts, compare, doc_class, load_prediction, load_reference
from evals.run import DATA, ROOT, TIMEOUT_S, correct_training_accounts

NATIVE = (
    "przyklad_02/odwolanie.pdf",
    "przyklad_01/pelnomocnictwo.pdf",
    "przyklad_01/przelew.pdf",
)
SCANS = tuple(f"skany/{group}/0001/0001.pdf" for group in ("odwolania", "pelnomocnictwa", "potwierdzenia"))
ORIENTATIONS = ("upright", "pixel_90", "pixel_180", "pixel_270", "pdf_rotate_90")
DAMAGED = {"odwolanie": ("first_marker",), "pelnomocnictwo": ("nip_digit",), "przelew": ("account_digit", "shift_line")}
ACCOUNT = re.compile(r"(?:[A-Z]{2})?\d{26}")


def damaged_words(words, defect):
    """Alter precisely one field or move the sender's value row just below the recipient's."""
    result = [word.copy() for word in words]
    if defect in ("account_digit", "shift_line"):
        sender, recipient = [word for word in result if ACCOUNT.fullmatch(word["text"])]
        if defect == "account_digit":
            sender["text"] = sender["text"][:-1]
        else:
            offset = recipient["bottom"] - sender["top"] + 1
            for word in result:
                if abs(word["top"] - sender["top"]) < 1:
                    word["bottom"] += offset
    elif defect == "nip_digit":
        index = next(i for i, word in enumerate(result) if word["text"].rstrip(":") == "NIP")
        word = result[index + 1]
        word["text"], n = re.subn(r"^(\d{9})\d(?!\d)", r"\1", word["text"])
        if n != 1:
            raise ValueError("expected a ten-digit NIP on the selected mandate")
    elif defect == "first_marker":
        word = next(word for word in result if word["text"] == "1.1.")
        word["text"] = "2.1."
    return result


def draw_layer(canvas, words, height):
    # Keep each word at its source baseline and fit it to its printed width. Mode 3 is invisible.
    for word in words:
        text, size = word["text"], word["size"]
        face = "DejaVuSans-Bold" if "bold" in word["fontname"].lower() else "DejaVuSans"
        block = canvas.beginText(word["x0"], height - word["bottom"] + size * 0.2)
        block.setFont(face, size)
        block.setTextRenderMode(3)
        block.setHorizScale(100 * (word["x1"] - word["x0"]) / pdfmetrics.stringWidth(text, face, size))
        # PDF text extractors can merge adjacent objects across a narrow visual word gap.
        block.textOut(text + " ")
        canvas.drawText(block)


def render(source, output, variant, layers):
    canvas = Canvas(str(output), invariant=1, pageCompression=1)
    if variant == "pdf_rotate_90":
        canvas.setPageRotation(90)
    else:
        # ReportLab normally emits an explicit /Rotate 0. Untagged images exercise a distinct input.
        canvas._pageRotation = None
    with pdfium.PdfDocument(source) as pdf:
        for i in range(len(pdf)):
            with closing(pdf[i]) as page, closing(page.render(scale=200 / 72)) as bitmap:
                image = bitmap.to_pil().convert("L")
                width, height = page.get_size()
            angle = 90 if variant == "mixed_first_90" and i == 0 else 0
            if variant.startswith("pixel_"):
                angle = int(variant.removeprefix("pixel_"))
            if angle:
                image = image.transpose(getattr(Image.Transpose, f"ROTATE_{angle}"))
                if angle != 180:
                    width, height = height, width
            # ReportLab swaps media-box dimensions when /Rotate is a quarter turn.
            canvas.setPageSize((height, width) if variant == "pdf_rotate_90" else (width, height))
            canvas.drawImage(ImageReader(image), 0, 0, width, height)
            if variant.startswith("layer_"):
                words = damaged_words(layers[i], variant.removeprefix("layer_")) if i == 0 else layers[i]
                draw_layer(canvas, words, height)
            canvas.showPage()
    canvas.save()


def stage(folder):
    register_fonts()
    manifest = []
    digest = hashlib.sha256()
    for relative in (*NATIVE, *SCANS):
        source = DATA / relative
        gold = load_reference(source.with_suffix(".json"))
        variants = list(ORIENTATIONS)
        if doc_class(gold) == "odwolanie":
            variants.append("mixed_first_90")
        layers = []
        if relative in NATIVE:
            # The public training gold omits country prefixes even where the transfer prints them.
            gold = correct_training_accounts(source, gold)
            with pdfplumber.open(source) as pdf:
                layers = [p.extract_words(extra_attrs=["size", "fontname"]) for p in pdf.pages]
            variants.extend(["layer_faithful", *(f"layer_{d}" for d in DAMAGED[source.stem])])
        for variant in variants:
            name = Path(f"case_{len(manifest) + 1:04d}", "document.pdf")
            target = folder / name
            target.parent.mkdir(parents=True)
            render(source, target, variant, layers)
            digest.update(hashlib.sha256(target.read_bytes()).digest())
            digest.update(hashlib.sha256(json.dumps(gold, sort_keys=True).encode()).digest())
            manifest.append((name, variant, gold))
    return manifest, digest.hexdigest()


def evaluate(root, manifest, fingerprint, extractor):
    inputs, outputs = root / "input", root / "output"
    env = {k: v for k, v in os.environ.items() if not k.startswith("KIO_")}
    env.update(KIO_LLM_BASE_URL="", KIO_LLM_MODEL="", KIO_LLM_API_KEY="", PYTHONPATH=str(extractor))
    start = time.monotonic()
    process = subprocess.run(
        [sys.executable, "-m", "kio2json", "--jobs", "2", "--input", str(inputs), "--output", str(outputs)],
        cwd=extractor,
        env=env,
        check=False,
        stdout=subprocess.DEVNULL,
        timeout=TIMEOUT_S,
    )
    elapsed = time.monotonic() - start
    rows = defaultdict(list)
    for name, variant, gold in manifest:
        pred, _ = load_prediction((outputs / name).with_suffix(".json"))
        rows[variant].append((pred, gold))
    scores = {}
    for variant, pairs in rows.items():
        counts = Counts()
        for pred, gold in pairs:
            counts.add(compare(pred, gold))
        scores[variant] = {
            "docs": len(pairs),
            "valid_outputs": sum(pred is not None for pred, _ in pairs),
            "uzp_f1": counts.f1,
            "exact": sum(exact_json(pred, gold) for pred, gold in pairs),
            "routed": sum(doc_class(pred) == doc_class(gold) for pred, gold in pairs),
        }
    return {
        "dataset_sha256": fingerprint,
        "docs": len(manifest),
        "seconds": elapsed,
        "cli_exit": process.returncode,
        "per_variant": scores,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / ".cache/rotation-textlayer.json")
    parser.add_argument("--extractor-root", type=Path, default=ROOT, help="checkout to run for paired comparisons")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="hn-rotation-") as root:
        folder = Path(root)
        manifest, fingerprint = stage(folder / "input")
        report = evaluate(folder, manifest, fingerprint, args.extractor_root.resolve())
    payload = json.dumps(report, indent=2) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return int(
        report["cli_exit"] != 0 or any(row["docs"] != row["valid_outputs"] for row in report["per_variant"].values())
    )


if __name__ == "__main__":
    sys.exit(main())
