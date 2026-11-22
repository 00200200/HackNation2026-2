"""Verify a cardinal rotation against the original displayed pixels and the primary OCR text."""

import os
import re
from functools import cache
from pathlib import Path
from shutil import which

from PIL import Image


@cache
def _osd_directory() -> Path | None:
    """The wheel and the system Tesseract executable can use different default paths."""
    candidates = []
    if prefix := os.getenv("TESSDATA_PREFIX"):
        candidates.append(Path(prefix))
    shares = [Path("/usr/share"), Path("/usr/local/share")]
    if binary := which("tesseract"):
        folder = Path(binary).parent
        candidates.append(folder / "tessdata")  # Windows distributions
        shares.insert(0, folder.parent / "share")
    for share in shares:
        candidates.extend((share / "tessdata", *sorted((share / "tesseract-ocr").glob("*/tessdata"), reverse=True)))
    return next((path for path in candidates if (path / "osd.traineddata").is_file()), None)


def correction_angle(image: Image.Image, dpi: int) -> int:
    """Ask OSD about the displayed raster, preserving its original axes and pixels."""
    from tesserocr import PSM, PyTessBaseAPI

    directory = _osd_directory()
    if directory is None or image.width * image.height > 12_000_000 or min(image.size) < 120:
        return 0
    # Skip blank pages and very sparse strips. Only this inexpensive ink check
    # sees a thumbnail. OSD always sees the complete original displayed image.
    scale = min(1, 320 / max(image.size))
    small = image.resize(tuple(max(1, round(n * scale)) for n in image.size), Image.Resampling.BOX).convert("L")
    ink = small.point(lambda x: 255 if x < 180 else 0).getbbox()
    if not ink or min(ink[2] - ink[0], ink[3] - ink[1]) < 18:
        return 0
    try:
        with PyTessBaseAPI(path=str(directory), lang="osd", psm=PSM.OSD_ONLY) as api:
            api.SetImage(image)
            api.SetSourceResolution(dpi)
            result = api.DetectOrientationScript()
    except (OSError, RuntimeError, ValueError):
        return 0
    if result and result["orient_conf"] >= 15 and result["orient_deg"] in (90, 180, 270):
        return result["orient_deg"]
    return 0


def rotation_improves_text(upright: str, candidate: str) -> bool:
    """Require at least four more distinct Polish words and a 50% gain."""
    from .appeal_scan_procurement import _polish_dictionary

    # Limit dictionary lookups on long OCR transcripts. Use whole lexical words
    # so that punctuation, lone initials and fragments inside identifiers cannot vote.
    def vocabulary(text):
        return set(re.findall(r"\b[^\W\d_]{3,40}\b", text[:16_000].casefold()))

    before, after = vocabulary(upright), vocabulary(candidate)
    if len(after - before) < 4:
        return False
    with _polish_dictionary() as valid:
        if valid is None:
            return False
        printed = {word for word in before | after if valid(word)}
    original = len(before & printed)
    improved = len(after & printed)
    return improved >= original + 4 and 2 * improved >= 3 * original


def source_box(box, size, angle):
    """Map upright OCR pixel edges back to the rendered PDF image."""
    x0, y0, x1, y1 = box
    width, height = size
    if angle == 90:
        return height - y1, x0, height - y0, x1
    if angle == 180:
        return width - x1, height - y1, width - x0, height - y0
    if angle == 270:
        return y0, width - x1, y1, width - x0
    return box
