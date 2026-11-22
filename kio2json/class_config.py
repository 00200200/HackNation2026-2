"""Load trusted TOML class definitions and route documents from page content."""

import argparse
import os
import re
import tomllib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from functools import cached_property, partial
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    FiniteFloat,
    ImportString,
    PrivateAttr,
    Tag,
    ValidationError,
    model_validator,
)

from . import trace
from .classify import classify, routing_evidence
from .model_pages import AlternateOCR, model_readings
from .model_profile import Profile, ProfileSettings
from .ocr_accounts import AccountEvidence
from .validators import Validator, declares_checks

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "config" / "classes"
# The model profile (KIO_LLM_*) supports these extractors; a class file opts in with model_profile = true.
# The rule classifier and the model route (llm.RouteDecision) answer only with these ids, so a class with another id
# is never chosen and cannot carry the model profile.
PROFILE_CLASSES = frozenset({"appeal", "power_of_attorney", "bank_transfer"})
PROFILE_EXTRACTORS = frozenset(
    {"kio2json.appeal.extract", "kio2json.bank_transfer.extract", "kio2json.power_of_attorney.extract"}
)


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


def phrase_pattern(phrase: str) -> re.Pattern:
    """Match a cue phrase case-insensitively, across any whitespace, as whole words.

    A label cue such as "NIP:" also matches the label printed as "NIP :".
    """
    words = phrase.split()
    if not words:
        raise ValueError("routing cues must contain text")
    start = r"(?<!\w)" if re.match(r"\w", words[0]) else ""
    end = r"(?!\w)" if re.search(r"\w$", words[-1]) else ""
    body = r"\s+".join(map(re.escape, words))
    if body.endswith(":") and len(body) > 1:
        body = body[:-1] + r"\s*:"
    return re.compile(start + body + end, re.IGNORECASE)


def reaches(score: float, threshold: float) -> bool:
    """Compare float cue weights with a relative tolerance: 0.7 + 0.1 reaches 0.8, and 0 never reaches a threshold."""
    return score >= threshold * (1 - 1e-9)


class Routing(Config):
    pages: int = Field(default=1, ge=1)
    headings: list[Pattern] = []
    required: list[Pattern] = []
    forbidden: list[Pattern] = []
    evidence: Evidence | None = None
    # Plain phrases and their weights. The class applies when the found phrases reach the threshold.
    cues: dict[str, FiniteFloat] = {}
    threshold: FiniteFloat | None = Field(default=None, gt=0)
    _phrases: dict[str, re.Pattern] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def positive_cue(self) -> Self:
        if not (self.headings or self.required or self.evidence or self.cues):
            raise ValueError("routing requires a positive cue")
        if bool(self.cues) != (self.threshold is not None):
            raise ValueError("routing cues and threshold must be set together")
        if any(weight == 0 for weight in self.cues.values()):
            raise ValueError("a routing cue weight must not be 0")
        reachable = sum(weight for weight in self.cues.values() if weight > 0)
        if self.cues and not reaches(reachable, self.threshold):
            raise ValueError(f"threshold {self.threshold:g} exceeds the positive cue weights ({reachable:g})")
        self._phrases = {phrase: phrase_pattern(phrase) for phrase in self.cues}
        return self

    def explain(self, pages: list[str]) -> dict | None:
        """Return the cues that matched these pages, or None when the class does not apply."""
        window = pages[: self.pages]
        text = "\n".join(window)
        lines = [line.strip() for line in text.splitlines()]
        headings = []
        for pattern in self.headings:
            line = next((line for line in lines if pattern.fullmatch(re.sub(r"\s+", "", line))), None)
            if line is None:
                return None
            headings.append(line)
        required = []
        for pattern in self.required:
            match = pattern.search(text)
            if match is None:
                return None
            required.append(match[0].strip())
        if any(pattern.search(text) for pattern in self.forbidden):
            return None
        if self.evidence is not None and not self.evidence.matches(text):
            return None
        cues = []
        for phrase, weight in self.cues.items():
            for number, page in enumerate(window, 1):
                if match := self._phrases[phrase].search(page):
                    cues.append({"cue": phrase, "weight": weight, "page": number, "text": " ".join(match[0].split())})
                    break
        score = sum(cue["weight"] for cue in cues)
        if self.threshold is not None and not reaches(score, self.threshold):
            return None
        return {"headings": headings, "required": required, "cues": cues, "score": score, "threshold": self.threshold}

    def matches(self, pages: list[str]) -> bool:
        return self.explain(pages) is not None


class ClassifierRouting(Config):
    classifier: ImportString[Callable[[list[str]], str | None]]


class OutputField(Config):
    span_evidence: Literal["attorney_name"] | None = None
    type: Literal["string", "integer", "number", "boolean", "object", "list"]
    instruction: Instruction
    nullable: bool = True
    grounding: (
        Literal["numer_bzp", "numer_ted", "czynnosc_powod_id", "czynnosc_opis", "przez-pelnomocnika", "typ"] | None
    ) = None
    normalizer: Literal["iso_date", "money", "account_number", "krs", "nip", "regon", "pesel"] | None = None
    pattern: Pattern | None = None
    fields: dict[str, "OutputField"] | None = None
    items: "OutputField | None" = None
    match_by: str | None = None
    validators: list[Validator] = []
    # "null" writes null for a failed check; "warn" keeps the value and reports it in the trace and viewer.
    on_invalid: Literal["null", "warn"] = "null"

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.validators and self.type in ("object", "list"):
            raise ValueError("validators apply to scalar fields")
        for check in self.validators:
            if not check.fits(self.type):
                article = "an" if self.type == "integer" else "a"
                raise ValueError(f"validator {check.name} does not fit {article} {self.type} field")
            if check.name == "date_range" and self.normalizer != "iso_date":
                raise ValueError("date_range requires the iso_date normalizer")
        if self.validators and self.on_invalid == "null" and not self.nullable:
            raise ValueError('a non-nullable field with validators needs on_invalid = "warn"')
        if (self.fields is not None) != (self.type == "object") or self.fields == {}:
            raise ValueError("only object fields declare a nonempty fields table")
        plain_keys(self.fields or {})
        if (self.items is not None) != (self.type == "list"):
            raise ValueError("only list fields declare an items definition")
        if self.match_by is not None:
            member = self.items
            for key in self.match_by.split("."):
                member = (member.fields or {}).get(key) if member else None
            if not member or member.type in ("object", "list"):
                raise ValueError("match_by must name a scalar field of a list item")
        if self.span_evidence and self.type != "string":
            raise ValueError("attorney name span evidence requires a string field")
        if self.normalizer and self.type != ("number" if self.normalizer == "money" else "string"):
            raise ValueError("normalizer does not match field type")
        if self.pattern and self.pattern.groups != 1:
            raise ValueError("field patterns require one capture group")
        return self


def plain_keys(fields: dict) -> None:
    """Field paths such as `osoby[0].pesel` name fields in the trace and the viewer, so keys cannot hold "." or brackets."""
    for key in fields:
        if any(char in key for char in ".[]"):
            raise ValueError(f"field key {key!r} may not contain '.', '[' or ']'")


def routing_kind(value) -> str:
    """A routing table with a classifier uses Python; any other table uses patterns and cues."""
    if isinstance(value, dict):
        return "classifier" if "classifier" in value else "patterns"
    return "classifier" if isinstance(value, ClassifierRouting) else "patterns"


class DocumentClass(Config):
    span_instructions: str = ""
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str | None = Field(default=None, min_length=1, description="Display name in the viewer")
    enabled: bool = True
    # The KIO_LLM_* profile (mode, routing, second OCR reading) applies to a Python class that sets this.
    model_profile: bool = False
    priority: int = 100
    routing: Annotated[
        Annotated[ClassifierRouting, Tag("classifier")] | Annotated[Routing, Tag("patterns")],
        Discriminator(routing_kind),
    ]
    engines: list[Literal["python", "labelled_fields", "llm"]] = Field(min_length=1)
    extractor: ImportString[Callable[[str], dict]] | None = None
    fields: dict[str, OutputField] = Field(min_length=1)
    _profile: Profile = PrivateAttr(default=Profile())

    _rule_definition: Self | None = PrivateAttr(default=None)
    _source: Path | None = PrivateAttr(default=None)

    @property
    def source(self) -> Path | None:
        return self._source

    @cached_property
    def checked(self) -> bool:
        return any(declares_checks(field) for field in self.fields.values())

    @property
    def rules_only(self) -> Self:
        return self._rule_definition or self

    @property
    def profile(self) -> Profile:
        return self._profile

    def apply_profile(self, profile: Profile) -> None:
        if profile.keyed:
            self._rule_definition = self.model_copy()
        self._profile = profile
        if profile.mode in ("L", "V"):
            self.engines = ["llm"]
            self.extractor = None
        elif profile.mode == "RL":
            self.engines = ["python", "llm"]
        elif profile.mode == "LR":
            self.engines = ["llm", "python"]

    @cached_property
    def output_model(self):
        from .output_schema import record_model

        return record_model(self.fields, self.id, allow_abstention="llm" in self.engines)

    @cached_property
    def cited_model(self):
        from .output_schema import record_model

        return record_model(self.fields, self.id, cited=True, allow_abstention=True)

    @cached_property
    def span_model(self):
        from .output_schema import record_model

        return record_model(self.fields, self.id, allow_abstention=True, spans=True)

    @model_validator(mode="after")
    def plain_top_keys(self) -> Self:
        plain_keys(self.fields)
        return self

    @model_validator(mode="after")
    def python_extractor(self) -> Self:
        if ("python" in self.engines) != (self.extractor is not None):
            raise ValueError("the python engine requires a dotted extractor path")
        return self


@dataclass(frozen=True)
class ClassSources:
    """Class files in load order and the IDs a run enables. Workers parse the same bytes."""

    files: dict[Path, bytes]
    enable: frozenset[str] = frozenset()


def _toml_files(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() != ".toml":
            raise ValueError(f"{path}: a class file must end in .toml")
        return [path]
    if not path.is_dir():
        raise ValueError(f"{path}: no such class directory or file")
    return sorted(path.glob("*.toml"))


def class_sources(
    directory: Path | None = None, extra: Iterable[Path] = (), enable: Iterable[str] = ()
) -> ClassSources:
    """Read the base directory, then each extra directory or TOML file, skipping repeated files.

    An extra directory may be empty, so a class file can be dropped into it while the viewer runs.
    """
    directory = directory or Path(os.getenv("KIO_CLASSES_DIR", DEFAULT_DIR))
    base = _toml_files(directory)
    if not base:
        raise ValueError(f"{directory}: no class TOML files")
    files = {}
    for file in base + [file for path in extra for file in _toml_files(path)]:
        files.setdefault(file.resolve(), file)
    return ClassSources({file: file.read_bytes() for file in files.values()}, frozenset(enable))


def add_class_options(parser: argparse.ArgumentParser) -> None:
    """The class selection flags shared by the batch CLI, the viewer and the class tool."""
    parser.add_argument(
        "--classes",
        action="append",
        default=[],
        type=Path,
        metavar="PATH",
        help="also load the class TOML files in this directory, or this TOML file (repeatable)",
    )
    parser.add_argument(
        "--enable",
        action="append",
        default=[],
        metavar="ID",
        help="turn on a class whose file sets enabled = false (repeatable)",
    )


def load_classes(directory: Path | None = None) -> list[DocumentClass]:
    return parse_classes(class_sources(directory))


def parse_classes(sources: ClassSources | Mapping[Path, bytes]) -> list[DocumentClass]:
    """Parse class files; a plain {path: bytes} mapping enables nothing beyond what its files say."""
    if not isinstance(sources, ClassSources):
        sources = ClassSources(dict(sources))
    classes = {}
    first = next(iter(sources.files))
    profile = ProfileSettings().profile() if first.parent.resolve() == DEFAULT_DIR else Profile()
    if profile.keyed:
        from pydantic import AnyHttpUrl, TypeAdapter

        from .llm import Endpoint
        from .pdf_text import DEFAULT_OCR_ENGINE, OCR_ENGINES

        try:
            endpoint = Endpoint()
            TypeAdapter(AnyHttpUrl).validate_python(endpoint.base_url)
        except ValidationError:
            raise ValueError("Invalid model endpoint configuration") from None
        if os.getenv("KIO_OCR_ENGINE", DEFAULT_OCR_ENGINE) not in OCR_ENGINES:
            raise ValueError("Invalid OCR engine configuration")
    for path, source in sources.files.items():
        try:
            raw = tomllib.loads(source.decode("utf-8"))
            definition = DocumentClass.model_validate(raw)
            if definition.id in classes:
                raise ValueError(f"duplicate class id {definition.id} (also in {classes[definition.id].source})")
            extractor = str(raw.get("extractor", "")).replace(":", ".")
            if definition.model_profile and (
                definition.id not in PROFILE_CLASSES or extractor not in PROFILE_EXTRACTORS
            ):
                # The model profile's routing and gap checks know only the organizer's classes and extractors.
                raise ValueError(
                    "model_profile applies only to the organizer's three classes and their Python extractors"
                )
            # Enable before the profile copies the class for rule recovery, so the copy is enabled too.
            if definition.id in sources.enable:
                definition.enabled = True
            if (
                definition.model_profile
                and definition.engines[0] == "python"
                and isinstance(definition.routing, ClassifierRouting)
            ):
                definition.apply_profile(profile)
        except ValidationError as error:
            details = "; ".join(
                f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors(include_url=False)
            )
            raise ValueError(f"{path}: {details}") from error
        except (ValueError, ImportError) as error:
            raise ValueError(f"{path}: {error}") from error
        definition._source = path
        classes[definition.id] = definition
    unknown = sorted(sources.enable - classes.keys())
    if unknown:
        raise ValueError(f"cannot enable {', '.join(unknown)}: no such class (loaded: {', '.join(sorted(classes))})")
    return sorted(classes.values(), key=lambda c: (c.priority, c.id))


def callable_name(function) -> str:
    """A dotted name for the trace; a partial or callable instance has no __qualname__."""
    name = getattr(function, "__qualname__", type(function).__qualname__)
    return f"{getattr(function, '__module__', type(function).__module__)}.{name}"


def model_route(pages: list[str], alternate: AlternateOCR | None = None) -> str | None:
    from .llm import classify_llm

    if not pages:
        return None
    first = pages[0]
    if alternate:
        first, _ = model_readings(first, [alternate.read(1)])
    return classify_llm(first) if first.strip() else None


def route(
    pages: list[str],
    definitions: list[DocumentClass],
    *,
    ocr_accounts: AccountEvidence | None = None,
    alternate: AlternateOCR | None = None,
    rules_only: bool = False,
) -> DocumentClass | None:
    # Organizer classes share a classifier. Compute its result once for this PDF.
    labels = {}
    fallback = {}

    model_classifier = partial(model_route, alternate=alternate) if alternate else model_route

    for definition in definitions:
        if not definition.enabled:
            continue
        routing = definition.routing
        if isinstance(routing, ClassifierRouting):
            classifier = (
                model_classifier if not rules_only and definition.profile.routing == "model" else routing.classifier
            )
            if not rules_only and definition.profile.routing in {"fallback", "supported"}:
                fallback[definition.id] = definition
            if classifier not in labels:
                labels[classifier] = (
                    classify(pages, ocr_accounts=ocr_accounts)
                    if classifier is classify and ocr_accounts is not None
                    else classifier(pages)
                )
            if labels[classifier] == definition.id:
                if classifier is routing.classifier:
                    trace.note_route(definition.id, "rules", callable_name(classifier))
                else:
                    trace.note_route(definition.id, "model", "first-page model routing")
                return definition
        elif (cues := routing.explain(pages)) is not None:
            trace.note_route(definition.id, "config", definition.source.name if definition.source else None, cues)
            return definition
    supported = {key for key, definition in fallback.items() if definition.profile.routing == "supported"}
    evidence, confirmed_transfer = routing_evidence(pages[0]) if pages and supported else (set(), False)
    for key in supported - evidence:
        del fallback[key]
    if not fallback:
        return None
    label = model_classifier(pages)
    if (
        label == "power_of_attorney"
        and "bank_transfer" in supported
        and evidence == {"bank_transfer"}
        and confirmed_transfer
    ):
        label = "bank_transfer"
    if label in fallback:
        trace.note_route(label, "model fallback", "first-page model routing")
    return fallback.get(label)
