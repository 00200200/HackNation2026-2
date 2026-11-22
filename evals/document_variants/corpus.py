"""Build the variant corpus: for every training case, `n` re-rendered appeals, powers of attorney and transfers,
plus invented negatives. A share of the documents is rasterised into stand-in scans.

The control set re-renders the same facts, text only, with every wording and layout choice at its default option: the
most common one among the 60 training documents of that class where that was measured. It is no copy of a training
template (the training powers of attorney alone use about a dozen). Variant `i` of a case has the same appeal and power
of attorney references in both sets; a transfer differs only where the drifted set picks another payment purpose than
the training one. The control score is the reference point on these facts, so the gap to the drifted set is what wording,
format, layout and scanning cost the app."""

import random
from collections.abc import Callable
from dataclasses import dataclass

from evals.document_variants import appeal, attorney, facts, negatives, scan, transfer
from evals.document_variants.pdfkit import Rendered

SOURCES = [f"przyklad_{n:02d}" for n in range(1, 61)]
DOCS: dict[str, tuple[str, Callable[[facts.Case, random.Random, bool], Rendered]]] = {
    "odwolanie": ("odwolanie.pdf", appeal.render),
    "pelnomocnictwo": ("pelnomocnictwo.pdf", attorney.render),
    "przelew": ("potwierdzenie_przelewu.pdf", transfer.render),
}
NEGATIVES_PER_CASE = 8  # negative documents staged together, like the organizer's "negatywne" folder


@dataclass(frozen=True)
class Item:
    case: str  # the directory the document is staged in
    name: str  # file name before the runner neutralises it
    pdf: bytes
    gold: dict
    tags: dict[str, str]


def rng_for(seed: int, *parts) -> random.Random:
    """A random generator that depends only on the run seed and the parts, so every document is reproducible alone."""
    return random.Random("/".join(map(str, (seed, *parts))))


def prefixed(kind: str, tags: dict[str, str]) -> dict[str, str]:
    """Renderer tags are per document class, so `odwolanie.family` and `pelnomocnictwo.layout` never mix in a slice."""
    return {f"{kind}.{key}": value for key, value in tags.items() if key != "class"}


def finish(pdf: bytes, tags: dict[str, str], rng: random.Random, scan_share: float) -> tuple[bytes, dict[str, str]]:
    if rng.random() >= scan_share:
        return pdf, {**tags, "medium": "text"}
    scanned, scan_tags = scan.scan(pdf, rng)
    return scanned, {**tags, **scan_tags, "medium": "scan"}


def build_cases(sources: list[str], n: int, seed: int, scan_share: float, faithful: bool = False) -> list[Item]:
    items = []
    stream, label = (("control",), "c") if faithful else ((), "v")
    for source in sources:
        for variant in range(n):
            case = facts.build_case(source, rng_for(seed, source, variant, "facts"), variant)  # the same in both sets
            for kind, (name, render) in DOCS.items():
                rng = rng_for(seed, source, *stream, variant, kind)
                rendered = render(case, rng, faithful)
                tags = {
                    "source": source,
                    "set": "control" if faithful else "variants",
                    **{f"case.{k}": v for k, v in case.tags.items()},
                    **prefixed(kind, rendered.tags),
                }
                pdf, tags = finish(rendered.pdf, tags, rng, scan_share)
                items.append(Item(f"{source}-{label}{variant}", name, pdf, rendered.gold, {"class": kind, **tags}))
    return items


def build_negatives(per_kind: int, seed: int, scan_share: float) -> list[Item]:
    items = []
    for kind in negatives.KINDS:
        for i in range(per_kind):
            rng = rng_for(seed, "negative", kind, i)
            rendered = negatives.render(kind, rng)
            pdf, tags = finish(rendered.pdf, prefixed("negatywny", rendered.tags), rng, scan_share)
            items.append(
                Item(
                    "", f"{kind}_{i}.pdf", pdf, {}, {"class": "negatywny", "neg_kind": kind, "set": "variants", **tags}
                )
            )
    return [
        Item(f"negatywne-{k // NEGATIVES_PER_CASE:02d}", item.name, item.pdf, item.gold, item.tags)
        for k, item in enumerate(items)
    ]
