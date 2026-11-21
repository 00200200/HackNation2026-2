"""Run one web upload through the shared extractor in a disposable process."""

import json
import sys
from dataclasses import asdict
from pathlib import Path

from .batch import configure_logging, read_document
from .class_config import load_classes


def main(source: Path, output: Path) -> None:
    classes = load_classes()
    configure_logging(classes)
    result = read_document(source, classes)
    output.write_text(json.dumps(asdict(result)), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
