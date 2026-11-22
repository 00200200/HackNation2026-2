"""Viewer panels built from the class list and a document's extraction trace."""

import json
from itertools import count

from shiny import ui

from .batch import Result
from .class_config import DocumentClass

ENGINE_NAMES = {
    "case repair": "inne pismo w sprawie",
    "rule": "reguły, tekst PDF",
    "ocr": "reguły, OCR",
    "model": "model",
    "rule or ocr": "reguły",
}
CHECK_NAMES = {
    "nip": "suma kontrolna NIP się nie zgadza",
    "regon": "suma kontrolna REGON się nie zgadza",
    "pesel": "PESEL jest niepoprawny",
    "iban": "suma kontrolna numeru rachunku się nie zgadza",
    "date_range": "data jest poza dozwolonym zakresem",
    "one_of": "wartości nie ma na liście dozwolonych",
}
NOTE_NAMES = {
    "confirmed by a sibling document": "potwierdzono w innym dokumencie sprawy",
    "no value extracted": "brak wartości",
    "derived code or flag, not a printed value": "kod lub znacznik wyliczony z treści",
    "value not found verbatim in the text read": "wartości nie ma dosłownie w odczytanym tekście",
    "producing engine not recorded": "nie wiadomo, która metoda podała wartość",
}


def display_name(definition: DocumentClass) -> str:
    return definition.name or definition.id.replace("_", " ")


def class_list(classes: list[DocumentClass], error: str | None) -> ui.Tag:
    if error:
        return ui.p(f"Błąd w konfiguracji klas: {error}", class_="class-error")
    rows = []
    for definition in classes:
        source = definition.source.name if definition.source else "?"
        state = source if definition.enabled else f"{source}, wyłączona (włącz: --enable {definition.id})"
        rows.append(ui.tags.li(ui.tags.strong(display_name(definition)), f" · {state}"))
    active = sum(definition.enabled for definition in classes)
    summary = ui.tags.summary(f"Aktywne klasy dokumentów: {active}")
    return ui.tags.details(summary, ui.tags.ul(*rows), class_="classes")


def _number(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def routing_reason(trace: dict | None) -> str:
    """One sentence saying which rule or cue chose the class."""
    routing = (trace or {}).get("routing")
    if not routing:
        return ""
    if routing["router"] in ("model", "model fallback"):
        return "Klasę wskazał model na podstawie pierwszej strony."
    if routing["router"] == "config":
        match = routing["match"]
        found = [f"„{cue['text']}” {'+' if cue['weight'] > 0 else ''}{_number(cue['weight'])}" for cue in match["cues"]]
        found += [f"„{line}”" for line in match["headings"] + match["required"]]
        reason = f"Klasę wskazał plik {routing['rule']}: " + ", ".join(found)
        if match["threshold"] is not None:
            reason += f". Wynik {_number(match['score'])} przy progu {_number(match['threshold'])}"
        return reason + "."
    cue = routing.get("cue") or {}
    if cue.get("line"):
        return f"Klasę wskazał nagłówek „{cue['line']}” na stronie {cue['page']}."
    if cue.get("note"):
        return "Klasę wskazała formuła pełnomocnictwa w akcie notarialnym."
    return "Klasę wskazały reguły klasyfikatora."


def warning_list(trace: dict | None) -> ui.Tag | None:
    warnings = (trace or {}).get("warnings") or []
    if not warnings:
        return None
    badges = []
    for warning in warnings:
        action = "usunięto z JSON" if warning["action"] == "null" else "zostawiono, sprawdź"
        problem = CHECK_NAMES.get(warning["check"], warning["check"])
        badges.append(
            ui.span(
                ui.tags.strong(warning["field"]),
                f" „{warning['value']}”: {problem}; {action}",
                class_="badge-warning",
            )
        )
    return ui.div(*badges, class_="checks", role="status")


def case_badges(warnings) -> ui.Tag | None:
    """Facts that disagree between the documents of one case folder, with the documents named."""
    if not warnings:
        return None
    badges = [
        ui.span(
            warning.message,
            " ",
            ui.tags.small(", ".join(name.as_posix() for name in warning.documents)),
            class_="badge-warning",
        )
        for warning in warnings
    ]
    return ui.div(ui.h3("Rozbieżności w dokumentach sprawy"), ui.div(*badges, class_="checks"), class_="case-checks")


# Messages of the PDF parsers for a file that is not a readable PDF.
DAMAGED_PDF = ("PdfminerException", "PDFSyntaxError", "No /Root object", "PdfiumError", "Failed to load", "EOF marker")


def outcome(result: Result) -> ui.Tag | None:
    """Plain Polish words for a document without fields: unreadable, or outside the known classes."""
    written = "{}" if result.text.strip() == "{}" else "pusty plik (0 B)"
    if result.error:
        if "no readable text" in result.error:
            reason = "Na stronach nie ma czytelnego tekstu, także po OCR."
        elif any(sign in result.error for sign in DAMAGED_PDF):
            reason = "Nie udało się odczytać pliku PDF. Plik może być uszkodzony, zaszyfrowany albo nie jest PDF-em."
        else:
            reason = "Nie udało się przetworzyć dokumentu."
        return ui.div(
            ui.p(f"{reason} Zapisano {written}."),
            ui.tags.details(ui.tags.summary("Szczegóły techniczne"), ui.tags.code(result.error)),
            class_="outcome",
        )
    if result.label is None and result.used_recovery:
        recovery = (result.trace or {}).get("recovery", "")
        if recovery.startswith("Could not read"):
            reason = "Nie udało się odczytać pliku, więc reguły nie miały czego sprawdzić"
        elif recovery.startswith("Used rules"):
            reason = "Przetwarzanie dokumentu nie powiodło się, a reguły nie rozpoznały jego typu"
        else:
            reason = "Przetwarzanie dokumentu i awaryjny odczyt regułami nie powiodły się"
        return ui.div(ui.p(f"{reason}, więc zapisano {written}."), class_="outcome")
    if result.label is None:
        return ui.div(ui.p(f"Nie rozpoznano typu dokumentu, więc zapisano {written}."), class_="outcome")
    return None


def _click(index: int) -> str:
    return f"Shiny.setInputValue('field', {index}, {{priority: 'event'}})"


def json_view(text: str, trace: dict | None, selected: int | None) -> ui.Tag:
    """The JSON exactly as written, with every value that has a known source clickable."""
    fields = (trace or {}).get("fields") or []
    flagged = {warning["field"] for warning in (trace or {}).get("warnings") or []}
    pieces = []
    leaves = count()

    def add(value, level: int) -> None:
        pad = "  " * level
        if isinstance(value, dict | list) and value:
            items = value.items() if isinstance(value, dict) else ((None, item) for item in value)
            pieces.append("{\n" if isinstance(value, dict) else "[\n")
            for n, (key, child) in enumerate(items):
                pieces.append(pad + "  " + ("" if key is None else json.dumps(key, ensure_ascii=False) + ": "))
                add(child, level + 1)
                pieces.append(",\n" if n < len(value) - 1 else "\n")
            pieces.append(pad + ("}" if isinstance(value, dict) else "]"))
            return
        literal = json.dumps(value, ensure_ascii=False)
        if isinstance(value, dict | list):
            pieces.append(literal)
            return
        index = next(leaves)
        field = fields[index] if index < len(fields) else None
        if field is None:
            pieces.append(literal)
            return
        classes = ["leaf"]
        classes += ["located"] if field["page"] else []
        classes += ["selected"] if index == selected else []
        classes += ["flagged"] if field["field"] in flagged else []
        title = f"Strona {field['page']}" if field["page"] else "Brak źródła na stronie"
        pieces.append(ui.span(literal, class_=" ".join(classes), title=title, onclick=_click(index)))

    if text.strip():
        add(json.loads(text), 0)
        pieces.append("\n")
    return ui.tags.pre(*pieces, class_="json-view")


def evidence(trace: dict | None, index: int | None) -> ui.Tag | None:
    fields = (trace or {}).get("fields") or []
    if index is None or not 0 <= index < len(fields):
        return ui.p("Kliknij wartość w JSON, aby zobaczyć jej źródło na stronie.", class_="trace-note")
    field = fields[index]
    engine = ENGINE_NAMES.get(field["engine"], field["engine"] or "nieznane źródło")
    where = f"strona {field['page']}" if field["page"] else "brak miejsca na stronie"
    notes = field.get("note", "").split("; ") if field.get("note") else []
    quote = f"„{field['snippet']}”" if field["snippet"] else "; ".join(NOTE_NAMES.get(n, n) for n in notes)
    return ui.p(ui.tags.strong(field["field"]), f" · {where} · {engine} · {quote}", class_="evidence")


def field_table(trace: dict | None) -> ui.Tag:
    if trace and trace.get("trace_error"):
        return ui.p(f"Nie udało się zebrać źródeł pól: {trace['trace_error']}", class_="trace-note")
    if not trace or not trace["class"]:
        return ui.p("Brak pól do wyjaśnienia.", class_="trace-note")
    rows = []
    for index, field in enumerate(trace["fields"]):
        page = field["page"]
        notes = field.get("note", "").split("; ") if field.get("note") else []
        # A snippet and a note can both apply, as when the source line is found but its engine was not recorded.
        named = "; ".join(NOTE_NAMES.get(note, note) for note in notes)
        source = "; ".join(part for part in (field["snippet"], named) if part)
        # A native button selects the field, as a click on its value in the JSON does, and works from the keyboard.
        show = ui.tags.button(
            str(page),
            type="button",
            class_="page-link",
            title=f"Pokaż źródło na stronie {page}",
            onclick=_click(index),
        )
        rows.append(
            ui.tags.tr(
                ui.tags.td(field["field"]),
                ui.tags.td(show if page else "–"),
                ui.tags.td(ENGINE_NAMES.get(field["engine"], field["engine"] or "–")),
                ui.tags.td(source),
            )
        )
    header = ui.tags.tr(*(ui.tags.th(name) for name in ("Pole", "Str.", "Źródło", "Fragment")))
    return ui.tags.table(ui.tags.thead(header), ui.tags.tbody(*rows))
