"""Session-local PDF snapshots, previews and the jury's ZIP layout."""

import base64
import hashlib
import ntpath
import os
import shutil
import stat
import sys
import zlib
from collections import OrderedDict, defaultdict
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path, PurePosixPath
from time import monotonic
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile, ZipInfo

import pypdfium2 as pdfium
from PIL import Image, ImageDraw
from shiny.types import FileInfo

from .batch import Result, configure_logging, read_batch, read_document, reconcile_cases
from .case_checks import CaseWarning, case_warnings
from .class_config import ClassSources, DocumentClass, load_classes
from .ocr_budget import batch_deadline

type Source = tuple[Path, Path]  # relative name for the jury and path to read


def validate_name(name: str) -> None:
    if not name.strip() or name in (".", "..") or ":" in name or "/" in name or "\\" in name or ntpath.isreserved(name):
        raise ValueError(f"Niedozwolona nazwa pliku lub folderu: {name!r}.")


ZIP_MAX_FILES = 500
ZIP_MAX_BYTES = 1 << 30
ZIP_MAX_ENTRIES = 20 * ZIP_MAX_FILES
# A PDF's streams are compressed already; a much higher ratio marks a ZIP bomb, not a document.
ZIP_MAX_RATIO = 100
# Reading an entry can fail on encryption or on damaged data.
UNREADABLE_ENTRY = (RuntimeError, NotImplementedError, BadZipFile, zlib.error, EOFError)


def entry_name(entry: ZipInfo) -> str:
    """Decode a name the way archivers write it: UTF-8 flag or Unicode path field, else UTF-8 or code page 852."""
    # On Windows zipfile turns "\\" into "/" in the name; that is not a Unicode path field.
    if entry.flag_bits & 0x800 or entry.filename.replace("\\", "/") != entry.orig_filename.replace("\\", "/"):
        return entry.filename
    raw = entry.orig_filename.encode("cp437")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp852")


def zip_sources(
    case: str,
    archive_path: Path,
    directory: Path,
    prefix: str,
    budget: tuple[int, int] = (ZIP_MAX_FILES, ZIP_MAX_BYTES),
) -> list[Source]:
    """Unpack the PDFs of a ZIP. Its folders become cases; loose PDFs go to the named case.

    `budget` is the number of PDFs and bytes the upload may still add.
    """
    try:
        bundle = ZipFile(archive_path)
    except NotImplementedError:
        raise ValueError("Tego wariantu ZIP nie da się otworzyć. Spakuj pliki ponownie zwykłym archiwum ZIP.") from None
    except (BadZipFile, UnicodeDecodeError, OSError):
        raise ValueError("Nie udało się otworzyć archiwum ZIP. Plik może być uszkodzony.") from None
    sources = []
    with bundle:
        if len(bundle.infolist()) > ZIP_MAX_ENTRIES:
            raise ValueError(f"Archiwum ma ponad {ZIP_MAX_ENTRIES} pozycji. Spakuj same foldery spraw z plikami PDF.")
        pdfs = []
        for index, entry in enumerate(bundle.infolist()):
            name = entry_name(entry)
            parts = PurePosixPath(name.replace("\\", "/")).parts
            if entry.is_dir() or not parts or parts[0] == "__MACOSX" or parts[-1].startswith("."):
                continue
            if name.lower().endswith(".pdf"):
                if stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError(f"Archiwum zawiera dowiązanie zamiast pliku: {name}. Spakuj same pliki PDF.")
                # Some Python builds let the BZIP2 and LZMA decoders allocate past an entry's declared size.
                if entry.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
                    raise ValueError(
                        f"Plik {name} jest skompresowany metodą, której nie obsługujemy. Spakuj pliki zwykłym ZIP-em."
                    )
                if entry.file_size > max(1 << 20, ZIP_MAX_RATIO * entry.compress_size):
                    raise ValueError(
                        f"Plik {name} po rozpakowaniu byłby ponad {ZIP_MAX_RATIO} razy większy niż w archiwum. "
                        "Tak nie zachowuje się żaden dokument PDF, więc archiwum odrzucono."
                    )
                pdfs.append((index, entry, name, parts))
        # zipfile reads no more than an entry's declared size, so checking those sizes first bounds the unpacking.
        if len(pdfs) > budget[0] or sum(entry.file_size for _, entry, _, _ in pdfs) > budget[1]:
            raise ValueError(
                f"Przekroczono limit przesyłania: najwyżej {ZIP_MAX_FILES} plików PDF i 1 GB po rozpakowaniu."
            )
        room = budget[1]
        for index, entry, name, parts in pdfs:
            # The entry's name is only checked and used for its JSON's name; the unpacked file gets a fixed one.
            for part in parts:
                validate_name(part)
            target = directory / f"{prefix}-{index}.pdf"
            try:
                with bundle.open(entry) as source, target.open("wb") as copy:
                    room -= bounded_copy(source, copy, min(entry.file_size, room))
            except (*UNREADABLE_ENTRY, OSError) as error:
                # A codec's data error has no errno; a full disk or a permission error keeps its own message.
                if isinstance(error, OSError) and error.errno is not None:
                    raise
                raise ValueError(
                    f"Nie udało się rozpakować {name}. Archiwum może być zaszyfrowane hasłem albo uszkodzone."
                ) from None
            sources.append((Path(*parts) if len(parts) > 1 else Path(case, *parts), target))
    return sources


def bounded_copy(source, copy, limit: int) -> int:
    """Copy at most `limit` bytes and return how many; a longer stream is refused while it is read."""
    copied = 0
    while chunk := source.read(1 << 20):
        copied += len(chunk)
        if copied > limit:
            raise ValueError(
                f"Przekroczono limit przesyłania: najwyżej {ZIP_MAX_FILES} plików PDF i 1 GB po rozpakowaniu."
            )
        copy.write(chunk)
    return copied


def upload_sources(
    case: str, files: list[FileInfo], directory: Path | None = None, uploads: Path | None = None
) -> list[Source]:
    """Uploaded PDFs go to the named case; ZIPs are unpacked into `directory`, within one limit for the upload.

    A browser can send any value for an input, so with `uploads` (the session's upload folder) a file is read
    only from inside it.
    """
    validate_name(case)
    if not files:
        raise ValueError("Wybierz co najmniej jeden plik PDF albo archiwum ZIP.")
    sources = []
    unpacked = 0
    for number, file in enumerate(files):
        name = file["name"]
        validate_name(name)
        if uploads is not None and not (Path(file["datapath"]).is_file() and inside(Path(file["datapath"]), uploads)):
            raise ValueError("Przesłane dane wskazują plik spoza tego wgrania. Wgraj pliki ponownie.")
        suffix = Path(name).suffix.lower()
        if suffix == ".zip" and directory is not None:
            budget = (ZIP_MAX_FILES - len(sources), ZIP_MAX_BYTES - unpacked)
            found = zip_sources(case, Path(file["datapath"]), directory, f"zip{number}", budget)
            unpacked += sum(path.stat().st_size for _, path in found)
            sources += found
        elif suffix == ".pdf":
            path = Path(file["datapath"])
            unpacked += path.stat().st_size
            sources.append((Path(case, name), path))
        else:
            raise ValueError(f"Plik {name} musi być plikiem PDF albo archiwum ZIP.")
        if len(sources) > ZIP_MAX_FILES or unpacked > ZIP_MAX_BYTES:
            raise ValueError(
                f"Przekroczono limit przesyłania: najwyżej {ZIP_MAX_FILES} plików PDF i 1 GB po rozpakowaniu."
            )
    if not sources:
        raise ValueError("W archiwum nie ma plików PDF.")
    return sources


def inside(path: Path, allowed: Path, *, missing_ok: bool = False) -> bool:
    """Whether a path's real target lies in the allowed folder.

    A strict resolve fails on a link chain too long to follow, where a lenient one stops expanding and looks inside.
    """
    try:
        return path.resolve(strict=True).is_relative_to(allowed.resolve(strict=True))
    except (FileNotFoundError, NotADirectoryError):
        return missing_ok and path.resolve().is_relative_to(allowed.resolve())
    except OSError:
        return False


def opened_path(descriptor: int) -> Path | None:
    """The real path of an open file as the operating system names it, or None where no call reports it."""
    if sys.platform == "darwin":
        import fcntl

        return Path(os.fsdecode(fcntl.fcntl(descriptor, fcntl.F_GETPATH, bytes(1024)).split(b"\0", 1)[0]))
    link = Path(f"/proc/self/fd/{descriptor}")
    return Path(os.readlink(link)) if link.exists() else None


def real_root(allowed: Path) -> Path:
    """The folder root named the way the system names an open file, including the case stored on disk."""
    try:
        descriptor = os.open(allowed, os.O_RDONLY)
    except OSError:
        return allowed.resolve(strict=True)
    try:
        return opened_path(descriptor) or allowed.resolve(strict=True)
    finally:
        os.close(descriptor)


def checked_copy(path: Path, base: Path, target: Path) -> bool:
    """Copy a PDF from the file that was opened and checked, if its real path lies under `base`.

    The check and the copy use one open file, so a link changed in between cannot redirect the read.
    """
    with path.open("rb") as source:
        real = opened_path(source.fileno())
        if real is None:
            # Without a call that names the open file, the check could race the read, so the folder is refused.
            raise ValueError(
                "Ten system nie pozwala bezpiecznie czytać folderu --folder-root. Wgraj pliki PDF albo ZIP."
            )
        if not real.is_relative_to(base):
            return False
        with target.open("wb") as copy:
            shutil.copyfileobj(source, copy)
    return True


def folder_sources(folder: str, allowed: Path | None = None, directory: Path | None = None) -> list[Source]:
    """PDFs under a folder; with `allowed`, the folder is read relative to it and must stay inside it.

    With `allowed`, each PDF is read from a checked copy in `directory`.
    """
    root = Path(os.path.expanduser(folder)) if allowed is None else allowed / folder.strip()
    if allowed is not None and not inside(root, allowed, missing_ok=True):
        raise ValueError(f"Można otwierać tylko foldery w {allowed}.")
    # With a root, an empty field opens the root itself.
    if (allowed is None and not folder.strip()) or not root.is_dir():
        raise ValueError("Podaj ścieżkę do istniejącego folderu.")
    sources = []
    base = real_root(allowed) if allowed is not None else None
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() == ".pdf" and path.is_file():
            relative = path.relative_to(root)
            if allowed is not None:
                # A link inside the allowed folder must not open a file outside it.
                copy = directory / f"folder-{len(sources)}.pdf"
                try:
                    kept = checked_copy(path, base, copy)
                except OSError as error:
                    message = error.strerror or str(error)
                    raise ValueError(f"Nie udało się odczytać pliku {relative.as_posix()}: {message}.") from None
                if not kept:
                    raise ValueError(f"Plik {relative.as_posix()} prowadzi poza folder {allowed}.")
                path = copy
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
    sources: list[Source],
    directory: Path,
    classes: list[DocumentClass] | None = None,
    class_key: str = "",
    *,
    class_files: ClassSources | None = None,
    workers: int = 1,
    on_progress: Callable[[int, Path], None] | None = None,
) -> list[Document]:
    """Read every source once, in parallel worker processes when given class files and several workers.

    `on_progress(done, name)` is called after each document, including cached ones.
    """
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
    snapshots, results, pending = [], {}, []
    for index, (_, path) in enumerate(sources):
        snapshot = directory / f"{index}.pdf"
        snapshots.append(snapshot)
        try:
            shutil.copyfile(path, snapshot)
            key = None
            if class_key:  # Hashed in chunks, so a large PDF is not held in memory a second time.
                with snapshot.open("rb") as file:
                    key = (hashlib.file_digest(file, "sha256").hexdigest(), class_key)
        except OSError as error:  # A file that cannot be read fails alone; the other documents still run.
            results[index] = Result(None, error=str(error))
            continue
        cached = _results.get(key) if key else None
        if cached is None:
            pending.append((index, key))
        else:
            results[index] = cached
    done = 0
    for index in sorted(results):
        done += 1
        if on_progress:
            on_progress(done, sources[index][0])
    paths = [snapshots[index] for index, _ in pending]
    if class_files is not None and workers > 1 and len(paths) > 1:
        # Worker processes each run their own PDFium, so the viewer's preview thread never shares one.
        stream = read_batch(paths, class_files, min(workers, len(paths)), explain=True)
    else:
        stream = (read_document(path, classes, batch_deadline=deadline, explain=True) for path in paths)
    for (index, key), result in zip(pending, stream, strict=True):
        results[index] = result
        # Keep only complete readings: no error, no rule fallback, and no optional OCR pass cut short.
        expired = (result.trace or {}).get("optional_ocr_expired") or monotonic() >= deadline
        if class_key and not (result.error or result.used_recovery or expired):
            _results[key] = result
            while len(_results) > CACHED_RESULTS:
                _results.popitem(last=False)
        done += 1
        if on_progress:
            on_progress(done, sources[index][0])
    documents = [Document(name, snapshots[index], results[index]) for index, (name, _) in enumerate(sources)]
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
