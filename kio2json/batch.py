"""Per-document output and diagnostics shared by the CLI and GUI."""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from .class_config import DocumentClass
from .endpoint_error import EndpointError
from .pdf_text import NoReadableTextError
from .pipeline import process_pdf


def configure_logging(classes: list[DocumentClass]) -> None:
    if any(c.enabled and ("llm" in c.engines or c.profile.routing != "rules") for c in classes):
        # The SDK banner names the model; debug logs include response headers and request URLs.
        os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
        os.environ.pop("OPENAI_LOG", None)
        for name in ("openai", "httpx2", "httpcore2"):
            logging.getLogger(name).setLevel(logging.CRITICAL + 1)


@dataclass(frozen=True)
class Result:
    label: str | None
    text: str
    error: str | None = None


def read_document(path: Path, classes: list[DocumentClass]) -> Result:
    try:
        label, data = process_pdf(path, classes=classes)
    except (EndpointError, NoReadableTextError) as error:
        return Result(None, "", str(error))
    except Exception as error:  # noqa: BLE001 - PDF and OCR backends raise unrelated types.
        return Result(None, "", f"{type(error).__name__}: {error}")
    return Result(label, json.dumps(data, ensure_ascii=False, indent=2) + "\n" if data else "")
