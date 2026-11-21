"""Load trusted TOML class definitions and route documents from page content."""

import os
import re
import tomllib
from collections.abc import Callable
from functools import cached_property
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ImportString, model_validator

from .bank_transfer import AccountEvidence
from .classify import classify, classify_with_evidence

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "config" / "classes"


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


def compile_pattern(value: str) -> re.Pattern:
    try:
        pattern = re.compile(value, re.IGNORECASE | re.MULTILINE)
    except (re.error, TypeError) as error:
        raise ValueError(f"invalid pattern: {error}") from error
    if pattern.search(""):
        raise ValueError("pattern must require nonempty text")
    return pattern


Pattern = Annotated[re.Pattern, BeforeValidator(compile_pattern)]
Instruction = Annotated[str, Field(min_length=1)]


class Evidence(Config):
    pattern: Pattern
    minimum: int = Field(ge=1)

    def matches(self, text: str) -> bool:
        hits = set()
        for match in self.pattern.finditer(text):
            # Alternatives can identify the same datum in different capture groups.
            for captured in match.groups() or (match[0],):
                if captured and (value := "".join(captured.split()).casefold()):
                    hits.add(value)
                    break
            if len(hits) >= self.minimum:
                return True
        return False


class Routing(Config):
    pages: int = Field(default=1, ge=1)
    headings: list[Pattern] = []
    required: list[Pattern] = []
    forbidden: list[Pattern] = []
    evidence: Evidence | None = None

    @model_validator(mode="after")
    def positive_cue(self) -> Self:
        if not (self.headings or self.required or self.evidence):
            raise ValueError("routing requires a positive cue")
        return self

    def matches(self, pages: list[str]) -> bool:
        text = "\n".join(pages[: self.pages])
        headings = [re.sub(r"\s+", "", line) for line in text.splitlines()]
        return (
            all(any(pattern.fullmatch(line) for line in headings) for pattern in self.headings)
            and all(pattern.search(text) for pattern in self.required)
            and not any(pattern.search(text) for pattern in self.forbidden)
            and (self.evidence is None or self.evidence.matches(text))
        )


class ClassifierRouting(Config):
    classifier: ImportString[Callable[[list[str]], str | None]]


class OutputField(Config):
    type: Literal["string", "integer", "number", "boolean", "object", "list"]
    instruction: Instruction
    nullable: bool = True
    normalizer: Literal["iso_date", "money", "account_number", "krs", "nip", "regon", "pesel"] | None = None
    pattern: Pattern | None = None
    fields: dict[str, "OutputField"] | None = None
    items: "OutputField | None" = None
    match_by: str | None = None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (self.fields is not None) != (self.type == "object") or self.fields == {}:
            raise ValueError("only object fields declare a nonempty fields table")
        if (self.items is not None) != (self.type == "list"):
            raise ValueError("only list fields declare an items definition")
        if self.match_by is not None:
            member = self.items
            for key in self.match_by.split("."):
                member = (member.fields or {}).get(key) if member else None
            if not member or member.type in ("object", "list"):
                raise ValueError("match_by must name a scalar field of a list item")
        if self.normalizer and self.type != ("number" if self.normalizer == "money" else "string"):
            raise ValueError("normalizer does not match field type")
        if self.pattern and self.pattern.groups != 1:
            raise ValueError("field patterns require one capture group")
        return self


class DocumentClass(Config):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    enabled: bool = True
    priority: int = 100
    routing: ClassifierRouting | Routing
    engines: list[Literal["python", "labelled_fields", "llm"]] = Field(min_length=1)
    extractor: ImportString[Callable[[str], dict]] | None = None
    fields: dict[str, OutputField] = Field(min_length=1)

    @cached_property
    def output_model(self):
        from .output_schema import record_model

        return record_model(self.fields, self.id, allow_abstention="llm" in self.engines)

    @cached_property
    def cited_model(self):
        from .output_schema import record_model

        return record_model(self.fields, self.id, cited=True, allow_abstention=True)

    @model_validator(mode="after")
    def python_extractor(self) -> Self:
        if ("python" in self.engines) != (self.extractor is not None):
            raise ValueError("the python engine requires a dotted extractor path")
        return self


def load_classes(directory: Path | None = None) -> list[DocumentClass]:
    directory = directory or Path(os.getenv("KIO_CLASSES_DIR", DEFAULT_DIR))
    files = sorted(directory.glob("*.toml"))
    if not files:
        raise ValueError(f"{directory}: no class TOML files")
    classes = {}
    for path in files:
        try:
            definition = DocumentClass.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
            if definition.id in classes:
                raise ValueError(f"duplicate class id {definition.id}")
        except (ValueError, ImportError) as error:
            raise ValueError(f"{path}: {error}") from error
        classes[definition.id] = definition
    return sorted(classes.values(), key=lambda c: (c.priority, c.id))


def route(pages: list[str], definitions: list[DocumentClass]) -> DocumentClass | None:
    definition, _ = route_with_evidence(pages, definitions)
    return definition


def route_with_evidence(
    pages: list[str], definitions: list[DocumentClass]
) -> tuple[DocumentClass | None, AccountEvidence | None]:
    # Organizer classes share a classifier. Compute its result once for this PDF.
    labels = {}
    for definition in definitions:
        if not definition.enabled:
            continue
        routing = definition.routing
        if isinstance(routing, ClassifierRouting):
            classifier = routing.classifier
            if classifier not in labels:
                labels[classifier] = (
                    classify_with_evidence(pages) if classifier is classify else (classifier(pages), None)
                )
            label, accounts = labels[classifier]
            if label == definition.id:
                return definition, accounts
        elif routing.matches(pages):
            return definition, None
    return None, None
