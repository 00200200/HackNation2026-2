"""Class tool: python -m kio2json.classes new <id> --from-pdf sample.pdf [--out DIR] | list

`new` writes a TOML skeleton from the labelled lines on the first page of a sample PDF, then shows
how the skeleton routes and what it extracts from that sample. `list` prints the classes a run
would load with the same --classes and --enable flags as the batch CLI.
"""

import argparse
import json
import math
import re
import sys
import tomllib
import unicodedata
from pathlib import Path

from . import trace
from .class_config import (
    DEFAULT_DIR,
    ClassifierRouting,
    ClassSources,
    DocumentClass,
    add_class_options,
    class_sources,
    parse_classes,
)
from .engines import extract
from .output_schema import NUMBER_TOKEN, normalize
from .pdf_text import NoReadableTextError, OCRRecognitionError, join_pages, read_pages

LABELLED_LINE = re.compile(
    r"^[ \t]*(?P<label>[^\W\d_][^:\n]{0,48}?)[ \t]*:[ \t]*(?P<value>[^\s/].*?)[ \t]*$", re.MULTILINE
)
REGISTRY_NUMBERS = ("nip", "regon", "pesel", "krs")
TITLE_WEIGHT = 2


def slug(label: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", label.translate(str.maketrans("łŁ", "lL")))
    words = re.findall(r"[a-z0-9]+", ascii_text.encode("ascii", "ignore").decode().lower())
    key = "_".join(words) or "pole"
    return key if key[0].isalpha() else f"pole_{key}"


def field_kind(label: str, value: str) -> dict:
    """Guess a normalizer and checks from the label and the sample value."""
    words = set(re.findall(r"\w+", label.casefold()))
    for name in REGISTRY_NUMBERS:
        if name in words and normalize(name, value):
            return {"normalizer": name} | ({} if name == "krs" else {"validators": [name]})
    if normalize("account_number", value) or words & {"iban", "rachunek", "rachunku", "konto"}:
        return {"normalizer": "account_number", "validators": ["iban"]}
    if normalize("iso_date", value):
        return {"normalizer": "iso_date"}
    money = NUMBER_TOKEN.fullmatch(value)
    if money and re.search(r"\d[.,]\d{2}$|zł|PLN|EUR", value, re.IGNORECASE) and normalize("money", value) is not None:
        return {"type": "number", "normalizer": "money"}
    return {}


def title_line(lines: list[str]) -> str | None:
    """The first mostly upper-case line without a label, else the first line of two or more words."""
    plain = [line for line in lines if ":" not in line and len(re.findall(r"[^\W\d_]", line)) >= 4]
    for line in plain:
        letters = re.findall(r"[^\W\d_]", line)
        if sum(c.isupper() for c in letters) >= 0.6 * len(letters):
            return line
    return next((line for line in plain if len(line.split()) >= 2), None)


def toml_string(text: str) -> str:
    # A literal string keeps regex backslashes readable. JSON escapes are valid TOML basic strings.
    if "'" in text or any(ord(c) < 32 and c != "\t" for c in text):
        return json.dumps(text, ensure_ascii=False)
    return f"'{text}'"


def skeleton(class_id: str, pages: list[str], source: Path, *, name: str | None, enabled: bool) -> str:
    first = pages[0] if pages else ""
    lines = [" ".join(line.split()) for line in first.splitlines() if line.strip()]
    labels = {}
    for match in LABELLED_LINE.finditer(first):
        label = " ".join(match["label"].split())
        if len(label.split()) <= 5 and label not in labels:
            labels[label] = " ".join(match["value"].split())
    if not labels:
        raise ValueError("no 'Label: value' lines on the first page")
    title = title_line(lines)
    cues = ({title: TITLE_WEIGHT} if title else {}) | {f"{label}:": 1 for label in labels}
    threshold = (TITLE_WEIGHT if title else 0) + max(1, math.ceil(len(labels) / 2))
    display = name or (title.capitalize() if title else class_id)

    out = [
        f"# Generated from {source.name} (page 1). Check the cues, field names, types and checks.",
        f"id = {toml_string(class_id)}",
        f"name = {toml_string(display)}",
        *([] if enabled else ["enabled = false"]),
        'engines = ["labelled_fields"]',
        "",
        "[routing]",
        "# The class applies when the weights of the phrases found reach the threshold.",
        "# Every `required` regex must match and any `forbidden` regex rejects the class.",
        f"threshold = {threshold}",
        "# forbidden = ['^Projekt\\b']",
        "",
        "[routing.cues]",
        *(f"{toml_string(cue)} = {weight}" for cue, weight in cues.items()),
    ]
    keys = set()
    for label, value in labels.items():
        key = slug(label)
        while key in keys:
            key += "_2"
        keys.add(key)
        kind = field_kind(label, value)
        label_pattern = r"\s+".join(map(re.escape, label.split()))
        out += [
            "",
            f"[fields.{key}]",
            f'type = "{kind.get("type", "string")}"',
            *([f'normalizer = "{kind["normalizer"]}"'] if "normalizer" in kind else []),
            *([f"validators = {json.dumps(kind['validators'])}"] if "validators" in kind else []),
            f"instruction = {toml_string(f'Value printed after {label}: on the document.')}",
            f"pattern = {toml_string(f'^{label_pattern}[ \\t]*:[ \\t]*(.+)$')}",
        ]
    return "\n".join(out) + "\n"


def preview(definition: DocumentClass, pages: list[str]) -> tuple[dict | None, dict, list[dict]]:
    match = definition.routing.explain(pages)
    with trace.recording() as events:
        record = extract(definition, join_pages(pages))
    return match, record, events["warnings"]


def new_class(args: argparse.Namespace) -> int:
    out = args.out / f"{args.id}.toml"
    if out.exists() and not args.force:
        print(f"{out} exists. Pass --force to replace it.", file=sys.stderr)
        return 1
    try:
        # The default set and the output folder must not already hold this ID. The file being replaced is
        # left out, so --force can also replace a generated file that no longer parses.
        sources = class_sources(extra=[args.out] if args.out.is_dir() else [])
        others = {path: data for path, data in sources.files.items() if path.resolve() != out.resolve()}
        loaded = parse_classes(ClassSources(others)) if others else []
    except (OSError, ValueError) as error:
        print(f"Class configuration: {error}", file=sys.stderr)
        return 1
    if any(definition.id == args.id for definition in loaded):
        print(f"Class ID {args.id} is already in use. Choose another ID.", file=sys.stderr)
        return 1
    # A file in the jury's default directory stays off until --enable selects it.
    enabled = args.out.resolve() != DEFAULT_DIR
    try:
        pages = read_pages(args.from_pdf)
        text = skeleton(args.id, pages, args.from_pdf, name=args.name, enabled=enabled)
        definition = DocumentClass.model_validate(tomllib.loads(text))
    except (OSError, ValueError, NoReadableTextError, OCRRecognitionError) as error:
        print(f"{args.from_pdf}: {error}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    match, record, warnings = preview(definition, pages)
    print(f"Wrote {out}: {len(definition.fields)} fields, routing threshold {definition.routing.threshold:g}.")
    if match is None:
        print(f"{args.from_pdf.name} does not reach the threshold. Lower it or edit the cues.")
    else:
        found = ", ".join(f"{cue['cue']!r} +{cue['weight']:g}" for cue in match["cues"])
        print(f"{args.from_pdf.name} routes with score {match['score']:g}: {found}")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    for warning in warnings:
        print(f"check {warning['check']} failed for {warning['field']} = {warning['value']!r}")
    flag = f"--classes {args.out}" if enabled else f"--enable {args.id}"
    print(f"Run: python -m kio2json {flag} --input input --output output")
    print(f"View: python -m kio2json.gui {flag}")
    return 0


def list_classes(args: argparse.Namespace) -> int:
    try:
        classes = parse_classes(class_sources(extra=args.classes, enable=args.enable))
    except (OSError, ValueError) as error:
        print(f"Class configuration: {error}", file=sys.stderr)
        return 1
    print(f"{'id':20} {'on':3} {'file':28} {'routing':16} engines")
    for definition in classes:
        routing = definition.routing
        if isinstance(routing, ClassifierRouting):
            kind = "classifier"
        elif routing.cues:
            kind = f"cues >= {routing.threshold:g}"
        else:
            kind = "patterns"
        source = definition.source.name if definition.source else "-"
        state = "yes" if definition.enabled else "no"
        print(f"{definition.id:20} {state:3} {source:28} {kind:16} {', '.join(definition.engines)}")
    return 0


def class_id(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise argparse.ArgumentTypeError("use lower-case letters, digits and _, starting with a letter")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m kio2json.classes", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new", help="write a class skeleton from a sample PDF")
    new.add_argument("id", type=class_id, help="class ID, also the TOML file name")
    new.add_argument("--from-pdf", required=True, type=Path, help="sample PDF of the new document type")
    new.add_argument("--out", type=Path, default=Path("classes"), help="directory for the TOML (default: classes)")
    new.add_argument("--name", help="display name in the viewer (default: the sample's title)")
    new.add_argument("--force", action="store_true", help="replace an existing file")
    new.set_defaults(run=new_class)
    listing = commands.add_parser("list", help="print the classes a run would load")
    add_class_options(listing)
    listing.set_defaults(run=list_classes)
    args = parser.parse_args()
    if args.command == "new" and not args.from_pdf.is_file():
        parser.error(f"sample PDF not found: {args.from_pdf}")
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
