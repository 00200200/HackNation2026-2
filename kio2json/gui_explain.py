"""Viewer panels built from the class list and a document's extraction trace."""

from shiny import ui

from .class_config import DocumentClass

ENGINE_NAMES = {"rule": "reguły, tekst PDF", "ocr": "reguły, OCR", "model": "model", "rule or ocr": "reguły"}
CHECK_NAMES = {
    "nip": "suma kontrolna NIP się nie zgadza",
    "regon": "suma kontrolna REGON się nie zgadza",
    "pesel": "PESEL jest niepoprawny",
    "iban": "suma kontrolna numeru rachunku się nie zgadza",
    "date_range": "data jest poza dozwolonym zakresem",
    "one_of": "wartości nie ma na liście dozwolonych",
}
NOTE_NAMES = {
    "no value extracted": "brak wartości",
    "derived code or flag, not a printed value": "kod lub znacznik wyliczony z treści",
    "value not found verbatim in the text read": "wartości nie ma dosłownie w odczytanym tekście",
    "producing engine not recorded": "nie wiadomo, która metoda podała wartość",
    "corrected from another document in the case folder": "poprawione według innego dokumentu sprawy",
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
    items = []
    for warning in warnings:
        action = "wartość usunięta z JSON" if warning["action"] == "null" else "wartość zachowana, sprawdź ją"
        problem = CHECK_NAMES.get(warning["check"], warning["check"])
        items.append(ui.tags.li(f"{warning['field']} = „{warning['value']}”: {problem}, {action}."))
    return ui.div(ui.h3("Uwagi"), ui.tags.ul(*items), class_="checks")


def field_table(trace: dict | None) -> ui.Tag:
    if trace and trace.get("trace_error"):
        return ui.p(f"Nie udało się zebrać źródeł pól: {trace['trace_error']}", class_="trace-note")
    if not trace or not trace["class"]:
        return ui.p("Brak pól do wyjaśnienia.", class_="trace-note")
    rows = []
    for field in trace["fields"]:
        page = field["page"]
        notes = field.get("note", "").split("; ") if field.get("note") else []
        source = field["snippet"] or "; ".join(NOTE_NAMES.get(note, note) for note in notes)
        # A native button opens the page, so a keyboard user can reach it with Tab, Enter and Space.
        show = ui.tags.button(
            str(page),
            type="button",
            class_="page-link",
            title=f"Pokaż stronę {page}",
            onclick=f"Shiny.setInputValue('trace_page', {page}, {{priority: 'event'}})",
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
