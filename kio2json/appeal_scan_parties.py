"""Recover parties and the appointed lawyer from a scanned appeal's cover sheet."""

import itertools
import re
from collections.abc import Collection

from stdnum.pl import nip

from . import appeal
from .common import EMAIL_RE, PERSON, registry_ids, squash
from .ocr_normalize import normalize_ocr
from .pdf_text import WordBox
from .personal_names import compatible_names
from .receipt_layout import _word_rows

# Polish letters have a one-to-one mapping here, so folded match offsets index the original.
_FOLD = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
_LABELS = {
    "odwalujacy": "Odwołujący",
    "odwolujacy": "Odwołujący",
    "zamawiajacy": "Zamawiający",
    "wykonawca": "Wykonawca",
    "pelnomocnik odwolujacego": "Pełnomocnik odwołującego",
}
_LABEL = re.compile(r"^(" + "|".join(_LABELS) + r")\s*(?=[:(])")
_STOP = re.compile(r"^(?:dotyczy\b|wpis od odwolania|dzialajac w imieniu|o\s*d\s*w\s*o\s*l\s*a\s*n\s*i\s*e\s*$)")
_APPOINT = re.compile(r"\b(?:(?:reprezentowan|zastepowan)\w* prze[zż]|pelnomocnik odwolujacego)\b")
_TITLE = re.compile(r"\b(?:adw\.|r\.\s*pr\.|adwokat\w*|radc\w* prawn\w*)\s+")
_TRIM = " \t.,„“”\"'’*|©®•—–"
_MAIL_LABEL = re.compile(r"\b(?:e[- ]?mail|adres poczty elektronicznej)\s*[:.]\s*", re.IGNORECASE)
_INSTITUTION = re.compile(
    r"\b(?:urzad|gmina|powiat|zespol|zarzad|zaklad|centrum|osrodek|szpital|instytut|uniwersytet|muzeum|biblioteka)\b"
)


def _fold(line: str) -> str:
    return line.translate(_FOLD).lower()


def _cover(page: str) -> list[str]:
    lines = []
    for row in page.splitlines():
        line = row.lstrip(_TRIM).strip()
        if re.match(r"^u[ił]\.\s+\S.+\d", line, re.IGNORECASE):
            line = "ul." + line[3:]
        line = re.sub(r"^KRS\s+nr\.?\s*:\s*(\d{1,9})\s*$", lambda m: "KRS " + m[1].zfill(10), line, flags=re.IGNORECASE)
        folded = _fold(line)
        if _STOP.match(folded):
            if folded.replace(" ", "") == "odwolanie" and not any(appeal.SECTION_RE.match(row) for row in lines):
                continue
            break
        if label := _LABEL.match(folded):
            line = _LABELS[label[1]] + re.sub(r"^:\s*[_.]+\s+", ": ", line[label.end() :])
        if line:
            if (
                lines
                and re.search(r"wspolnie\b", _fold(lines[-1]))
                and line.lower().startswith("art.")
                and line.endswith(":")
            ):
                lines[-1] += " " + line
            else:
                lines.append(line)
    return lines


def _layout_cover(page: str, boxes: list[WordBox]) -> str:
    """Read label and value columns together only when both printed roles support that layout."""
    if not boxes or not re.search(r"(?im)^\s*(?:zamawiaj[ąa]cy|odwo[łl]uj[ąa]cy|dotyczy)\s*:\s*$", page):
        return page
    rows, height = _word_rows(boxes)
    anchors = []
    for i, row in enumerate(rows):
        # A left column can consist of just the role word and a separate colon.
        match = _LABEL.match(_fold(" ".join(w.text for w in row)))
        if match and match[1] in {"zamawiajacy", "odwolujacy"}:
            anchors.append((i, row[0]))
    if len(anchors) != 2 or abs(anchors[0][1].x1 - anchors[1][1].x1) > 4 * height:
        return page
    # Require a persistent right column, not two standalone headings in ordinary prose.
    for n, word in anchors:
        if not any(row[0].x0 > word.x1 + height for row in rows[max(0, n - 2) : n] + rows[n + 1 : n + 3]):
            return page
    text = [" ".join(w.text for w in row) for row in rows]
    for n, word in anchors:
        # A centre-aligned role can sit halfway down its value cell. Attach it to
        # the first line after the blank gutter above that cell.
        if not re.fullmatch(r"[\włŁ]+\s*:", text[n]) or n == 0:
            continue
        above = n
        while above and rows[above - 1][0].x0 > word.x1 + height:
            gap = min(w.y0 for w in rows[above]) - max(w.y1 for w in rows[above - 1])
            if gap > 1.5 * height:
                break
            above -= 1
        if above < n:
            text[above], text[n] = text[n] + " " + text[above], ""
    return normalize_ocr("\n".join(text))


def _form_cards(lines: list[str]) -> list[str]:
    """Translate the role and field labels of an electronic form into ordinary party cards."""
    if not any("ustawowy/pelnomocnik:" in _fold(line) for line in lines):
        return lines
    result = []
    role = None
    first = ""
    for row in lines:
        if role_label := re.match(
            r"^(Odwołujący|Zamawiający|Przedstawiciel ustawowy/pełnomocnik)\s*:\s*", row, re.IGNORECASE
        ):
            role = role_label[1].casefold()
            row = row[role_label.end() :]
        key, colon, value = row.partition(":")
        if not colon or not role:
            continue
        field = _fold(key.strip())
        value = value.strip()
        if field in ("nazwa firmy", "nazwa") and value and role in ("odwołujący", "zamawiający"):
            result.append(role.capitalize() + ": " + value)
        elif role.startswith("przedstawiciel"):
            if field == "imie":
                first = value
            elif field == "nazwisko" and first and re.fullmatch(PERSON, first + " " + value):
                result.append("Pełnomocnik odwołującego: " + first + " " + value)
            elif field == "email" and value:
                result.append("e-mail: " + value)
    if any(line.startswith("Odwołujący:") for line in result) and any(
        line.startswith("Zamawiający:") for line in result
    ):
        return result
    return lines


def _recover_authority_label(lines: list[str]) -> None:
    if any(line.startswith("Zamawiający:") for line in lines) or not any(
        line.startswith("Odwołujący:") for line in lines
    ):
        return
    # Two separate address cards. The first already ended with an e-mail, and
    # the second identifies a public institution with its own address, ID and e-mail.
    candidates = []
    for n, line in enumerate(lines):
        if not _INSTITUTION.search(_fold(line)) or not any(_MAIL_LABEL.search(row) for row in lines[max(0, n - 3) : n]):
            continue
        card = lines[n + 1 : n + 7]
        if (
            card
            and appeal.ADDRESS_RE.match(card[0])
            and (
                (any(appeal.ID_LINE_RE.search(row) for row in card) and any(_MAIL_LABEL.search(row) for row in card))
                or (n and appeal.CONTACT.search(lines[n - 1]) and any(re.match(r"^\d{2}-\d{3} ", row) for row in card))
            )
        ):
            candidates.append(n)
    if len(candidates) == 1:
        lines[candidates[0]] = "Zamawiający: " + lines[candidates[0]]


def _lawyer(line: str) -> str | None:
    if (title := _TITLE.search(_fold(line))) and (person := re.match(PERSON, line[title.end() :])):
        return person[0]
    return None


def _signature_name(appointed: str, pages: list[str]) -> str:
    # Use the same person's printed nominative from a signature or professional stamp.
    candidates = set()
    for page in pages:
        lines = page.splitlines()
        for i, line in enumerate(lines):
            if not i or not re.match(
                r"^(?:podpis(?:ano|al[ao]?)?\b|podpis elektroniczny|z powazaniem|pelnomocnik(?: odwolujacego)?[: ]*$)",
                _fold(lines[i - 1]).strip(),
            ):
                continue
            candidate = _lawyer(line) or (line.strip() if re.fullmatch(PERSON, line.strip()) else None)
            if candidate and candidate != appointed and compatible_names(appointed, candidate):
                candidates.add(candidate)
        # Professional rosters also print names in the nominative above each title.
        for line, title in itertools.pairwise(lines):
            if not re.fullmatch(r"radca prawny|adwokat", _fold(title.strip())):
                continue
            if re.fullmatch(PERSON, line.strip()) and compatible_names(appointed, line.strip()):
                candidates.add(line.strip())
    if len(candidates) == 1:
        return candidates.pop()
    # Unambiguous accusative endings in a female name after "reprezentowany przez".
    first, last = appointed.split()
    if first.endswith("ę") and last.endswith(("ską", "cką", "dzką")):
        names = [part[:-1] + "a" if part.endswith(("ą", "ę")) else part for part in last.split("-")]
        return first[:-1] + "a " + "-".join(names)
    return appointed


def _mail(lines: list[str], name: str, scan_pages: list[str]) -> str | None:
    first, last = _fold(name).split()
    local = rf"((?:{re.escape(first[0])}|{re.escape(first)})\s*\.\s*{re.escape(last)}|biuro|kancelaria)"
    domain = r"([\w-]+(?:\.[\w-]+)+)"
    for line in lines:
        label = _MAIL_LABEL.search(line)
        value = line[label.end() :].strip() if label else line
        if address := EMAIL_RE.search(value):
            return address[0]
        # A labelled address must begin with this lawyer's name or a conventional
        # office mailbox before interpreting a damaged separator.
        separator = r"\s*(?:[Q(©®]+(?:a(?=\s))?|[O0])\s*"
        if label and (damaged := re.match(local + separator + domain, value.translate(_FOLD), re.IGNORECASE)):
            host = value[damaged.start(2) : damaged.end(2)]
            # A repeated letterhead website can corroborate an accent error in the host.
            printed_hosts = set(re.findall(r"\bwww\.([\w-]+(?:\.[\w-]+)+)", "\n".join(scan_pages), re.IGNORECASE))
            confirmed = [h for h in printed_hosts if _fold(h) == _fold(host)]
            if len(confirmed) == 1:
                host = confirmed[0]
            return re.sub(r"\s+", "", damaged[1]).lower() + "@" + host
    return None


def _representative(block: list[str], scan_pages: list[str]) -> dict | None:
    start = next((n for n, line in enumerate(block) if _APPOINT.search(_fold(line))), None)
    if start is None:
        start = next((n for n, row in enumerate(block) if _TITLE.match(_fold(row))), None)
    if start is None:
        return None
    appointment = block[start:]
    first = None
    for n, line in enumerate(appointment[:4]):
        if re.search(r"\b(?:kancelaria|adres do korespondencji|prezes\w*|prokurent\w*|czlonek zarzadu)\b", _fold(line)):
            break
        phrase = line
        if _TITLE.search(_fold(line) + " ") and n + 1 < len(appointment):
            phrase = squash(line + " " + appointment[n + 1])
        if first := _lawyer(phrase):
            break
        if re.match(r"^pelnomocnik odwolujacego\s*:", _fold(line)):
            value = line.partition(":")[2].strip()
            if re.fullmatch(PERSON, value):
                first = value
                break
    if not first:
        return None
    first = _signature_name(first, scan_pages)
    firm = None
    for i, line in enumerate(appointment):
        if _fold(line).endswith("z kancelarii:"):
            # Explicit firm block ends at the seat, street or correspondence heading.
            parts = []
            for row in appointment[i + 1 :]:
                if re.search(r"^(?:z siedziba|adres\b|ul\.|tel|e-mail)", _fold(row)):
                    break
                parts.append(row)
            firm = squash(" ".join(parts)) or None
        elif re.search(r"\b(?:kancelaria|biuro prawne)\b", _fold(line)) and not _MAIL_LABEL.search(line):
            value = line.partition(":")[2].strip() if ":" in line else line
            if i and appointment[i - 1].isupper() and not re.search(r"\d|[:@]", appointment[i - 1]):
                value = appointment[i - 1] + " " + value
            firm = re.split(r",?\s+(?:ul\.|al\.|\|)\s*", value)[0].strip(" *|!") or None
        if firm:
            break
    return {"imie_nazwisko": first, "nazwa": firm, "mail": _mail(appointment, first, scan_pages)}


def _registry_footer(party: dict, pages: list[str]) -> None:
    """Link register footers to the appellant only via a matching letterhead or printed identifier."""
    core = re.split(r"\b(?:sp\.|spolka|s\.a\.)", _fold(party["nazwa"]), maxsplit=1)[0].strip().split()
    if len(core) < 2:
        return
    # A letterhead can split the brand from its full legal name. Require the
    # first three words (or the whole two-word name) before the court address.
    header = []
    for line in pages[0].splitlines()[:10]:
        if appeal.SECTION_RE.match(line) or re.match(r"prezes", _fold(line)):
            break
        header.append(line)
    letter = _fold(squash(" ".join(header)))
    if " ".join(core[:3]) in letter:
        initial = registry_ids(letter.upper())
        if initial["nip"] and nip.is_valid(initial["nip"]):
            party["nip"] = party["nip"] or initial["nip"]

    candidates = {k: set() for k in ("nip", "regon", "krs")}
    for page in pages:
        lines = page.splitlines()
        for i, line in enumerate(lines):
            ids = registry_ids(line.upper())
            if not any(ids.values()):
                continue
            section = [line]
            for next_line in lines[i + 1 : i + 4]:
                if not any(registry_ids(next_line.upper()).values()):
                    break
                section.append(next_line)
            ids = registry_ids(" ".join(section).upper())
            if any(party[k] and party[k] == ids[k] for k in ids) and not any(
                party[k] and ids[k] and party[k] != ids[k] for k in ids
            ):
                for k, value in ids.items():
                    if value and not party[k]:
                        candidates[k].add(value)
    for k, values in candidates.items():
        if len(values) == 1:
            party[k] = values.pop()


def _signed_mandate(party: dict, pages: list[str]) -> None:
    # A repeated footer stamp needs the same role and person on two separate pages.
    if party["przez-pelnomocnika"]:
        return
    stamps = []
    for page in pages:
        tail = page.splitlines()[-9:]
        marked = next((i for i, row in enumerate(tail) if re.search(r"\bpelnomocnik(?:\s+\d+)?$", _fold(row))), None)
        candidates = set()
        if marked is not None:
            for row in tail[marked + 1 :]:
                if name := re.search(rf"({PERSON})\s*$", row):
                    candidates.add(name[1])
        stamps.append(candidates)
    repeated = {name for names in stamps for name in names if sum(name in s for s in stamps) > 1}
    if len(repeated) == 1:
        party["przez-pelnomocnika"] = 1
        party["pelnomocnik"]["imie_nazwisko"] = repeated.pop()
    elif any(
        re.search(r"na podstawie udzielonego mi pelnomocnictwa,?\s+wnosze odwolanie", _fold(page)) for page in pages
    ):
        party["przez-pelnomocnika"] = 1


def _authority_rows(parties: list[dict], block: list[str]) -> list[dict]:
    rows = []
    for party in parties:
        name = re.sub(r"(?<=\w)-\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])", "-", party["nazwa"])
        # A marginal "prowadzący postępowanie" caption belongs to the numbered
        # institution immediately above it.
        entry = next((i for i, line in enumerate(block) if party["nazwa"] in line), None)
        leading = bool(re.search(r"prowadząc|lider", party["sublabel"], re.IGNORECASE))
        if entry is not None:
            for line in block[entry + 1 :]:
                if appeal.MEMBER.match(line) or appeal.SECTION_RE.match(line):
                    break
                if "zamawiajacy prowadzacy postepowanie" in _fold(line):
                    leading = True
                    break
        rows.append(
            {
                "nazwa": name,
                **{k: party[k] for k in ("krs", "nip", "regon")},
                "prowadzacy_postepowanie": int(leading) if len(parties) > 1 else None,
            }
        )
    return rows


def apply_parties(
    record: dict, pages: list[str], ocr_pages: Collection[int], first_page_words: list[WordBox] | None = None
) -> None:
    if not pages or 1 not in ocr_pages:
        return
    cover = _layout_cover(pages[0], first_page_words or [])
    lines = _form_cards(_cover(cover))
    _recover_authority_label(lines)
    explicit = any(appeal.EXPLICIT_APPELLANT.match(line) for line in lines)
    parties = appeal._parties(lines, frozenset(), explicit)
    appellants = parties["Odwołujący"]
    if appellants:
        leader = next((p for p in appellants if "lider" in _fold(p["sublabel"])), appellants[0])
        if not record["Odwolujacy"]:
            record["Odwolujacy"] = [
                {
                    **{k: leader[k] for k in ("krs", "nip", "regon", "nazwa")},
                    "przez-pelnomocnika": 0,
                    "pelnomocnik": {"imie_nazwisko": None, "nazwa": None, "mail": None},
                }
            ]
        current = record["Odwolujacy"][0]
        # Sole traders are identified by the registered name following "pod firmą".
        printed = leader["nazwa"]
        trade = re.search(r"\bprowadz[\w]+ dzialalnosc gospodarcza pod firma\s+", _fold(printed))
        if trade and printed[: trade.start()].strip() in printed[trade.end() :]:
            printed = printed[trade.end() :]
        if "lider" in _fold(leader["sublabel"]) and re.search(r"wspolnie|konsorcjum", _fold(current["nazwa"])):
            current.update({k: leader[k] for k in ("nazwa", "krs", "nip", "regon")})
        if current["nazwa"] == leader["nazwa"] or re.match(r"^\s+u[ił]\. ", current["nazwa"].removeprefix(printed)):
            printed = re.sub(r"(?<=\w)-\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])", "-", printed)
            current["nazwa"] = re.sub(r"(?<=Sp\.) Z (?=o\.o\.)", " z ", printed)
        role = False
        block = []
        for line in lines:
            if label := appeal.SECTION_RE.match(line):
                role = appeal._party_role(label[1], explicit) == "Odwołujący"
            elif line.startswith("Pełnomocnik odwołującego:"):
                role = True
            elif not (
                _APPOINT.search(_fold(line))
                or appeal.EMPLOYER_LABEL.match(line)
                or appeal.CONTACT.search(line)
                or re.match(r"^adres (?:do|dla) doreczen|^adres poczty elektronicznej|^doreczen:", _fold(line))
            ) and appeal._ends_party(line):
                role = False
            if role:
                block.append(line)
        scan_pages = [page for i, page in enumerate(pages, 1) if i in ocr_pages]
        _registry_footer(current, scan_pages)
        _signed_mandate(current, scan_pages)
        # Some unnumbered consortium lists mark the leader on its address row.
        if re.search(r"konsorcjum", _fold(leader["nazwa"])):
            marked = [
                block[i - 1]
                for i, row in enumerate(block)
                if i and appeal.ADDRESS_RE.match(row) and re.search(r"\blider konsorcjum\b", _fold(row))
            ]
            if len(marked) == 1 and marked[0] in leader["nazwa"]:
                current["nazwa"] = marked[0]
        if rep := _representative(block, scan_pages):
            current["przez-pelnomocnika"] = 1
            current["pelnomocnik"].update({k: v for k, v in rep.items() if v})
    authorities = parties["Zamawiający"]
    if authorities:
        rows = _authority_rows(authorities, lines)
        existing = record["Zamawiajacy"]
        # A continuation sheet may hold further authorities or identifiers.
        if not existing:
            record["Zamawiajacy"] = rows
        elif len(rows) == len(existing):
            for previous, new in zip(existing, rows, strict=True):
                old_name = previous["nazwa"].lstrip(" _.").rstrip(" *|")
                compact = re.sub(r"(?<=\w)-\s+(?=\w)", "-", old_name)
                suffix = old_name.removeprefix(new["nazwa"]).lstrip(_TRIM)
                if compact == new["nazwa"] or (old_name.startswith(new["nazwa"]) and appeal.ADDRESS_RE.match(suffix)):
                    previous.update({k: v for k, v in new.items() if v is not None})
