"""PDF -> (document class, canonical JSON)."""

from pathlib import Path

from .class_config import DocumentClass, load_classes, route
from .engines import extract
from .pdf_text import join_pages, read_pages


def process_pdf(
    pdf_path: Path, force_ocr: bool = False, *, classes: list[DocumentClass] | None = None
) -> tuple[str | None, dict]:
    """Class and JSON for one PDF. Any other document gives (None, {}). Raises on a PDF it cannot read."""
    pages = read_pages(pdf_path, force_ocr=force_ocr)
    definition = route(pages, classes if classes is not None else load_classes())
    if definition is None:
        return None, {}
    return definition.id, extract(definition, join_pages(pages))
