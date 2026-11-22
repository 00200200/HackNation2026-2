"""Render Polish text PDFs and deterministic image-only scans for the layout evaluation."""

import io
import math
import os
from unittest.mock import patch

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import _glyphlist, pdfmetrics
from reportlab.pdfgen.canvas import Canvas

FACES = ("Helvetica", "Times-Roman", "Courier")


def polish_font(face):
    name = f"{face}-PL"
    if name not in pdfmetrics.getRegisteredFontNames():
        # PDF core fonts have Polish glyphs but their default WinAnsi encoding does not.
        glyphs = {code: name for name, code in _glyphlist._glyphname2unicode.items()}
        encoding = pdfmetrics.Encoding("cp1250")
        for byte in range(128, 256):
            try:
                encoding[byte] = glyphs[ord(bytes([byte]).decode("cp1250"))]
            except (UnicodeError, KeyError):
                continue
        pdfmetrics.registerEncoding(encoding)
        pdfmetrics.registerFont(pdfmetrics.Font(name, face, "cp1250"))
    return name


@patch.dict(os.environ, {"SOURCE_DATE_EPOCH": ""})  # Use ReportLab’s invariant timestamp even in CI builds.
def render(title, sections, profile, rng):
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=A4, invariant=1)
    page_width, page_height = A4
    font = polish_font(rng.choice(FACES))
    size = rng.choice((10, 11, 12))
    margin = rng.randint(32, 48)
    leading = size + rng.randint(2, 5)
    canvas.setFont(font, 16)
    canvas.drawString(margin, page_height - margin, title)
    columns = 2 if profile == "two-column" else 1
    width = (page_width - 2 * margin - (columns - 1) * 18) / columns
    top = page_height - margin - 34
    for col in range(columns):
        start = math.ceil(len(sections) * col / columns)
        end = math.ceil(len(sections) * (col + 1) / columns)
        x, y = margin + col * (width + 18), top
        canvas.setFont(font, size)
        for section in sections[start:end]:
            for paragraph in section:
                words = paragraph.split()
                line = ""
                lines = []
                for word in words:
                    if line and pdfmetrics.stringWidth(f"{line} {word}", font, size) > width:
                        lines.append(line)
                        line = ""
                    line = (line + " " + word).strip()
                lines.append(line)
                for line in lines:
                    if y < margin:
                        canvas.showPage()
                        canvas.setFont(font, size)
                        y = top
                    canvas.drawString(x, y, line)
                    y -= leading
            y -= leading / 2
    canvas.save()
    if profile != "scan":
        return buffer.getvalue()

    output = io.BytesIO()
    scan = Canvas(output, pagesize=A4, invariant=1)
    noise = np.random.default_rng(rng.getrandbits(64))
    dpi = rng.choice((150, 180, 220, 300))
    with pdfium.PdfDocument(buffer.getvalue()) as doc:
        for page in doc:
            bitmap = page.render(scale=dpi / 72)
            gray = bitmap.to_pil().convert("L")
            bitmap.close()
            page.close()
            gray = gray.rotate(rng.uniform(-1.4, 1.4), fillcolor=255).filter(ImageFilter.GaussianBlur(0.45))
            pixels = np.asarray(gray).astype(np.int16) + noise.integers(-12, 13, gray.size[::-1], dtype=np.int16)

            jpeg = io.BytesIO()
            Image.fromarray(pixels.clip(0, 255).astype("uint8")).save(jpeg, "JPEG", quality=rng.randrange(45, 76))
            scan.drawImage(ImageReader(jpeg), 0, 0, *A4)
            scan.showPage()
    scan.save()
    return output.getvalue()
