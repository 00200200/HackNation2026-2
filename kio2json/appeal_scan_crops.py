"""Verify ambiguous cover-sheet glyphs against their original scanned word boxes."""

import math
import re
from collections.abc import Callable, Iterator
from contextlib import ExitStack, suppress
from functools import cache
from os.path import commonprefix
from pathlib import Path
from statistics import median

import pdfplumber
from PIL import Image
from rapidfuzz.distance import Levenshtein

from .appeal_scan_parties import _fold
from .common import EMAIL_RE
from .ocr_budget import CROP_TIMEOUT_MS, RereadExpired, remaining_ms, require_remaining_ms
from .pdf_text import WordBox, _language_dir

_ReadCrop = Callable[[list[WordBox], str, bool], str]


def _inclination(words: list[WordBox]) -> float:
    slopes = []
    for i, left in enumerate(words):
        for right in words[i + 1 : i + 7]:
            if right.x0 < left.x1:
                break
            dx = (right.x0 + right.x1 - left.x0 - left.x1) / 2
            dy = (right.y0 + right.y1 - left.y0 - left.y1) / 2
            if dx > 65 and abs(dy / dx) < 0.09:
                slopes.append(dy / dx)
    return math.degrees(math.atan(median(slopes))) if len(slopes) >= 3 else 0.0


def _matching_boxes(words: list[WordBox], tokens: list[str]) -> Iterator[list[WordBox]]:
    for i, word in enumerate(words):
        if word.text == tokens[0]:
            span = words[i : i + len(tokens)]
            if [w.text for w in span] == tokens:
                yield span


def _contact(name: str, header: str, words: list[WordBox], read: _ReadCrop) -> str | None:
    # A person's name can locate the right line, but cannot supply their address.
    parts = _fold(name).split()
    if len(parts) < 2:
        return None
    initial, surname = parts[0][0], parts[-1]
    local = initial + "." + surname
    for line in header.splitlines():
        label = re.search(r"\be[- ]?mail\s*:\s*", line, re.IGNORECASE)
        if not label:
            continue
        damaged = re.match(r"([\w. (©®-]+?\.[\w-]+(?:\.[\w-]+)*)\s*$", line[label.end() :].strip())
        if not damaged or not re.match(rf"{re.escape(initial)}[. ]{re.escape(surname)}", damaged[1], re.IGNORECASE):
            continue
        for span in _matching_boxes(words, damaged[1].split()):
            second = read(span, "eng", False).casefold().strip("‘’' ")
            if "@" not in second:
                continue
            mailbox, host = second.split("@", 1)
            if not damaged[1].casefold().endswith(host) or not EMAIL_RE.fullmatch(local + "@" + host):
                continue
            if mailbox == local:
                return local + "@" + host
            # Confirm the dot independently when one segmentation split the mailbox.
            if mailbox.replace(" ", ".") == local and read(span, "pol", True).casefold().startswith(local):
                return local + "@" + host
    return None


def _disputed_counsel(firm: str, words: list[WordBox], read: _ReadCrop) -> bool:
    """Check the printed name when both words following a professional title have weak OCR."""
    if not re.search(r"(?i)\b(?:radca prawny|adwokat)\s+[^\W\d_]+\s+[^\W\d_]+$", firm):
        return False
    spans = list(_matching_boxes(words, firm.split()))
    scores = [getattr(word, "confidence", None) for span in spans for word in span[-2:]]
    if not scores or any(score is None or score >= 55 for score in scores):
        return False

    def letters(name):
        return "".join(char for char in _fold(name) if char.isalpha())

    expected = letters(" ".join(firm.split()[-2:]))
    readings = [letters(read(span[-2:], "pol", False)) for span in spans]
    return all(value and value != expected for value in readings)


def verify_cover(record: dict, page: str, words: list[WordBox], path: Path, *, all_scanned: bool = False) -> None:
    if not words or not remaining_ms(1):
        return
    from tesserocr import PSM, PyTessBaseAPI

    header = re.split(r"(?im)^\W*odwołanie\W*$", page, maxsplit=1)[0]
    with ExitStack() as stack, suppress(RereadExpired):

        @cache
        def raster():
            doc = stack.enter_context(pdfplumber.open(path))
            page = doc.pages[0]
            require_remaining_ms()
            return page.to_image(resolution=360)

        @cache
        def api(language):
            return stack.enter_context(PyTessBaseAPI(path=_language_dir(), lang=language))

        @cache
        def angle():
            return _inclination(words)

        def read(span, language, deskew=False):
            require_remaining_ms()
            frame = raster()
            require_remaining_ms()
            left, top = frame.bbox[:2]
            coords = (
                min(w.x0 for w in span) - left - 1,
                min(w.y0 for w in span) - top - 1,
                max(w.x1 for w in span) - left + 1,
                max(w.y1 for w in span) - top + 1,
            )
            crop = frame.original.crop(tuple(round(x * frame.scale) for x in coords)).convert("L")
            if deskew:
                crop = crop.rotate(angle(), Image.Resampling.BICUBIC, expand=True, fillcolor=255)
            reader = api(language)
            reader.SetPageSegMode(PSM.SINGLE_WORD if deskew or language == "eng" else PSM.SINGLE_LINE)
            reader.SetImage(crop)
            reader.SetSourceResolution(360)
            return (
                reader.GetUTF8Text().strip() if reader.Recognize(timeout=require_remaining_ms(CROP_TIMEOUT_MS)) else ""
            )

        for party in record["Odwolujacy"]:
            counsel = party["pelnomocnik"]
            if not counsel["mail"] and counsel["imie_nazwisko"]:
                counsel["mail"] = _contact(counsel["imie_nazwisko"], header, words, read)
            firm = counsel["nazwa"] or ""
            if all_scanned and _disputed_counsel(firm, words, read):
                counsel["nazwa"] = None
            elif " $ " in firm:
                for span in _matching_boxes(words, firm.split()):
                    symbol = span[firm.split().index("$")]
                    if read([symbol], "eng") == "&":
                        counsel["nazwa"] = firm.replace(" $ ", " & ", 1)
                    break

        for party in record["Zamawiajacy"]:
            name = party["nazwa"]
            town = re.search(r"\bw ([\w-]+)$", name)
            if not town or name not in header:
                continue
            # A postal town printed in the same address block corroborates the root
            # of an inflected institutional name. The replacement must appear in the crop.
            card = header.partition(name)[2].splitlines()[1:4]
            postal = re.search(r"(?m)^\s*\d{2}-\d{3}\s+([\w-]+)", "\n".join(card))
            if not postal or len(commonprefix([town[1], postal[1]])) < 3 or town[1] == postal[1]:
                continue
            for span in _matching_boxes(words, name.split()):
                candidate = read(span[-1:], "pol")
                if (
                    candidate.isalpha()
                    and Levenshtein.distance(town[1], candidate) == 1
                    and len(commonprefix([candidate, postal[1]])) > len(commonprefix([town[1], postal[1]]))
                ):
                    party["nazwa"] = name[: town.start(1)] + candidate
                break

        procurement = record["ZamowieniePubliczne"]
        value = procurement["numer_postepowania"]
        if value and re.match(r"[0258][A-Z]+[./-]", value):
            for word in words:
                if word.text.rstrip(",;:.") != value:
                    continue
                english, polish = (read([word], lang).rstrip(",;:.") for lang in ("eng", "pol"))
                if english == polish and re.fullmatch(r"[A-Z]", english[:1]) and value[1:] == english[1:]:
                    procurement["numer_postepowania"] = english
                break
