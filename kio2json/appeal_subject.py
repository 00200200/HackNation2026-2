"""Read an uncaptioned procurement subject in the same cover block as its reference."""

import re
from itertools import pairwise
from statistics import median

from .pdf_text import WordBox
from .power_of_attorney import LEGAL_FORM
from .receipt_layout import word_rows

_REFERENCE = re.compile(
    r"(?:znak(?: sprawy| postępowania)?|(?:nr\.?|numer) (?:referencyjny(?: sprawy)?|postępowania|zamówienia|sprawy)"
    r"|postępowani[uea] (?:nr\.?|numer))(?:\s*[:–-]\s*|\s+)(?P<value>(?=[\w./-]*\d)[\w./-]+)[.,]?",
    re.IGNORECASE,
)
# Action nouns and nominal descriptions of supplies, works or services.
_SUBJECT = re.compile(
    r"^[„«\"]?(?:zakup|dostaw[ay]|(?:prze|roz|od)?budowa|remont|renowacja|modernizacja|roboty|usług[ai]|"
    r"(?:zaprojekt|oprac|przygot|wykon|wyposaż|wdroż|utrzym|świadc|dostos|zagospodar)\w*nie|"
    r"organizacja|obsługa|instalacja|sieć|system|infrastruktura|kompleksow[ae] (?:usług[ai]|wykonanie))\b",
    re.IGNORECASE,
)
_NON_SUBJECT = re.compile(
    rf"@|\b{LEGAL_FORM}|\b(?:spółk\w*|KRS|NIP|REGON|PESEL|kancelari\w*|pełnomocni\w*|"
    r"odwołani\w*|dowod\w*|zarzut\w*|skarg\w*|załącznik\w*|uzasadnieni\w*|procesow\w*|"
    r"sygnatur\w*|koszt\w* (?:sprawy|postępowania)|(?:niniejsz\w*|poprzedni\w*) spraw\w*)\b",
    re.IGNORECASE,
)
_QUALIFIER = r"(?:(?:wcześniejsz|przykład|poprzedni|historyczn|porównawcz)\w*|inn(?:e\w*|y\w*|a|ą))"
_PROCEEDING = r"(?:postępowani|przetarg|zamówieni|spraw|procedur)\w*"
_OTHER_PROCEDURE = re.compile(rf"\b(?:{_QUALIFIER} {_PROCEEDING}|{_PROCEEDING} {_QUALIFIER})\b", re.IGNORECASE)


def unlabelled_title(boxes: list[WordBox], reference: str) -> str | None:
    rows, height = word_rows(boxes)
    lines = [" ".join(word.text for word in row) for row in rows]
    anchors = [
        (i, match["value"].rstrip(".,")) for i, line in enumerate(lines) if (match := _REFERENCE.fullmatch(line))
    ]
    if len(anchors) != 1 or anchors[0][1] != reference:
        return None
    end = anchors[0][0]
    if not end:
        return None

    # A larger vertical gap separates paragraphs even when both start at the same margin.
    tops = [row[0].y0 for row in rows]
    steps = [b - a for a, b in pairwise(tops) if height * 0.7 < b - a <= height * 2]
    pitch = median(steps) if steps else height
    start = end
    for i in range(end - 1, max(-1, end - 6), -1):
        if tops[i + 1] - tops[i] > 1.25 * pitch or abs(rows[i][0].x0 - rows[end][0].x0) > height:
            break
        if any(b.x0 - a.x1 > 2 * height for a, b in pairwise(rows[i])):
            return None
        if _NON_SUBJECT.search(lines[i]):
            return None
        if lines[i].endswith(":"):
            if re.search(_PROCEEDING, lines[i], re.IGNORECASE) and re.search(_QUALIFIER, lines[i], re.IGNORECASE):
                return None
            break
        start = i

    title = " ".join(lines[start:end])
    if not _SUBJECT.match(title) or not 3 <= len(title.split()) <= 80:
        return None
    if _OTHER_PROCEDURE.search(" ".join(lines[max(0, start - 1) : end])):
        return None
    return title
