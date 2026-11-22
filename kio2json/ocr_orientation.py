"""Find a cardinal rotation from the rendered pixels before full-resolution OCR."""

import os
from functools import cache
from itertools import groupby
from pathlib import Path
from shutil import which

from PIL import Image

from .ocr_budget import remaining_ms


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


def _line_bands(mask: Image.Image) -> tuple[int, list[tuple[int, int]]]:
    """Count distinct text-height ink bands and retain their locations."""
    profile = mask.resize((1, mask.height), Image.Resampling.BOX).tobytes()
    spans = []
    for present, rows in groupby(enumerate(profile), key=lambda entry: entry[1] >= 5):
        if present:
            group = list(rows)
            start, end = group[0][0], group[-1][0] + 1
            if 4 <= end - start <= 120:
                spans.append((start, end))
    # Characters on a line share many inked rows. Vertical gaps between words
    # also form bands, but usually have a much smaller mean ink density.
    density = sum(sum(profile[start:end]) for start, end in spans)
    return density, spans


def _sample_score(api, sample: Image.Image, reread: bool) -> int:
    timeout = remaining_ms(1200) if reread else 1200
    if not timeout:
        return 0
    api.SetImage(sample)
    api.SetSourceResolution(150)
    if not api.Recognize(timeout=timeout):
        return 0
    words = api.GetUTF8Text().split()
    return sum(
        len(word)
        for word, confidence in zip(words, api.AllWordConfidences())
        if confidence >= 75 and sum(c.isalpha() for c in word) >= 3
    )


def correction_angle(image: Image.Image, language_dir: str, *, reread: bool = False) -> int:
    """Counterclockwise correction. Ambiguous or sparse images keep their orientation."""
    from tesserocr import PSM, PyTessBaseAPI

    if min(image.size) < 120 or (reread and remaining_ms(2500) < 2500):
        return 0
    scale = min(1, 1600 / max(image.size))
    size = tuple(max(1, round(n * scale)) for n in image.size)
    preview = image.resize(size, Image.Resampling.BOX).convert("L")
    # Scanner borders can otherwise connect many unrelated lines.
    w, h = preview.size
    preview = preview.crop((w // 32, h // 32, w - w // 32, h - h // 32))
    mask = preview.point(lambda x: 255 if x < 150 else 0)
    bounds = mask.getbbox()
    if bounds is None or min(bounds[2] - bounds[0], bounds[3] - bounds[1]) < 85:
        return 0
    horizontal = _line_bands(mask)
    vertical = _line_bands(mask.transpose(Image.Transpose.ROTATE_90))
    sideways = vertical[0] > horizontal[0]
    _, spans = vertical if sideways else horizontal
    if len(spans) < 3:
        return 0

    angle = 90 if sideways else 0
    if sideways:
        preview = preview.transpose(Image.Transpose.ROTATE_90)
    # Tesseract only needs a few text lines. A complete page of fine print
    # adds latency and provides little additional orientation evidence.
    count = min(7, len(spans))
    start, end = min(
        ((a[0], b[1]) for a, b in zip(spans, spans[count - 1 :])),
        key=lambda pair: pair[1] - pair[0],
    )
    if directory := _osd_directory():
        try:
            with PyTessBaseAPI(path=str(directory), lang="osd", psm=PSM.OSD_ONLY) as osd:
                osd.SetImage(preview.crop((0, max(0, start - 3), preview.width, min(preview.height, end + 3))))
                osd.SetSourceResolution(150)
                result = osd.DetectOrientationScript()
            if result and result["orient_conf"] >= 5:
                return (result["orient_deg"] + angle) % 360
        except RuntimeError:
            # A separately installed OSD model may be incompatible with the wheel.
            pass

    # Compare a single complete line in each direction with the bundled Polish
    # model when the OSD language data is missing or the result is uncertain.
    profile = preview.resize((1, preview.height), Image.Resampling.BOX).tobytes()
    # The densest band can be a logo or several touching rows in a noisy scan.
    # Prefer bands the height of a single line of body text in this thumbnail.
    body = [(a, b) for a, b in spans if 7 <= b - a <= 40]
    start, end = max(
        body or spans, key=lambda span: sum(255 - x for x in profile[span[0] : span[1]]) / (span[1] - span[0])
    )
    sample = preview.crop((0, max(0, start - 3), preview.width, min(preview.height, end + 3)))
    with PyTessBaseAPI(path=language_dir, lang="pol", psm=PSM.SINGLE_LINE) as api:
        first = _sample_score(api, sample, reread)
        if angle == 0 and first >= 24:
            return angle
        second = _sample_score(api, sample.transpose(Image.Transpose.ROTATE_180), reread)
    if max(first, second) < 8 or abs(first - second) < 5:
        return 0
    return angle if first > second else angle + 180


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
