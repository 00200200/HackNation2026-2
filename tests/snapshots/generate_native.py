"""Record class and canonical fields from the pinned integration base (see README.md)."""

import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from kio2json.pipeline import process_pdf

BASE = "32106434f746628c7080191597f0766d4151d786"
CASES = Path(__file__).with_name("native_cases.json")


def write_native_pdf(path, pages):
    """Write selectable Polish text using a standard PDF font and a Central European encoding."""
    encoding = (
        "/Encoding << /BaseEncoding /WinAnsiEncoding /Differences "
        "[140 /Sacute 143 /Zacute 156 /sacute 159 /zacute 163 /Lslash 165 /Aogonek "
        "175 /Zdotaccent 179 /lslash 185 /aogonek 191 /zdotaccent 198 /Cacute 202 /Eogonek "
        "209 /Nacute 230 /cacute 234 /eogonek 241 /nacute] >>"
    )
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>",
        f"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica {encoding} >>",
    ]
    for text in pages:
        content_id = len(objects) + 2
        objects.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1600 800] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        )
        lines = [f"<{line.encode('cp1250').hex()}> Tj" for line in text.splitlines()]
        stream = "BT /F1 10 Tf 20 770 Td 14 TL " + " T* ".join(lines) + " ET"
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    data = bytearray(b"%PDF-1.4\n")
    offsets = ["0000000000 65535 f "]
    for index, obj in enumerate(objects, start=1):
        offsets.append(f"{len(data):010d} 00000 n ")
        data.extend(f"{index} 0 obj\n{obj}\nendobj\n".encode("ascii"))
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    data.extend("\n".join(offsets).encode("ascii"))
    data.extend(f"\ntrailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    path.write_bytes(data)


def main():
    checkout = Path.cwd()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if revision != BASE or Path(process_pdf.__code__.co_filename).resolve().parent.parent != checkout:
        raise SystemExit("Run in the pinned base worktree with PYTHONPATH set to its root.")
    os.environ.pop("KIO_CLASSES_DIR", None)
    outputs = {}
    with (
        TemporaryDirectory() as tmp,
        patch("kio2json.pdf_text._ocr", side_effect=AssertionError("Expected native text")),
    ):
        path = Path(tmp) / "document.pdf"
        for name, pages in json.loads(CASES.read_text(encoding="utf-8")).items():
            write_native_pdf(path, pages)
            outputs[name] = process_pdf(path)
    print(json.dumps({"base": revision, "outputs": outputs}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
