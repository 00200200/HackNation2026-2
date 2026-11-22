"""Read role-labelled party and signature cards from native or OCR word boxes."""

import itertools
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from . import appeal
from .common import ATTORNEY_RE, EMAIL_RE, PARTY_LABELS, PERSON
from .pdf_text import WordBox
from .personal_names import compatible_names, nominative
from .power_of_attorney import GRANT, MANDATE_TITLE, NAMED_SIGNATURE
from .receipt_layout import word_rows

_ROLE = r"(?:zamawiający|odwołujący|wykonawca|pełnomocnik odwołującego|nazwa postępowania):"
DETACHED_ROLES = re.compile(rf"(?im)^({_ROLE})[ \t]*\n({_ROLE})[ \t]*$")


def restore_labels(page: str, words: list[WordBox]) -> str:
    lines = page.splitlines()
    insertions = {}
    omitted = set()
    for index, label in enumerate(lines):
        label = label.strip()
        if not re.fullmatch(_ROLE, label, re.IGNORECASE):
            continue
        # The colon ends the label even when it consists of several words.
        ends = [w for w in words if w.text.casefold() == label.split()[-1].casefold()]
        if len(ends) != 1:
            continue
        end = ends[0]
        adjacent = sorted(
            (w for w in words if w.x0 > end.x1 and abs((w.y0 + w.y1 - end.y0 - end.y1) / 2) < (end.y1 - end.y0) * 0.65),
            key=lambda w: w.x0,
        )
        if not adjacent:
            continue
        row = " ".join(w.text for w in adjacent)
        matches = [n for n, line in enumerate(lines) if " ".join(line.split()) == row]
        if not matches:
            prefix = " ".join(w.text for w in adjacent[:2])
            matches = [n for n, line in enumerate(lines) if line == prefix or line.startswith(prefix + " ")]
        if len(matches) == 1 and matches[0] not in insertions:
            insertions[matches[0]] = label
            omitted.add(index)
    return "\n".join(
        (insertions[n] + " " if n in insertions else "") + line for n, line in enumerate(lines) if n not in omitted
    )


def restore_party_columns(pages: list[str], boxes: list[WordBox]) -> list[str]:
    detached = [i for i, page in enumerate(pages) if DETACHED_ROLES.search(page)]
    if not detached:
        return pages
    return [
        restore_labels(page, [w for w in boxes if w.page == i + 1]) if i in detached else page
        for i, page in enumerate(pages)
    ]


_HEADING = re.compile(
    r"^(?:" + "|".join(f"(?P<{k}>{v})" for k, v in PARTY_LABELS.items()) + r")(?:\s*:\s*|\s*$)", re.IGNORECASE
)
_STOP = re.compile(
    r"^(?:udziel\w*|upoważni\w*|ustanawiam\w*|dotyczy|odwołanie|pełnomocnictwo|za zgodność|uzasadnienie|"
    r"działając|załączniki|przedmiot zamówienia)\b",
    re.IGNORECASE,
)
_ID_FIELD = re.compile(r"^(?:NIP|REGON|KRS|PESEL|e-mail)\b", re.IGNORECASE)


@dataclass
class PartyBlock:
    role: str
    order: tuple[int, int, int]  # page, visual row, column
    parent: tuple[int, int, int] | None
    lines: list[str] = field(default_factory=list)
    heading: str = ""
    group: int | None = None


def _line(words):
    return " ".join(w.text for w in words)


def _gutter(row, following, gap):
    """A second role starts a column only if the next physical lines respect its gutter."""
    for i in range(1, len(row)):
        left, right = row[i - 1].x1, row[i].x0
        if right - left < 2 * gap or not _HEADING.match(_line(row[i:])):
            continue
        if not _HEADING.match(_line(row[:i])):
            continue
        split = right - gap
        if any(
            any(w.x1 < split for w in line)
            and any(w.x0 >= split for w in line)
            and not any(w.x0 < split < w.x1 for w in line)
            for line in following
        ):
            return split
    return None


def party_inventory(boxes: list[WordBox], sizes: dict[int, tuple[float, float]]) -> list[PartyBlock]:
    """Enumerate labelled owners before reading any field. Repeated marginal rows delimit cards."""
    pages = {}
    margins = defaultdict(set)
    for page, (width, length) in sizes.items():
        if width <= 0 or length <= 0:
            continue
        rows, height = word_rows(boxes, page)
        pages[page] = rows, height, width, length
        for row in rows:
            y = row[0].y0 / length
            if y < 0.15 or y > 0.85:
                margins[_line(row).casefold(), round(y * 20)].add(page)

    blocks = []
    for page, (rows, height, width, length) in sorted(pages.items()):
        split = None
        group = None
        current = {}
        owners = {}
        grant_columns = set()
        bottom = {}
        for n, row in enumerate(rows):
            y = min(w.y0 for w in row)
            key = _line(row).casefold(), round(row[0].y0 / length * 20)
            if len(margins.get(key, ())) > 1:
                current.clear()
                owners.clear()
                split = None
                continue
            if split is not None and y - max(bottom.values(), default=y) > 3 * height:
                split = None
                owners.clear()
                current.clear()
            gutter = _gutter(row, rows[n + 1 : n + 4], max(height, width * 0.012))
            if (gutter is not None and (split is None or abs(split - gutter) > height)) or (
                split is not None and any(w.x0 < split < w.x1 for w in row)
            ):
                if split is None and gutter is not None and 0 in grant_columns:
                    grant_columns.add(1)
                split = gutter
                group = n
                current.clear()
                owners.clear()
            cells = [row] if split is None else [[w for w in row if w.x0 < split], [w for w in row if w.x0 >= split]]
            for col, cell in enumerate(cells):
                if not cell:
                    continue
                text = _line(cell)
                if y - bottom.get(col, y) > 3 * height:
                    current.pop(col, None)
                    owners.pop(col, None)
                bottom[col] = max(w.y1 for w in cell)
                match = _HEADING.match(text) or NAMED_SIGNATURE.match(text)
                if match:
                    role = match.lastgroup or "signature_owner"
                    order = (page, n, col)
                    if role in {"authority", "other"}:
                        grant_columns.discard(col)
                    elif role == "principal":
                        grant_columns.add(col)
                    if role == "appointee" and col not in grant_columns:
                        role = "other"
                    parent = owners.get(col) if role in {"signer", "representation", "appointee"} else None
                    block = PartyBlock(
                        role, order, parent, heading=match[0].strip(), group=group if split is not None else None
                    )
                    blocks.append(block)
                    current[col] = block
                    if role in {"principal", "appellant", "authority", "signature_owner"}:
                        owners[col] = order
                    elif role != "signer":
                        owners.pop(col, None)
                    text = text[match.end() :]
                elif (
                    (active := current.get(col))
                    and active.role in {"principal", "appointee", "signer"}
                    and active.lines
                    and appeal.MEMBER.match(active.lines[0])
                    and appeal.MEMBER.match(text)
                ):
                    order = (page, n, col)
                    block = PartyBlock(active.role, order, active.parent, group=active.group)
                    blocks.append(block)
                    current[col] = block
                    if active.role == "principal":
                        owners[col] = order
                elif _STOP.match(text) or (appeal.SECTION_LABEL.match(text) and not _ID_FIELD.match(text)):
                    owners.pop(col, None)
                    current.pop(col, None)
                    if (
                        MANDATE_TITLE.fullmatch(text)
                        or GRANT.match(text)
                        or re.match(r"(?i)^niniejszym\s+", text)
                        and GRANT.search(text)
                    ):
                        grant_columns.add(col)
                    else:
                        grant_columns.discard(col)
                if text and col in current:
                    current[col].lines.append(text)
    return blocks


def read_role_columns(pages: list[str], blocks: list[PartyBlock]) -> list[str]:
    """Replace a unique contiguous transcript span only when every printed token is accounted for."""
    groups = defaultdict(list)
    for block in blocks:
        if block.group is not None:
            groups[block.order[0], block.group].append(block)
    result = pages.copy()
    for (page, _), cards in groups.items():
        ordered = sorted(cards, key=lambda b: (b.order[2], b.order[1]))
        if not all(b.lines for b in cards) or len({b.order[2] for b in cards}) < 2:
            continue
        lines = [line for card in ordered for line in [card.heading, *card.lines] if line]
        target = Counter(" ".join(lines).split())
        source = result[page - 1].splitlines()
        spans = []
        for start, line in enumerate(source):
            if not _HEADING.match(line.strip()):
                continue
            seen = Counter()
            for end in range(start, len(source)):
                seen.update(source[end].split())
                if seen == target:
                    spans.append((start, end + 1))
                    break
                if not seen <= target:
                    break
        if len(spans) == 1:
            start, end = spans[0]
            source[start:end] = lines
            result[page - 1] = "\n".join(source)
    return result if result != pages else pages


def apply_appeal_blocks(record: dict, blocks: list[PartyBlock]) -> None:
    """Complete a named appellant's representative using their printed appointment card."""
    if len(record["Odwolujacy"]) != 1:
        return
    appellant = record["Odwolujacy"][0]
    owners = {b.order for b in blocks if b.role == "appellant"}
    counsel = [
        b
        for b in blocks
        if b.order[0] == 1 and (b.role == "counsel" or (b.role == "representation" and b.parent in owners))
    ]
    if len(counsel) != 1 or not counsel[0].lines:
        return
    block = counsel[0]
    first, *following = block.lines
    titled = ATTORNEY_RE.fullmatch(first) or re.fullmatch(rf"(?i:adw\.)\s+({PERSON})", first)
    if not titled and not re.fullmatch(PERSON, first):
        return
    if not titled and block.role == "representation" and not appellant["przez-pelnomocnika"]:
        return
    name = titled[1] if titled else first
    rep = appellant["pelnomocnik"]
    if rep["imie_nazwisko"] and (
        len(rep["imie_nazwisko"].split()) != 2 or not compatible_names(name, rep["imie_nazwisko"])
    ):
        return
    appellant["przez-pelnomocnika"] = 1
    rep["imie_nazwisko"] = (
        rep["imie_nazwisko"] or (nominative(name, "acc") if block.role == "representation" else None) or name
    )
    if (
        following
        and not rep["nazwa"]
        and re.search(r"(?i)\b(?:kancelaria|partners|spółka|sp\.\s+[zjk])\b", following[0])
        and not (appeal.CONTACT.search(following[0]) or appeal.ADDRESS_RE.match(following[0]))
    ):
        rep["nazwa"] = following[0]
    mails = set(EMAIL_RE.findall("\n".join(following)))
    if len(mails) == 1 and not rep["mail"]:
        rep["mail"] = mails.pop()


def _spans_gutter(row, gutter, height):
    if any(w.x0 < gutter < w.x1 for w in row):
        return True
    return any(a.x1 <= gutter <= b.x0 and b.x0 - a.x1 <= height for a, b in itertools.pairwise(row))


def form_columns(page: str, boxes: list[WordBox], width: float) -> str:
    """Read parallel party sections around a persistent gutter. The receipt reader owns bank tables."""
    if not re.search(r"\b(?:zamawiaj[ąa]cy|mocodawca)\b", page, re.IGNORECASE):
        return page
    rows, height = word_rows(boxes)
    if len(rows) < 3 or not width:
        return page
    # The start of the right column recurs at the same position on several rows.
    starts = Counter(
        round(b.x0 / height)
        for row in rows
        for a, b in itertools.pairwise(row)
        if b.x0 - a.x1 > 2 * height and width * 0.32 < b.x0 < width * 0.72
    )
    section = re.compile(
        rf"^(?:{appeal.APPELLANT_LABEL}|(?:wykonawca|podmiot) wnosz[ąa]cy odwo[łl]anie|zamawiaj[ąa]cy|"
        r"mocodawca|pe[łl]nomocni(?:k|cy))(?:[ \t]*:|$)|"
        r"^(?:odwo[łl]anie do|pe[łl]nomocnictwo(?: procesowe)?$|(?:niniejszym )?(?:upowa[żz]niam|udzielam|ustanawiam)\b)",
        re.IGNORECASE,
    )
    for margin, count in starts.most_common():
        if count < 3:
            break
        gutter = (margin - 0.8) * height
        ordered = []
        changed = False
        # Headings and footers that cross the gutter retain their place between bands.
        for spanning, band_rows in itertools.groupby(rows, key=lambda row: _spans_gutter(row, gutter, height)):
            band = list(band_rows)
            if spanning:
                ordered.extend(_line(row) for row in band)
                continue
            columns = [[], []]
            paired_rows = 0
            for row in band:
                cells = [[w for w in row if (w.x0 >= gutter) == col] for col in (0, 1)]
                paired_rows += int(all(cells))
                for col, cell in enumerate(cells):
                    if cell:
                        columns[col].append(_line(cell))
            if paired_rows >= 3 and all(any(section.match(line) for line in column) for column in columns):
                ordered.extend(columns[0] + columns[1])
                changed = True
            else:
                ordered.extend(_line(row) for row in band)
        restored = "\n".join(ordered)
        if changed and Counter(restored.split()) == Counter(page.split()):
            return restored
    return page
