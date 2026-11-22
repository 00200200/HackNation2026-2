"""Recover procurement fields from the labelled portions of OCR appeal pages."""

import ctypes
import re
from collections import Counter
from collections.abc import Collection
from contextlib import contextmanager
from importlib.metadata import files
from itertools import groupby

from .appeal import _procurement
from .common import squash
from .pdf_text import _language_dir

_TED = re.compile(r"\b(20\d\d)\s*/\s*[S5$8]{1,2}\s*(\d{3})\s*[-–—]\s*(\d{6})(?!\d)", re.IGNORECASE)
_BZP = re.compile(r"\b(20\d\d)\s*/\s*[B8][Z2]P\s*(\d{8})(?:\s*/\s*(\d{2}))?(?!\d)", re.IGNORECASE)
_NOTICE = re.compile(r"og[łl]oszeni|dziennik[ua]?\s+urz[ęe]d|\bted\b|\bdz\.?\s*u\.", re.IGNORECASE)
_REFERENCE_LABEL = re.compile(
    r"\b(?:(?:nr|numer)\s+(?:referencyjny(?:\s+sprawy)?|post[ęe]powania|zam[oó]wienia|sprawy)"
    r"|znak\s+sprawy)\s*:?\s*",
    re.IGNORECASE,
)
_REFERENCE_VALUE = re.compile(r"[A-Z\d]+(?:[ \t]*[./-][ \t]*[A-Z\d]+)+(?!\w)")
_TITLE_MARK = re.compile(
    r'\b(?:pn\.|pod\s+nazw[ąa]|przedmiotem\s+jest)\s*[:.]?\s*(?:[„“"«]|,,|\.\.)\s*',
    re.IGNORECASE,
)
_END_QUOTE = re.compile(r'[”"»](?=\s*[,;.()\n]|\s+(?:[-–—]|znak\b|nr\b|numer\b|dalej\b)|\s*$)', re.IGNORECASE)
_PLAIN_TITLE = re.compile(
    r"\bpost[ęe]powaniu\s+na:\s*|^[^\w\n]{0,4}dotyczy\s*:\s*"
    r"|\b(?:okre[śs]lenie\s+)?przedmiotu?\s+zam[oó]wienia:\s*"
    r"|(?P<complement>\bna\s+zadanie:\s*(?:na\s+)?|\bprzetargu\s+nieograniczonego\s+na:\s*)",
    re.IGNORECASE | re.MULTILINE,
)
_TITLE_END = re.compile(
    r"\s*[,;(]?\s*(?:\b(?:nr|numer)\s+(?:og[łl]oszenia|referencyjny|sprawy|post[ęe]powania)"
    r"|\bznak\s+sprawy|\bog[łl]oszonym\s+w\s+dniu)\b",
    re.IGNORECASE,
)
_LETTERS = re.compile(r"\b[^\W\d_]{5,}\b")
_ACCENTS = dict(zip("ąćęłńóśźż", "acelnoszz", strict=True))


@contextmanager
def _polish_dictionary():
    """Use the word dictionary in the Polish traineddata already installed for OCR."""
    from tesserocr import PyTessBaseAPI, tesserocr

    if hasattr(PyTessBaseAPI, "IsValidWord"):
        with PyTessBaseAPI(path=_language_dir(), lang="pol") as api:
            yield api.IsValidWord
        return

    # The pinned wheels omit the Python binding. The Windows .pyd exports
    # PyInit_tesserocr only; its adjacent, wheel-owned DLL exports the C API.
    bundled = next(
        (
            entry.locate().resolve()
            for entry in files("tesserocr") or ()
            if entry.match("tesserocr.libs/tesseract[0-9]*.dll")
            or entry.match("tesserocr.libs/libtesseract-*.so.*")
            or entry.match("tesserocr/.dylibs/libtesseract.*.dylib")
        ),
        tesserocr.__file__,
    )
    try:
        lib = ctypes.CDLL(str(bundled))
        create, init, lookup, delete = (
            lib.TessBaseAPICreate,
            lib.TessBaseAPIInit3,
            lib.TessBaseAPIIsValidWord,
            lib.TessBaseAPIDelete,
        )
    except (AttributeError, OSError):
        yield None
        return
    create.argtypes = []
    create.restype = ctypes.c_void_p
    init.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
    lookup.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    delete.argtypes = [ctypes.c_void_p]
    delete.restype = None
    api = create()
    try:
        if api and init(api, _language_dir().encode(), b"pol") == 0:
            yield lambda word: bool(lookup(api, word.encode()))
        else:
            yield None
    finally:
        if api:
            delete(api)


def _repair_accents(title: str, text: str) -> str:
    if not any(c in _ACCENTS for c in title.lower()):
        return title
    other_words = Counter(word.lower() for word in _LETTERS.findall(text))
    with _polish_dictionary() as valid:
        if valid is None:
            return title

        def replace(match):
            word = match[0]
            lower = word.lower()
            if not any(c in _ACCENTS for c in lower) or valid(lower):
                return word
            candidates = {lower[:i] + _ACCENTS[c] + lower[i + 1 :] for i, c in enumerate(lower) if c in _ACCENTS}
            accepted = [candidate for candidate in candidates if valid(candidate)]
            if len(accepted) == 1:
                candidate = accepted[0]
                if word.islower():
                    return candidate
                if word.istitle() and other_words[candidate] > other_words[lower]:
                    return candidate.capitalize()
            return word

        return _LETTERS.sub(replace, title)


def _title(page: str) -> str | None:
    candidates = []
    for m in _TITLE_MARK.finditer(page):
        tail = page[m.end() : m.end() + 720]
        if (end := _END_QUOTE.search(tail)) and not _TITLE_END.search(tail[: end.start()]):
            candidates.append((m.start(), squash(tail[: end.start()])))
    for m in _PLAIN_TITLE.finditer(page):
        tail = page[m.end() : m.end() + 720]
        if end := _TITLE_END.search(tail):
            span = tail[: end.start()]
            if span.count("\n") > 7:
                continue
            value = squash(span).strip(" ,;")
            if value.endswith(("”", '"')) and not any(q in value[:-1] for q in '„“"'):
                value = value[:-1].strip()
            # A task described as "na dostawę ..." takes the accusative after the
            # preposition. A standalone title uses the nominative ("Dostawa ...").
            if m["complement"] and (noun := re.match(r"([a-ząćęłńóśźż]+)ę\b", value)):
                value = noun[1].capitalize() + "a" + value[noun.end() :]
            # The narrow upright glyph before an administrative unit is an ordinal.
            value = re.sub(r"(?<=\s)\|\s+(?=(?:Klinik|Wydział|Oddział|Instytut|Liceum)\w*\b)", "I ", value)
            if value[:1].isupper() and not re.match(
                r"(?:post[ęe]powani|zamawiaj[ąa]cy\b|odwo[łl]uj[ąa]cy\b)", value, re.IGNORECASE
            ):
                candidates.append((m.start(), value))
    return next((value for _, value in sorted(candidates) if len(value.split()) >= 2), None)


def _notice(pattern: re.Pattern, text: str) -> re.Match | None:
    return next(
        (m for m in pattern.finditer(text) if _NOTICE.search(text[max(0, m.start() - 160) : m.start()])),
        None,
    )


def apply_procurement(record: dict, pages: list[str], ocr_pages: Collection[int]) -> None:
    """Use procurement evidence only from OCR pages, preserving native field readings."""
    if not ocr_pages:
        return
    fields = record["ZamowieniePubliczne"]
    protected = set()
    scanned = []
    has_native = False
    for is_ocr, group in groupby(enumerate(pages, 1), key=lambda item: item[0] in ocr_pages):
        text = "\n".join(page for _, page in group)
        if is_ocr:
            scanned.append(text)
        else:
            has_native = True
            protected.update(k for k, v in _procurement(text).items() if v is not None)

    if has_native:
        # A value can begin on a native page and end on a scanned page. Only
        # replace existing fields that the base rules can also read from OCR alone.
        origins = [_procurement(text) for text in scanned]
        protected.update(k for k, v in fields.items() if v and not any(origin[k] == v for origin in origins))

    for text in scanned:
        if "numer_bzp" not in protected and (bzp := _notice(_BZP, text)):
            number = f"{bzp[1]}/BZP{bzp[2]}" + (f"/{bzp[3]}" if bzp[3] else "")
            if number.startswith(fields["numer_bzp"] or ""):
                fields["numer_bzp"] = number
        if not fields["numer_ted"] and "numer_ted" not in protected and (ted := _notice(_TED, text)):
            fields["numer_ted"] = f"{ted[3]}-{ted[1]}"
        if "numer_postepowania" not in protected:
            for label in _REFERENCE_LABEL.finditer(text):
                if m := _REFERENCE_VALUE.match(text, label.end()):
                    value = re.sub(r"\s+", "", m[0])
                    if any(c.isdigit() for c in value) and (
                        not fields["numer_postepowania"] or value.startswith(fields["numer_postepowania"])
                    ):
                        fields["numer_postepowania"] = value
                    break
        if "tytul" not in protected and (title := _title(text)):
            fields["tytul"] = _repair_accents(title, text)
            protected.add("tytul")
