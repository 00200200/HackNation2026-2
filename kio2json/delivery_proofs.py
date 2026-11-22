"""Identify the author's message inside electronic delivery and validation forms."""

import re

from .common import POLISH_FOLD

FORM_TITLE = re.compile(
    r"(?m)^[ \t]*(?:(?:epuap|e[- ]?doreczenia)\s*[-–—:|]?\s*)?"
    r"(?:(?:urzedowe\s+)?(?:poswiadczenie|potwierdzenie|dowod)\s+"
    r"(?:przedlozenia|nadania|wyslania|otrzymania|odbioru|doreczenia|dostarczenia)\b"
    r"|up[po]\b|pismo\s+ogolne\b|(?:raport|protokol|wynik|poswiadczenie)\s+"
    r"(?:(?:z|o)\s+)?(?:weryfikacji|walidacji|sprawdzenia)\b[^\n]{0,40}podpis|raport\s+walidacyjny\b)"
)
TRANSPORT_FIELD = re.compile(
    r"\b(?:epuap|e[- ]?doreczen\w*|ae:pl|adresat|nadawca|zalacznik\w*|"
    r"(?:identyfikator|numer|data|czas) (?:dokumentu|pisma|przesylki|wyslania|nadania|doreczenia|wplywu)|"
    r"(?:wynik|status) (?:podpisu|weryfikacji|walidacji)|certyfikat\w*|podpisujac\w*|nazwa pliku)\b"
)
ATTACHMENTS = re.compile(
    r"^(?:(?:lista|wykaz|spis|podglad|opis|fragment|cytat|tresc) (?:z )?(?:zalacznik|plik)\w*\b"
    r"|zalacznik(?:i|ow)?\b|(?:nazwa|tytul) (?:pliku|dokumentu|zalacznika)\b)"
)
BODY = re.compile(
    r"^(?:tresc(?: (?:pisma|wniosku|dokumentu|wiadomosci|oswiadczenia))?|wiadomosc)"
    r"\s*(?:[:|]\s*|$)"
)
METADATA = re.compile(
    r"^(?:temat|tytul|przedmiot|rodzaj (?:dokumentu|pisma)|nadawca|adresat|identyfikator|"
    r"skrot|odcisk|cytat|streszczenie|nazwa pliku)\s*(?:[:|]\s*|$)"
)
REPORTED = re.compile(
    r"\b(?:w ktorym|zgodnie z ktorym|ze (?:wykonawca|odwolujacy|mocodawca|spolka)\b|"
    r"w zalacz\w*|(?:zalaczon|przeslan)\w* (?:pism|plik|dokument)\w*)\b"
)
QUOTATION = re.compile(r'[„“«"].*?[”»"]', re.DOTALL)
APPEAL_ACT = re.compile(
    r"(?<!nie )\b(?:wnosze|wnosimy|wnosi|wnosza|skladam|skladamy|sklada)\s+(?:(?:niniejsze?|niniejszym)\s+)?odwolanie\b"
    r"|(?<!nie )\b(?:zaskarzam(?:y)?|zarzucam(?:y)?)\s+(?:czynnosc|zamawiajac|naruszenie)\w*"
)
GRANT_ACT = re.compile(
    r"(?<!nie )\b(?:udziel(?:a|am|amy|aja)\b[^.!?]{0,90}\b(?:pelnomocnictw|umocowani|upowaznieni)"
    r"|(?:upowaznia(?:m|my|ja)?|ustanawia(?:m|my|ja)?|umocowuj(?:e|emy|a))\b[^.!?]{0,120}\b(?:do|pelnomocni)\w*)"
)


def message_pages(pages: list[str]) -> list[str] | None:
    """Return body rows only when the opening page identifies a transmission form."""
    opening = pages[0][:1800].casefold().translate(POLISH_FOLD)
    title = FORM_TITLE.search(opening)
    if not title or not TRANSPORT_FIELD.search(pages[0].casefold().translate(POLISH_FOLD)):
        return None
    # A proof listed among the filing's exhibits is not its document heading.
    if any(ATTACHMENTS.match(row.strip()) for row in opening[: title.start()].splitlines()):
        return None
    result = []
    attachments = False
    for page in pages[:2]:
        rows = []
        detached_value = False
        for row in QUOTATION.sub(" ", page).splitlines():
            line = row.strip().casefold().translate(POLISH_FOLD)
            if not line:
                continue
            if ATTACHMENTS.match(line):
                attachments = True
            elif body := BODY.match(line):
                attachments = False
                rows.append(row.strip()[body.end() :])
            elif field := METADATA.match(line):
                detached_value = field.end() == len(line)
                continue
            elif not (attachments or detached_value or FORM_TITLE.match(line)):
                rows.append(row)
            detached_value = False
        result.append("\n".join(rows))
    return result


def filing_act(body: list[str]) -> str | None:
    text = " ".join(" ".join(body).casefold().translate(POLISH_FOLD).split())
    for clause in re.split(r"[.!?;]", text):
        # The sender may describe what the enclosed document declares.
        assertion = REPORTED.split(clause, maxsplit=1)[0]
        if APPEAL_ACT.search(assertion):
            return "appeal"
        if GRANT_ACT.search(assertion):
            return "power_of_attorney"
    return None
