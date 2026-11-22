"""Session-local PDF snapshots, previews and the jury's ZIP layout."""

import base64
import hashlib
import ntpath
import os
import shutil
import zlib
from collections import OrderedDict, defaultdict
from contextlib import closing
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path, PurePosixPath
from time import monotonic
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

import pypdfium2 as pdfium
from PIL import Image, ImageDraw
from shiny.types import FileInfo

from .batch import Result, configure_logging, read_document, reconcile_cases
from .case_checks import CaseWarning, case_warnings
from .class_config import DocumentClass, load_classes
from .ocr_budget import batch_deadline

type Source = tuple[Path, Path]  # relative name for the jury and path to read


def validate_name(name: str) -> None:
    if not name.strip() or name in (".", "..") or ":" in name or "/" in name or "\\" in name or ntpath.isreserved(name):
        raise ValueError(f"Niedozwolona nazwa pliku lub folderu: {name!r}.")


ZIP_MAX_FILES = 500
ZIP_MAX_BYTES = 1 << 30
# Reading an entry can fail on encryption, an unsupported method or damaged data.
UNREADABLE_ENTRY = (RuntimeError, NotImplementedError, BadZipFile, zlib.error, EOFError)


def entry_name(entry: ZipInfo) -> str:
    """Decode a name the way archivers write it: UTF-8 flag or Unicode path field, else UTF-8 or code page 852."""
    if entry.flag_bits & 0x800 or entry.filename != entry.orig_filename:
        return entry.filename
    raw = entry.orig_filename.encode("cp437")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp852")


def zip_sources(case: str, archive_path: Path, directory: Path, prefix: str) -> list[Source]:
    """Unpack the PDFs of a ZIP. Its folders become cases; loose PDFs go to the named case."""
    try:
        bundle = ZipFile(archive_path)
    except BadZipFile:
        raise ValueError("Nie udało się otworzyć archiwum ZIP. Plik może być uszkodzony.") from None
    sources = []
    with bundle:
        pdfs = []
        for index, entry in enumerate(bundle.infolist()):
            name = entry_name(entry)
            parts = PurePosixPath(name.replace("\\", "/")).parts
            if entry.is_dir() or not parts or parts[0] == "__MACOSX" or parts[-1].startswith("."):
                continue
            if name.lower().endswith(".pdf"):
                pdfs.append((index, entry, name, parts))
        # zipfile reads no more than an entry's declared size, so checking those sizes first bounds the unpacking.
        if len(pdfs) > ZIP_MAX_FILES or sum(entry.file_size for _, entry, _, _ in pdfs) > ZIP_MAX_BYTES:
            raise ValueError(f"Archiwum jest za duże. Limit to {ZIP_MAX_FILES} plików PDF i 1 GB po rozpakowaniu.")
        for index, entry, name, parts in pdfs:
            for part in parts:
                validate_name(part)
            target = directory / f"{prefix}-{index}.pdf"
            try:
                with bundle.open(entry) as source, target.open("wb") as copy:
                    shutil.copyfileobj(source, copy)
            except UNREADABLE_ENTRY:
                raise ValueError(
                    f"Nie udało się rozpakować {name}. Archiwum może być zaszyfrowane hasłem albo uszkodzone."
                ) from None
            sources.append((Path(*parts) if len(parts) > 1 else Path(case, *parts), target))
    return sources


def upload_sources(case: str, files: list[FileInfo], directory: Path | None = None) -> list[Source]:
    """Uploaded PDFs go to the named case; ZIPs are unpacked into `directory`, within one limit for the upload."""
    validate_name(case)
    if not files:
        raise ValueError("Wybierz co najmniej jeden plik PDF albo archiwum ZIP.")
    sources = []
    unpacked = 0
    for number, file in enumerate(files):
        name = file["name"]
        validate_name(name)
        suffix = Path(name).suffix.lower()
        if suffix == ".zip" and directory is not None:
            found = zip_sources(case, Path(file["datapath"]), directory, f"zip{number}")
            unpacked += sum(path.stat().st_size for _, path in found)
            sources += found
        elif suffix == ".pdf":
            sources.append((Path(case, name), Path(file["datapath"])))
        else:
            raise ValueError(f"Plik {name} musi być plikiem PDF albo archiwum ZIP.")
        if len(sources) > ZIP_MAX_FILES or unpacked > ZIP_MAX_BYTES:
            raise ValueError(f"Za dużo plików naraz. Limit to {ZIP_MAX_FILES} plików PDF i 1 GB po rozpakowaniu.")
    if not sources:
        raise ValueError("W archiwum nie ma plików PDF.")
    return sources


def folder_sources(folder: str, allowed: Path | None = None) -> list[Source]:
    """PDFs under a folder; with `allowed`, the folder is read relative to it and must stay inside it."""
    root = Path(os.path.expanduser(folder)) if allowed is None else allowed / folder
    if allowed is not None and not root.resolve().is_relative_to(allowed.resolve()):
        raise ValueError(f"Można otwierać tylko foldery w {allowed}.")
    if not folder.strip() or not root.is_dir():
        raise ValueError("Podaj ścieżkę do istniejącego folderu.")
    sources = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() == ".pdf" and path.is_file():
            relative = path.relative_to(root)
            if len(relative.parts) == 1:  # User selected the case folder itself.
                relative = Path(root.resolve().name, relative)
            sources.append((relative, path))
    if not sources:
        raise ValueError("W tym folderze nie ma plików PDF.")
    return sources


@dataclass(frozen=True)
class Document:
    name: Path
    snapshot: Path
    result: Result
    warnings: tuple[CaseWarning, ...] = ()


# Results by PDF content and class set, so a repeated run in the viewer skips OCR.
_results: OrderedDict[tuple[str, str], Result] = OrderedDict()
CACHED_RESULTS = 512


def analyze(
    sources: list[Source], directory: Path, classes: list[DocumentClass] | None = None, class_key: str = ""
) -> list[Document]:
    deadline = batch_deadline(len(sources))
    targets = set()
    for name, _ in sources:
        for part in name.parts:
            validate_name(part)
        key = name.with_suffix(".json").as_posix().casefold()
        if key in targets:
            raise ValueError(f"Dwa dokumenty mają tę samą nazwę wyniku: {key}. Zmień nazwę jednego z nich.")
        targets.add(key)

    classes = load_classes() if classes is None else classes
    configure_logging(classes)
    documents = []
    for index, (name, path) in enumerate(sources):
        snapshot = directory / f"{index}.pdf"
        try:
            shutil.copyfile(path, snapshot)
        except OSError as error:
            result = Result(None, error=str(error))
        else:
            key = (hashlib.sha256(snapshot.read_bytes()).hexdigest(), class_key)
            result = _results.get(key) if class_key else None
            if result is None:
                result = read_document(snapshot, classes, batch_deadline=deadline, explain=True)
                # Keep only complete readings: no error, no rule fallback, and optional OCR still had time.
                if class_key and not (result.error or result.used_recovery) and monotonic() < deadline:
                    _results[key] = result
                    while len(_results) > CACHED_RESULTS:
                        _results.popitem(last=False)
        documents.append(Document(name, snapshot, result))
    names = [document.name for document in documents]
    results = reconcile_cases(names, [document.result for document in documents])
    warnings = defaultdict(list)
    for warning in case_warnings(names, results):
        for name in warning.documents:
            warnings[name].append(warning)
    return [
        replace(document, result=result, warnings=tuple(warnings[document.name]))
        for document, result in zip(documents, results, strict=True)
    ]


def archive(documents: list[Document]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as bundle:
        for document in documents:
            # The CLI writes LF line endings on every platform; the ZIP holds the same bytes.
            bundle.writestr(document.name.with_suffix(".json").as_posix(), document.result.text)
    return output.getvalue()


def page_count(path: Path) -> int:
    with pdfium.PdfDocument(path) as pdf:
        return len(pdf)


def page_image(path: Path, number: int, boxes: list[list[float]] = ()) -> str:
    """Render a page as a PNG data URL and mark the given word boxes (PDF points from the top left)."""
    with pdfium.PdfDocument(path) as pdf, closing(pdf[number - 1]) as page:
        scale = min(2, 1500 / max(page.get_size()))
        with closing(page.render(scale=scale)) as bitmap:
            image = bitmap.to_pil().convert("RGBA")
    if boxes:
        overlay = Image.new("RGBA", image.size)
        draw = ImageDraw.Draw(overlay)
        for x0, y0, x1, y1 in boxes:
            draw.rectangle(
                [x0 * scale - 3, y0 * scale - 3, x1 * scale + 3, y1 * scale + 3],
                fill=(255, 196, 0, 80),
                outline=(24, 61, 64, 255),
                width=3,
            )
        image = Image.alpha_composite(image, overlay)
    output = BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
