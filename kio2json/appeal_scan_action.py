"""Read the first challenged act in the opening of a scanned appeal."""

import re
from bisect import bisect_right
from collections import Counter
from collections.abc import Collection
from datetime import date

from .appeal import PLACE_DATE_RE, REASONS
from .appeal_charges import ACTS
from .common import MONTHS, date_pattern, squash, to_iso

# One character maps to one character, so matches retain the source-page offsets.
_ACCENTS = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
_FILING = re.compile(
    r"\b(?:wnos(?:ze|za|imy|i)|sklad(?:am|amy|a))\s+(?:niniejsz(?:e|ym)\s+)?odwolanie\s+(?:wobec|od|na)\b",
    re.IGNORECASE,
)
_FIRST_ITEM = re.compile(r"^[ \t]*[1Il|][.)][ \t]+", re.MULTILINE)
_END_ITEM = re.compile(
    r";|(?:^|(?<=\s))(?:2|II)[.)]\s+|\b(?:zaskarzonym\s+czynnosciom|zarzucam|wnosze\s+o|uzasadnienie)\b",
    re.MULTILINE | re.IGNORECASE,
)
# Reuse the general dictionary cues, adding objects which can be expressed
# through a party role or a longer name for the specification.
_CUES = {
    **{reason: pattern.translate(_ACCENTS) for reason, pattern in ACTS.items()},
    2: r"wybor\w*\s+(?:jako\s+)?(?:najkorzystniejsz\w*\s+)?ofert\w*",
    3: r"wyklucz\w*\s+(?:wykonawc\w*|odwolujac\w*)",
    4: r"specyfikacj\w*|\bsi?wz\b|opis\w*\s+kryteri\w*\s+oceny\s+ofert",
    5: r"(?:modyfikacj\w*|zmian\w*)\s+(?:tresci\s+)?(?:si?wz|specyfikacj\w*)",
    12: r"(?:wzor\w*|projekt\w*|postanowien\w*)\s+umow\w*",
}
# A list heading can supply the negation for its numbered first subitem.
_OMISSION = r"(?:zaniecha\w*|brak\w*)\s*:?\s*(?:\([1Il]\)\s*)?"
for omission, positive in ((7, 1), (8, 3), (10, 9)):
    _CUES[omission] = rf"(?:{_OMISSION}(?:{_CUES[positive]})|{_CUES[omission]})"
_ACT = re.compile("|".join(rf"(?P<r{key}>\b(?:{expr}))" for key, expr in _CUES.items()), re.IGNORECASE)
_DAY = date_pattern(r"[-/.][ \t]*").translate(_ACCENTS)
_WHEN = re.compile(
    rf"\b(?:w\s+dniu|dnia|pismem\s+z|zawiadomieni\w*\s+z|opublikowan\w*)\s+(?P<day>{_DAY})",
    re.IGNORECASE,
)
_MONTH_SPELLINGS = {month.translate(_ACCENTS): month for month in MONTHS}
_DATE_LINK = re.compile(
    r"\b(?:opublikow|przekaz|dorecz|zawiadom|poinform|oglos|powzi|uzysk|"
    r"udziel|dokonan|podjet|zamieszcz)\w*\b",
    re.IGNORECASE,
)


def _iso(day: str) -> str | None:
    value = squash(re.sub(r"(?<=[.\-])\s+(?=\d)", "", day.lower().replace("/", "-")))
    parts = value.split()
    if len(parts) == 3:
        parts[1] = _MONTH_SPELLINGS[parts[1]]
        value = " ".join(parts)
    return to_iso(value)


def apply_action(record: dict, pages: list[str], ocr_pages: Collection[int]) -> None:
    """Apply OCR rules only when the supporting field evidence comes from OCR."""
    if not pages or not ocr_pages or "OdwolanieKIO" not in record:
        return
    action = record["OdwolanieKIO"]
    if 1 in ocr_pages:
        for line in pages[0].splitlines()[:20]:
            clean = line.strip(" \t|/*,:;—–\"'„”")
            if re.match(r"miejscowo[śs][ćc]\s*:", clean, re.IGNORECASE):
                clean = re.sub(r"[„'\"](?=\d)", "", clean.partition(":")[2]).strip()
            if header := PLACE_DATE_RE.fullmatch(clean):
                if day := to_iso(header[2]):
                    action.update(data=day, miejscowosc=header[1])
                break

    text = "\n".join(pages).translate(_ACCENTS)
    page_ends = []
    offset = 0
    for page in pages:
        offset += len(page) + 1
        page_ends.append(offset)

    def scanned(match: re.Match) -> bool:
        first = bisect_right(page_ends, match.start()) + 1
        last = bisect_right(page_ends, match.end() - 1) + 1
        return all(p in ocr_pages for p in range(first, last + 1))

    act, end = _first_act(text, action["czynnosc_powod_id"])
    reason = int(act.lastgroup[1:]) if act else None
    if act and scanned(act):
        if action["czynnosc_powod_id"] != reason:
            action["czynnosc_dzien"] = None
        action.update(czynnosc_powod_id=reason, czynnosc_opis=REASONS[reason])
    decision_object = None
    if act and action["czynnosc_powod_id"] == reason:
        previous = act.end()
        for match in _WHEN.finditer(text, act.end(), end):
            before = text[previous : match.start()].strip(" \t\n,:")
            previous = match.end()
            named_bidder = reason in (1, 2, 3, 7, 8) and re.fullmatch(
                r"(?:(?:spolki|wykonawcy)\s+)?[A-Z][\w-]*(?: [A-Z][\w-]*){0,3}", before
            )
            if before and not (_DATE_LINK.search(before) or named_bidder):
                continue
            if re.search(r"\b(?:zlozon\w*|ustaw\w*|rozporzadzeni\w*|dyrektyw\w*)\s*z?$", before, re.IGNORECASE):
                continue
            if scanned(match) and (day := _iso(match["day"])):
                action["czynnosc_dzien"] = day
                if re.search(r"poinform|zawiadom|przekaz|powzi|dorecz", before, re.IGNORECASE):
                    decision_object = None
                    break
                if scanned(act):
                    decision_object = squash(before).casefold()
    if not action["czynnosc_dzien"]:
        action["czynnosc_dzien"] = _notice_date(text, action["czynnosc_powod_id"], scanned)
    elif decision_object is not None:
        # A later timeliness paragraph can explicitly name the same act and
        # give its communication date separately from the decision date.
        notice = _notice_date(text, reason, scanned, decision=(end, decision_object))
        if notice and notice >= action["czynnosc_dzien"]:
            action["czynnosc_dzien"] = notice
    if 1 in ocr_pages and action["data"] and action["czynnosc_dzien"]:
        # A repeated transmission timestamp can corroborate a one-digit OCR
        # error in the dateline year when it fits the independently dated act.
        timestamps = Counter(
            m[1]
            for i, page in enumerate(pages, 1)
            if i in ocr_pages and (m := re.match(r"^\s*(\d{4}-\d{2}-\d{2})\s+\d{1,2}:\d{2}\b", page))
        )
        printed = action["data"]
        for stamp, count in timestamps.items():
            if count < 2 or stamp[4:] != printed[4:] or not to_iso(stamp):
                continue
            days_after_act = (date.fromisoformat(stamp) - date.fromisoformat(action["czynnosc_dzien"])).days
            changed_digits = sum(a != b for a, b in zip(stamp[:4], printed[:4], strict=True))
            if changed_digits == 1 and 0 <= days_after_act <= 31:
                action["data"] = stamp


def _first_act(text: str, existing: int | None) -> tuple[re.Match | None, int]:
    # In a structured appeal the first item identifies the act itself. In prose,
    # a generic introduction can name the entire specification before the actual
    # allegation identifies one clause of the draft contract or its annexes.
    filing = _FILING.search(text)
    act = None
    end = 0
    if filing:
        start = filing.end()
        end = min(start + 1600, len(text))
        if stop := _END_ITEM.search(text, start, end):
            end = stop.start()
        bullets = re.finditer(r"(?m)^[ \t]*[-–—]\s+", text[start:end])
        next(bullets, None)
        if second := next(bullets, None):
            end = start + second.start()
        item = _FIRST_ITEM.search(text, start, end)
        act = _ACT.search(text, item.end() if item else start, end)
        if act and (item or re.match(r"[;:\s.]*(?:2|II)[.)]\s", text[end : end + 30])):
            return act, end

    allegation = re.search(
        r"\b(?:zarzucam\s+zamawiajacemu,?\s+ze\s+dokonal|zwiezle\s+przedstawienie\s+zarzutow|"
        r"wskazanie\s+naruszen)\b",
        text,
        re.IGNORECASE,
    )
    if allegation:
        start = allegation.end()
        limit = min(start + 800, len(text))
        if stop := re.search(r";|\s(?:2|II)[.)]\s|\bwnosz\w*\s+o\b", text[start:limit], re.IGNORECASE):
            limit = start + stop.start()
        if first := _ACT.search(text, start, limit):
            # "Część ... SWZ – opis przedmiotu" identifies the particular annex.
            if (
                first.lastgroup == "r4"
                and (annex := _ACT.search(text, first.end(), min(first.end() + 55, limit)))
                and annex.lastgroup in {"r11", "r12"}
            ):
                first = annex
            return first, limit
    if act and (existing is None or existing == int(act.lastgroup[1:])):
        return act, end
    return None, 0


_DAY_CAPTURE = rf"(?P<day>{_DAY})(?:\s*(?:r\.|roku))?"
# Each expression names the event starting the appeal period or names the
# document that was published. A deadline to file is a separate event.
_NOTIFICATION = (
    rf"{_DAY_CAPTURE}\s+stanowi\s+poczatkow\w*\s+dat\w*\s+biegu\s+terminu",
    (
        rf"\b(?:do\s+publicznej\s+wiadomosci|informacj\w*\s+stanowi\w*\s+podstawe\s+wniesienia\s+odwolania)"
        rf"[^;!?]{{0,90}}?\b(?:przekazan\w*|powzi\w*)\s+w\s+dniu\s+{_DAY_CAPTURE}"
    ),
    rf"\b(?:dnia|w\s+dniu)\s+{_DAY_CAPTURE}\s+odwolujac\w*\s+(?:otrzym\w*|powzi\w*)\s+informacj\w*\s+o\b",
    rf"\bodwolujac\w*\s+w\s+dniu\s+{_DAY_CAPTURE}[^;!?]{{0,200}}?\bpowzi\w*\s+informacj\w*\s+o\b",
    rf"\bpismem\s+z\s+dnia\s+{_DAY_CAPTURE}\s+otrzyman\w*\s+w\s+tym\s+samym\s+dniu",
    (
        rf"{_DAY_CAPTURE}\s*\((?:wtedy\s+tez|tego\s+samego\s+dnia)\s+[^;!?()]{{0,40}}?"
        rf"\b(?:zawiadom\w*|przekaz\w*|rozesl\w*|powiadom\w*)\b"
    ),
)
_PUBLICATION = (
    (
        rf"\b(?:ogloszenie\s+si?wz|(?:wyjasnie\w*\s+(?:tresci\s+)?si?wz|dokumentacj\w*\s+przetargow\w*)"
        rf"[^;!?]{{0,50}}?\b(?:opublikowan\w*|udostepnion\w*)|zamiescil\s+ogloszenie\s+wraz\s+z\s+dokumentami)"
        rf"[^;!?]{{0,60}}?\b(?:w\s+dniu|dnia)\s+{_DAY_CAPTURE}"
    ),
)
_CONTRACT_NOTICE = (
    (
        rf"\b(?:ogloszenie\s+o\s+(?:zamowieniu|postepowaniu)[^;!?]{{0,45}}?(?:opublikow\w*|ukazalo\s+sie)"
        rf"[^;!?]{{0,80}}?\b(?:dnia|z\s+data)|data\s+opublikowania\s+w\s+(?:Dz\.\s*U\.\s*UE|BZP|TED)\s*:)\s+{_DAY_CAPTURE}"
    ),
)


def _notice_date(text, reason, scanned, *, decision=None):
    patterns = _NOTIFICATION
    if reason in (4, 5, 6, 11, 12):
        patterns += _PUBLICATION
    if reason in (4, 11, 12) and re.search(
        r"termin\w*[^;!?]{0,90}\b(?:ogloszen\w*|si?wz|publikacji)\b|"
        r"(?:od|wobec)\s+(?:postanowien|tresci)\s+ogloszenia\s+o\s+zamowieniu",
        text,
        re.IGNORECASE,
    ):
        patterns += _CONTRACT_NOTICE
    if reason == 10 and re.search(r"wszczeci\w*\s+(?:nowego\s+)?postepowania", text, re.IGNORECASE):
        patterns += (rf"\bpostepowanie\s+(?:zostalo\s+)?opublikowan\w*[^;!?]{{0,80}}?\bw\s+dniu\s+{_DAY_CAPTURE}",)
    named_dates = set()
    for pattern in patterns:
        dates = set()
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if not scanned(match):
                continue
            subject = None
            if match[0].split()[-1].casefold() == "o":
                start = re.compile(r"\s*").match(text, match.end()).end()
                subject = _ACT.match(text, start)
                if subject and (not scanned(subject) or (reason is not None and int(subject.lastgroup[1:]) != reason)):
                    continue
            if decision is not None:
                first_end, object_text = decision
                if subject is None or match.start() < first_end:
                    continue
                # Keep the full object qualification. Two bidders can both
                # challenge a rejection, and a notice about one cannot date the other.
                notice_object = re.split(r"[.;!?\n]", text[subject.end() :], maxsplit=1)[0]
                competing = any(m.lastgroup == subject.lastgroup for m in _ACT.finditer(text, first_end, match.start()))
                if competing or squash(notice_object).casefold() != object_text:
                    continue
            if day := _iso(match["day"]):
                dates.add(day)
        if decision is not None:
            named_dates.update(dates)
        elif len(dates) == 1:
            return dates.pop()
    return named_dates.pop() if len(named_dates) == 1 else None
