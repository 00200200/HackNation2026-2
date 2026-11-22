"""Local document viewer: python -m kio2json.gui [--classes PATH] [--enable ID] [--host H] [--port P] [--no-browser]."""

import argparse
import asyncio
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory

from shiny import App, Inputs, Outputs, Session, reactive, render, req, run_app, ui

from kio2json.class_config import ClassSources, DocumentClass, add_class_options, class_sources, parse_classes
from kio2json.gui_explain import (
    case_badges,
    display_name,
    evidence,
    field_table,
    json_view,
    outcome,
    routing_reason,
    warning_list,
)
from kio2json.gui_explain import class_list as class_panel
from kio2json.gui_files import Document, analyze, archive, folder_sources, page_count, page_image, upload_sources

# Class files are read again for every analysis, so a class file added to a --classes directory
# applies on the next click.
options = argparse.Namespace(classes=[], enable=[], host="127.0.0.1", folder_root=None)
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def load_classes() -> tuple[list[DocumentClass], str | None, str, ClassSources | None]:
    """The class set for one run, an error message, a cache key, and the class files for workers.

    The key changes with any class file, every KIO_* setting from the environment or .env and the parsed
    profiles, so a cached result never outlives the settings it was read with. Being a digest, it does not
    reveal the API key it covers.
    """
    try:
        sources = class_sources(extra=options.classes, enable=options.enable)
        classes = parse_classes(sources)
    except (OSError, ValueError) as error:
        return [], str(error), "", None
    dotenv = Path(".env")
    state = (
        sorted(sources.files.items()),
        sorted(sources.enable),
        [(definition.id, definition.profile) for definition in classes],
        sorted((name, value) for name, value in os.environ.items() if name.startswith("KIO_")),
        dotenv.read_bytes() if dotenv.is_file() else b"",
    )
    return classes, None, hashlib.sha256(repr(state).encode()).hexdigest(), sources


# PDFium must never be called simultaneously from multiple threads or sessions.
pdf_worker = ThreadPoolExecutor(max_workers=1)
# Documents are read in worker processes, as in the CLI, so a large folder is not read one by one.
WORKERS = min(4, os.process_cpu_count() or 1)

app_ui = ui.page_fluid(
    ui.include_css(Path(__file__).with_name("gui.css")),
    ui.tags.header(ui.h1("Odwołania2json"), ui.span("Analiza dokumentów KIO")),
    ui.div(
        ui.tags.aside(
            ui.h2("Dokumenty"),
            ui.input_radio_buttons(
                "mode", "Źródło plików", {"upload": "Wybierz pliki", "folder": "Otwórz folder"}, inline=True
            ),
            ui.panel_conditional(
                "input.mode === 'upload'",
                ui.input_file(
                    "files",
                    "Pliki PDF albo archiwum ZIP ze sprawami",
                    multiple=True,
                    accept=[".pdf", ".zip"],
                    button_label="Wybierz pliki…",
                    placeholder="Nie wybrano plików",
                ),
                ui.output_text("upload_summary"),
                ui.input_text("case", "Nazwa sprawy w archiwum", "sprawa"),
            ),
            ui.panel_conditional(
                "input.mode === 'folder'",
                ui.input_text("folder", "Ścieżka do folderu", "input"),
                ui.output_text("folder_hint", container=ui.p),
            ),
            # A task button stays disabled while its run is in progress, so a second click cannot repeat OCR.
            ui.input_task_button("run", "Analizuj dokumenty", label_busy="Trwa analiza…"),
            ui.div(ui.output_text("notice"), role="status", class_="notice"),
            ui.output_ui("class_list"),
            ui.panel_conditional(
                "output.count > 0",
                ui.tags.hr(),
                ui.input_select("document", "Dokument do podglądu", {}),
                ui.download_button("download", "Pobierz wyniki (.zip)"),
                ui.p("Program czyta tekst z PDF. Strony bez czytelnego tekstu odczytuje przez OCR.", class_="method"),
            ),
        ),
        ui.tags.main(
            ui.panel_conditional(
                "!output.count || output.count === '0'",
                ui.h2("Podgląd analizy"),
                ui.p("Wybierz dokumenty i kliknij „Analizuj dokumenty”, aby porównać plik PDF z wynikiem."),
                class_="empty",
            ),
            ui.panel_conditional(
                "output.count > 0",
                ui.output_text("classification", container=ui.h2),
                ui.output_text("routing", container=ui.p),
                ui.output_ui("consistency_warnings"),
                ui.div(
                    ui.tags.section(
                        ui.div(ui.h3("Dokument źródłowy"), ui.output_ui("page_picker"), class_="panel-head"),
                        ui.output_ui("preview"),
                        class_="viewer",
                    ),
                    ui.tags.section(
                        ui.div(ui.h3("Wynik JSON"), ui.output_text("target"), class_="panel-head"),
                        ui.output_ui("result_json"),
                        ui.output_ui("field_evidence"),
                        ui.output_ui("checks"),
                        ui.h3("Źródła pól", class_="trace-head"),
                        ui.output_ui("trace_table"),
                        class_="viewer",
                    ),
                    class_="comparison",
                ),
            ),
        ),
        class_="workspace",
    ),
    ui.div(ui.output_text("count"), hidden=True),
    title="Odwołania2json",
    lang="pl",
)


def server(input: Inputs, output: Outputs, session: Session):
    documents = reactive.value(list[Document]())
    message = reactive.value("")
    classes = reactive.value(load_classes()[:2])
    field = reactive.value(None)
    scratch = TemporaryDirectory(prefix="odwolania-")
    session.on_ended(lambda: scratch.cleanup())

    @reactive.effect
    @reactive.event(input.run)
    async def analyze_files():
        nonlocal scratch
        documents.set([])
        scratch.cleanup()
        scratch = TemporaryDirectory(prefix="odwolania-")
        loaded, error, class_key, class_files = load_classes()
        classes.set((loaded, error))
        if error:
            message.set("Popraw plik klasy i spróbuj ponownie.")
            return
        loop = asyncio.get_running_loop()
        try:
            with ui.Progress() as progress:
                progress.set(message="Przygotowanie dokumentów…")
                # Listing a folder or unpacking a ZIP can take a while, so it runs off the event loop too.
                if input.mode() == "folder":
                    if options.folder_root is None and options.host not in LOOPBACK:
                        raise ValueError("Na tym serwerze można tylko wgrać pliki PDF albo archiwum ZIP.")
                    sources = await loop.run_in_executor(
                        pdf_worker, folder_sources, input.folder(), options.folder_root
                    )
                else:
                    files = input.files() or []
                    sources = await loop.run_in_executor(
                        pdf_worker, upload_sources, input.case().strip(), files, Path(scratch.name)
                    )
                total = len(sources)
                progress.max = total
                progress.set(0, message="Trwa analiza dokumentów…", detail=f"0 z {total}")

                def report(done: int, name: Path) -> None:
                    # Called from the analysis thread; Shiny sends progress from its event loop.
                    detail = f"{done} z {total}: {name.as_posix()}"
                    loop.call_soon_threadsafe(progress.set, done, "Trwa analiza dokumentów…", detail)

                analysis = partial(analyze, class_files=class_files, workers=WORKERS, on_progress=report)
                results = await loop.run_in_executor(
                    pdf_worker, analysis, sources, Path(scratch.name), loaded, class_key
                )
        except (ValueError, OSError) as error:
            message.set(str(error))
            return
        documents.set(results)
        failures = sum(doc.result.error is not None for doc in results)
        message.set(f"Liczba dokumentów: {len(results)}." + (f" Błędy odczytu: {failures}." if failures else ""))
        choices = {str(i): doc.name.as_posix() for i, doc in enumerate(results)}
        ui.update_select("document", choices=choices, selected="0")

    @render.text
    def folder_hint():
        if options.folder_root is None:
            return "Wskaż folder ze sprawami lub folder jednej sprawy."
        return f"Ścieżka liczy się od folderu {options.folder_root}. Puste pole otwiera cały ten folder."

    @render.text
    def upload_summary():
        files = input.files() or []
        if len(files) == 1:
            return files[0]["name"]
        return f"Wybrane pliki: {len(files)}" if files else "Nie wybrano plików."

    @render.text
    def notice():
        return message()

    @render.ui
    def class_list():
        return class_panel(*classes())

    @output(suspend_when_hidden=False)
    @render.text
    def count():
        return str(len(documents()))

    @reactive.calc
    def selected() -> Document:
        items = documents()
        req(items)
        index = int(input.document() or 0)
        return items[index if 0 <= index < len(items) else 0]

    @reactive.effect
    @reactive.event(input.document, documents)
    def forget_field():
        field.set(None)

    @reactive.effect
    @reactive.event(input.field)
    def choose_field():
        index = input.field()
        fields = (selected().result.trace or {}).get("fields") or []
        field.set(index)
        if 0 <= index < len(fields) and fields[index]["page"]:
            ui.update_select("page", selected=str(fields[index]["page"]))

    @render.text
    def classification():
        result = selected().result
        names = {definition.id: display_name(definition) for definition in classes()[0]}
        if result.error:
            # The reason and the raw error appear beside the JSON, under "Szczegóły techniczne".
            return "Nie udało się odczytać dokumentu"
        if result.used_recovery:
            if result.label is None:
                return "Brak wyniku po awaryjnej próbie odczytu regułami"
            return f"{names.get(result.label, result.label)} (reguły awaryjne)"
        if result.label is None:
            return "Nie rozpoznano typu dokumentu"
        return names.get(result.label, result.label.replace("_", " "))

    @render.text
    def routing():
        return routing_reason(selected().result.trace)

    @render.ui
    def checks():
        return warning_list(selected().result.trace)

    @render.ui
    def trace_table():
        return field_table(selected().result.trace)

    @render.text
    def target():
        return selected().name.with_suffix(".json").as_posix()

    @render.ui
    def consistency_warnings():
        return case_badges(selected().warnings)

    @render.ui
    def result_json():
        result = selected().result
        return outcome(result) or json_view(result.text, result.trace, field())

    @render.ui
    def field_evidence():
        result = selected().result
        return None if outcome(result) else evidence(result.trace, field())

    @reactive.calc
    async def pages():
        try:
            return await asyncio.get_running_loop().run_in_executor(pdf_worker, page_count, selected().snapshot)
        except (OSError, ValueError, RuntimeError):
            return 0

    @render.ui
    async def page_picker():
        total = await pages()
        if total:
            return ui.input_select("page", "Strona", {str(n): f"{n} / {total}" for n in range(1, total + 1)})

    @render.ui
    async def preview():
        doc = selected()
        total = await pages()
        if total:
            number = max(1, min(int(input.page() or 1), total))
            fields = (doc.result.trace or {}).get("fields") or []
            index = field()
            chosen = fields[index] if index is not None and 0 <= index < len(fields) else None
            boxes = chosen["boxes"] if chosen and chosen["page"] == number else []
            try:
                image = await asyncio.get_running_loop().run_in_executor(
                    pdf_worker, page_image, doc.snapshot, number, boxes
                )
                return ui.img(src=image, alt=f"{doc.name.name}, strona {number}")
            except (OSError, ValueError, RuntimeError):
                pass
        return ui.p("Nie udało się wyświetlić strony PDF. Plik może być uszkodzony.")

    @render.download_button(filename="wyniki.zip", media_type="application/zip")
    def download():
        yield archive(documents())


app = App(app_ui, server)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="python -m kio2json.gui", description="Local document viewer")
    add_class_options(parser)
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on; 0.0.0.0 serves other machines")
    parser.add_argument("--port", type=int, default=8000, help="port to listen on (default: 8000)")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser, for servers and containers")
    parser.add_argument(
        "--folder-root",
        type=Path,
        help="folder whose cases the viewer may open; without it, a host other than localhost allows uploads only",
    )
    parser.parse_args(namespace=options)
    run_app(app, host=options.host, port=options.port, launch_browser=not options.no_browser, dev_mode=False)
