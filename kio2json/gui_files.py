"""Session-local PDF snapshots, previews and the jury's ZIP layout."""

import base64
import ntpath
import os
import shutil
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pypdfium2 as pdfium
from shiny.types import FileInfo

from .batch import Result, configure_logging, read_document, reconcile_cases
from .case_checks import CaseWarning, case_warnings
from .class_config import DocumentClass, load_classes
from .ocr_budget import batch_deadline

type Source = tuple[Path, Path]  # relative name for the jury and path to read


def validate_name(name: str) -> None:
    if not name.strip() or name in (".", "..") or ":" in name or "/" in name or "\\" in name or ntpath.isreserved(name):
        raise ValueError(f"Niedozwolona nazwa pliku lub folderu: {name!r}.")


def upload_sources(case: str, files: list[FileInfo]) -> list[Source]:
    validate_name(case)
    if not files:
        raise ValueError("Wybierz co najmniej jeden plik PDF.")
    sources = []
    for file in files:
        name = file["name"]
        validate_name(name)
        if Path(name).suffix.lower() != ".pdf":
            raise ValueError(f"Plik {name} musi mieć rozszerzenie PDF.")
        sources.append((Path(case, name), Path(file["datapath"])))
    return sources


def folder_sources(folder: str) -> list[Source]:
    root = Path(os.path.expanduser(folder))
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


def analyze(sources: list[Source], directory: Path, classes: list[DocumentClass] | None = None) -> list[Document]:
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
            result = Result(None, "", str(error))
        else:
            result = read_document(snapshot, classes, batch_deadline=deadline, explain=True)
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
            bundle.writestr(document.name.with_suffix(".json").as_posix(), document.result.text)
    return output.getvalue()


def page_count(path: Path) -> int:
    with pdfium.PdfDocument(path) as pdf:
        return len(pdf)


def page_image(path: Path, number: int) -> str:
    with pdfium.PdfDocument(path) as pdf, closing(pdf[number - 1]) as page:
        scale = min(2, 1500 / max(page.get_size()))
        with closing(page.render(scale=scale)) as bitmap:
            output = BytesIO()
            bitmap.to_pil().save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
