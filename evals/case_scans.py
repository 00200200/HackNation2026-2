"""Render image-only copies of synthetic native PDFs at measured scan settings."""

from contextlib import closing
from io import BytesIO
from pathlib import Path
from random import Random

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont, PdfImagePlugin, PdfParser, features


def _stationery(image: Image.Image, dpi: int, rng: Random, first_page: bool) -> None:
    """Add letterhead rules and a copy stamp only where the native page is blank."""
    width, height = image.size
    draw = ImageDraw.Draw(image)
    ink = rng.choice(((78, 104, 130), (90, 113, 105), (130, 94, 103)))
    line = max(1, round(dpi / 90))
    left, top = round(width * 0.08), round(height * 0.032)
    end = round(width * rng.uniform(0.31, 0.45))
    if image.crop((left, top, end + 1, top + 4 * line + 1)).convert("L").getextrema()[0] >= 245:
        draw.line((left, top, end, top), fill=ink, width=line)
        draw.line((left, top + 3 * line, (left + end) // 2, top + 3 * line), fill=ink, width=line)

    if first_page:
        font = ImageFont.load_default(size=round(10 * dpi / 72))
        stamp_width = round(54 * dpi / 72)
        stamp_height = round(18 * dpi / 72)
        for x_fraction in rng.sample((0.12, 0.5, 0.76), 3):
            x, y = round(width * x_fraction), round(height * 0.94)
            box = (x, y, x + stamp_width, y + stamp_height)
            if box[2] >= width or box[3] >= height or image.crop(box).convert("L").getextrema()[0] < 245:
                continue
            draw.rectangle(box, outline=ink, width=line)
            draw.text((x + stamp_width / 2, y + stamp_height / 2), "KOPIA", fill=ink, font=font, anchor="mm")
            break


def scan_pdf(native: Path, output: Path, *, dpi: int, codec: str, quality: int, angle: float, seed: int) -> None:
    """Rasterize each page with a counterclockwise skew about its center.

    Each page retains its native visible dimensions in points. Quality selects
    the standard JPEG quantization tables for the two JPEG codecs.
    """
    if dpi not in (150, 200, 300):
        raise ValueError("Scan DPI must be 150, 200 or 300")
    if codec not in ("jpeg-rgb", "jpeg-gray", "ccitt"):
        raise ValueError(f"Unknown scan codec {codec!r}")
    if codec != "ccitt" and not 35 <= quality <= 80:
        raise ValueError("JPEG quality must be in the measured range 35–80")
    if codec == "ccitt" and not features.check("libtiff"):
        raise RuntimeError("CCITT Group 4 requires Pillow with libtiff")

    rng = Random(seed)
    with pdfium.PdfDocument(native) as source, BytesIO() as stream:
        with PdfParser.PdfParser(f=stream, mode="w+b") as pdf:
            pdf.start_writing()
            pdf.write_header()
            pdf.pages.extend(pdf.next_object_id(0) for _ in range(len(source)))
            pdf.write_catalog()
            for index in range(len(source)):
                with closing(source[index]) as page, closing(page.render(scale=dpi / 72, rev_byteorder=True)) as bitmap:
                    width, height = page.get_size()
                    image = bitmap.to_pil().convert("RGB")
                _stationery(image, dpi, rng, first_page=index == 0)
                image = image.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor="white")
                if codec == "jpeg-gray":
                    image = image.convert("L")
                elif codec == "ccitt":
                    image = image.convert("L").point(lambda value: 255 if value >= 175 else 0, mode="1")

                # Pillow's image writer implements the DCT and single-strip G4
                # streams. Its high-level PDF save rounds the page to pixel units.
                image.encoderinfo = {} if codec == "ccitt" else {"quality": quality}
                image_ref, _ = PdfImagePlugin._write_image(image, "", pdf)
                contents = pdf.write_obj(None, stream=f"q {width:.8f} 0 0 {height:.8f} 0 0 cm /Scan Do Q\n".encode())
                pdf.write_page(
                    index,
                    Resources=PdfParser.PdfDict(XObject=PdfParser.PdfDict(Scan=image_ref)),
                    MediaBox=[0, 0, width, height],
                    Contents=contents,
                )
            pdf.write_xref_and_trailer()
        output.write_bytes(stream.getvalue())
