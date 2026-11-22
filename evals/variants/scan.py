"""Stand-in scans: rasterise a generated PDF, skew and degrade it, and wrap the pages in an image-only PDF."""

import io
import random
import time
from dataclasses import dataclass

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFilter

from evals.variants.vocab import Pick

DPI = [("150", 150), ("200", 200), ("300", 300)]
SKEW = [("0", 0.0), ("0.5", 0.5), ("-0.5", -0.5), ("1", 1.0), ("-1", -1.0), ("2", 2.0), ("-2", -2.0)]
NOISE = [("0", 0), ("6", 6), ("12", 12), ("20", 20)]
BLUR = [("0", 0.0), ("0.6", 0.6), ("1", 1.0)]
PAD = [("none", 0), ("small", 30), ("large", 90)]
MODES = ["rgb", "bw", "gray"]  # the organizer's 30 sample scans: 15 colour JPEG, 9 one-bit CCITT, 6 grey JPEG
PAPER = [("255", 255), ("245", 245), ("235", 235), ("228", 228)]  # their paper background runs from 228 to 255
TINT = [("none", (1.0, 1.0, 1.0)), ("warm", (1.0, 0.99, 0.94))]
QUALITY = [("85", 85), ("70", 70), ("55", 55)]
EPOCH = time.gmtime(0)


@dataclass(frozen=True)
class Degradation:
    """How one scanner run treats every page of a document."""

    dpi: int
    angle: float
    sigma: int
    blur: float
    pad: int
    specks: bool
    edge: bool
    paper: int  # background level of the page, 255 is pure white
    tint: tuple[float, float, float] | None  # set for colour output
    threshold: int | None  # set for 1-bit output

    def apply(self, page: Image.Image, rng: random.Random, np_rng: np.random.Generator) -> Image.Image:
        scale = self.dpi / 150
        if self.pad:  # a different canvas: extra white at the bottom and right, as from another scanner
            pad = round(self.pad * scale)
            canvas = Image.new("L", (page.width + pad, page.height + 2 * pad), 255)
            canvas.paste(page, (0, 0))
            page = canvas
        if self.angle:
            page = page.rotate(self.angle, resample=Image.Resampling.BICUBIC, fillcolor=255)
        if self.blur:
            page = page.filter(ImageFilter.GaussianBlur(self.blur * scale))
        if self.sigma:
            noise = np_rng.normal(0, self.sigma, (page.height, page.width))
            page = Image.fromarray(np.clip(np.asarray(page, dtype=np.float32) + noise, 0, 255).astype(np.uint8))
        draw = ImageDraw.Draw(page)
        if self.specks:
            for _ in range(rng.randint(10, 60)):
                x, y, r = rng.randrange(page.width), rng.randrange(page.height), rng.randint(1, 3) * scale
                draw.ellipse((x - r, y - r, x + r, y + r), fill=rng.randint(0, 90))
        if self.edge:
            width = round(rng.randint(6, 25) * scale)
            box = (0, 0, width, page.height) if rng.random() < 0.5 else (page.width - width, 0, page.width, page.height)
            draw.rectangle(box, fill=40)
        if self.threshold is not None:
            return page.point(lambda v: 255 if v > self.threshold else 0).convert("1")
        page = page.point(lambda v: v * self.paper // 255)
        if self.tint:
            return Image.merge("RGB", [page.point(lambda v, k=k: round(v * k)) for k in self.tint])
        return page


def scan(pdf: bytes, rng: random.Random) -> tuple[bytes, dict[str, str]]:
    """Return an image-only PDF of the same pages and the tags of the degradations applied."""
    pick = Pick(rng)
    mode = pick("scan_mode", MODES, [5, 3, 2])
    degradation = Degradation(
        dpi=pick("scan_dpi", DPI, [2, 3, 2]),
        angle=pick("scan_skew", SKEW, [3, 1, 1, 1, 1, 1, 1]),
        sigma=pick("scan_noise", NOISE, [3, 3, 2, 1]),
        blur=pick("scan_blur", BLUR, [3, 2, 1]),
        pad=pick("scan_pad", PAD, [4, 2, 1]),
        specks=pick.chance("scan_specks", 0.4),
        edge=pick.chance("scan_edge", 0.25),
        paper=pick("scan_paper", PAPER, [2, 3, 3, 1]) if mode != "bw" else 255,
        tint=pick("scan_tint", TINT, [3, 1]) if mode == "rgb" else None,
        threshold=pick("scan_threshold", [("150", 150), ("180", 180)]) if mode == "bw" else None,
    )
    np_rng = np.random.default_rng(rng.randrange(2**32))
    pages = [
        degradation.apply(source.render(scale=degradation.dpi / 72).to_pil().convert("L"), rng, np_rng)
        for source in pdfium.PdfDocument(pdf)
    ]
    options = {"quality": pick("scan_quality", QUALITY, [3, 2, 1])} if mode != "bw" else {}  # JPEG pages only
    out = io.BytesIO()
    pages[0].save(
        out,
        "PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=float(degradation.dpi),
        creationDate=EPOCH,  # Pillow stamps the current time otherwise, and the same seed must give the same bytes
        modDate=EPOCH,
        **options,
    )
    return out.getvalue(), pick.tags
