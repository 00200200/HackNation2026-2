"""Local document viewer. Start with python -m kio2json.gui."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from shiny import App, Inputs, Outputs, Session, reactive, render, req, run_app, ui

from kio2json.gui_files import Document, analyze, archive, folder_sources, page_count, page_image, upload_sources

CLASS_NAMES = {
    "appeal": "Odwołanie",
    "power_of_attorney": "Pełnomocnictwo",
    "bank_transfer": "Potwierdzenie przelewu",
    "participation": "Karta uczestnika",
}

# PDFium must never be called simultaneously from multiple threads or sessions.
pdf_worker = ThreadPoolExecutor(max_workers=1)

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
                    "Pliki PDF",
                    multiple=True,
                    accept=".pdf",
                    button_label="Wybierz pliki PDF…",
                    placeholder="Nie wybrano plików",
                ),
                ui.output_text("upload_summary"),
                ui.input_text("case", "Nazwa sprawy w archiwum", "sprawa"),
            ),
            ui.panel_conditional(
                "input.mode === 'folder'",
                ui.input_text("folder", "Ścieżka do folderu", "input"),
                ui.p("Wskaż folder ze sprawami lub folder jednej sprawy."),
            ),
            ui.input_action_button("run", "Analizuj dokumenty", class_="btn-primary"),
            ui.div(ui.output_text("notice"), role="status", class_="notice"),
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
                ui.div(
                    ui.tags.section(
                        ui.div(ui.h3("Dokument źródłowy"), ui.output_ui("page_picker"), class_="panel-head"),
                        ui.output_ui("preview"),
                        class_="viewer",
                    ),
                    ui.tags.section(
                        ui.div(ui.h3("Wynik JSON"), ui.output_text("target"), class_="panel-head"),
                        ui.output_code("result_text"),
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
    scratch = TemporaryDirectory(prefix="odwolania-")
    session.on_ended(lambda: scratch.cleanup())

    @reactive.effect
    @reactive.event(input.run)
    async def analyze_files():
        nonlocal scratch
        documents.set([])
        scratch.cleanup()
        scratch = TemporaryDirectory(prefix="odwolania-")
        try:
            if input.mode() == "folder":
                sources = folder_sources(input.folder())
            else:
                sources = upload_sources(input.case().strip(), input.files() or [])
            with ui.Progress() as progress:
                progress.set(message="Trwa analiza dokumentów…")
                results = await asyncio.get_running_loop().run_in_executor(
                    pdf_worker, analyze, sources, Path(scratch.name)
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
    def upload_summary():
        files = input.files() or []
        if len(files) == 1:
            return files[0]["name"]
        return f"Wybrane pliki: {len(files)}" if files else "Nie wybrano plików."

    @render.text
    def notice():
        return message()

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

    @render.text
    def classification():
        result = selected().result
        if result.error:
            return "Nie udało się odczytać dokumentu"
        if result.label is None:
            return "Dokument poza obsługiwanymi klasami"
        return CLASS_NAMES.get(result.label, result.label.replace("_", " "))

    @render.text
    def target():
        return selected().name.with_suffix(".json").as_posix()

    @render.code
    def result_text():
        result = selected().result
        if result.error:
            return f"Zapisano pusty plik (0 B).\nPrzyczyna: {result.error}"
        return result.text or "Zapisano pusty plik (0 B)."

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
            try:
                image = await asyncio.get_running_loop().run_in_executor(pdf_worker, page_image, doc.snapshot, number)
                return ui.img(src=image, alt=f"{doc.name.name}, strona {number}")
            except (OSError, ValueError, RuntimeError):
                pass
        return ui.p("Nie udało się wyświetlić strony PDF.")

    @render.download_button(filename="wyniki.zip", media_type="application/zip")
    def download():
        yield archive(documents())


app = App(app_ui, server)

if __name__ == "__main__":
    run_app(app, host="127.0.0.1", launch_browser=True, dev_mode=False)
