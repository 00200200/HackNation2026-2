// doc2json: drop PDFs on the left, read the JSON on the right.
// Files go to the extraction API only when /api/health answers; otherwise nothing leaves the browser.

const MAX_MB = 20;
const MAX_FILES = 10; // same limits as kio2json/web_api.py
const API_TIMEOUT_MS = 600000;
// Class ids from config/classes/*.toml; a document outside every class comes back with class null.
const CLASS_LABEL = {
  appeal: "Odwołanie",
  power_of_attorney: "Pełnomocnictwo",
  bank_transfer: "Przelew",
  participation: "Przystąpienie",
};

const $ = (sel) => document.querySelector(sel);
const state = { items: [], selected: null };

function notice(text) {
  $("#notice").textContent = text;
  $("#notice").hidden = !text;
}

function jsonText(item) {
  return JSON.stringify(item.data, null, 2);
}

function renderFiles() {
  const list = $("#file-list");
  list.replaceChildren();
  for (const item of state.items) {
    const done = item.data !== undefined;
    const row = document.createElement(done ? "button" : "div");
    row.className = "file";
    if (done) {
      row.type = "button";
      row.setAttribute("aria-current", String(state.selected === item));
      row.addEventListener("click", () => select(item));
    }
    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = item.file.name;
    const status = document.createElement("span");
    status.className = "file-status" + (item.busy ? " is-busy" : "");
    status.textContent = item.status || (item.cls ? (CLASS_LABEL[item.cls] ?? item.cls) : "Inny dokument");
    row.append(name, status);
    const li = document.createElement("li");
    li.append(row);
    list.append(li);
  }
  const any = state.items.length > 0;
  $("#drop-empty").hidden = any;
  $("#drop-files").hidden = !any;
  $("#app-note").hidden = any;
}

function showOutput(name, tag, text, actions) {
  $("#out-name").textContent = name;
  $("#out-tag").textContent = tag;
  $("#out-tag").hidden = !tag;
  $("#out-code").textContent = text;
  $("#copy").hidden = $("#download").hidden = !actions;
}

function select(item) {
  state.selected = item;
  $("#copy").title = "Kopiuj JSON";
  const name = item.file.name.replace(/\.pdf$/i, "") + ".json";
  showOutput(name, item.error || "", jsonText(item), true);
  renderFiles();
}

async function apiAvailable() {
  try {
    return (await fetch("/api/health", { signal: AbortSignal.timeout(4000) })).ok;
  } catch {
    return false;
  }
}

async function extract(items) {
  const form = new FormData();
  items.forEach((item) => form.append("files", item.file, item.file.name));
  const res = await fetch("/api/extract", { method: "POST", body: form, signal: AbortSignal.timeout(API_TIMEOUT_MS) });
  if (!res.ok) {
    const detail = await res.json().then((body) => body.detail).catch(() => null);
    throw new Error(typeof detail === "string" ? detail : `serwer odpowiedział ${res.status}`);
  }
  return res.json();
}

async function handleFiles(fileList) {
  const files = [...fileList];
  const pdfs = files.filter((f) => (f.type === "application/pdf" || /\.pdf$/i.test(f.name)) && f.size <= MAX_MB * 1048576);
  const overflow = Math.max(0, pdfs.length - MAX_FILES);
  pdfs.splice(MAX_FILES);
  const skipped = files.length - pdfs.length - overflow;
  const skipNote =
    (skipped ? `Pominięto ${skipped}: tylko PDF do ${MAX_MB} MB. ` : "") +
    (overflow ? `Pominięto ${overflow}: najwyżej ${MAX_FILES} plików naraz. ` : "");
  if (!pdfs.length) {
    notice(skipNote || "Wybierz pliki PDF.");
    return;
  }

  const fresh = pdfs.map((file) => ({ file, status: "Sprawdzam…", busy: true }));
  state.items.push(...fresh);
  renderFiles();
  showOutput("wynik.json", "", "", false);
  notice(skipNote);

  if (!(await apiAvailable())) {
    fresh.forEach((item) => Object.assign(item, { status: "Nie wysłano", busy: false }));
    renderFiles();
    notice(`${skipNote}Silnik ekstrakcji nie jest jeszcze podłączony. Pliki zostały w przeglądarce.`);
    return;
  }

  fresh.forEach((item) => (item.status = "Przetwarzam"));
  renderFiles();
  try {
    const { results } = await extract(fresh);
    fresh.forEach((item, i) => {
      const hit = results.find((r) => r.index === i);
      if (!hit) Object.assign(item, { busy: false, status: "Brak wyniku" });
      else Object.assign(item, {
        busy: false,
        status: hit.error ? "Błąd odczytu" : "",
        error: hit.error,
        cls: hit.class,
        data: hit.data,
      });
    });
    const failed = fresh.filter((item) => item.error);
    notice(skipNote + (failed.length ? `Nie udało się odczytać: ${failed.map((f) => f.file.name).join(", ")}.` : ""));
    const first = fresh.find((item) => item.data !== undefined);
    if (first) select(first);
    else renderFiles();
  } catch (err) {
    fresh.forEach((item) => Object.assign(item, { status: "Błąd", busy: false }));
    renderFiles();
    const reason = err.name === "TimeoutError" ? "przekroczono czas" : err.message;
    notice(`Nie udało się przetworzyć plików (${reason}). Spróbuj ponownie.`);
  }
}

function wire() {
  const drop = $("#drop");
  const input = $("#files");
  const pick = () => input.click();
  $("#pick").addEventListener("click", pick);
  $("#add").addEventListener("click", pick);
  input.addEventListener("change", () => {
    if (input.files.length) handleFiles(input.files);
    input.value = "";
  });
  ["dragenter", "dragover"].forEach((t) =>
    drop.addEventListener(t, (e) => {
      e.preventDefault();
      drop.classList.add("is-over");
    }),
  );
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("is-over")));
  // Files dropped anywhere on the page go to the upload; otherwise the browser would open the PDF and leave the app.
  const carriesFiles = (e) => e.dataTransfer?.types.includes("Files");
  window.addEventListener("dragover", (e) => {
    if (carriesFiles(e)) e.preventDefault();
  });
  // Cancel every drop, so a link dropped on the zone does not navigate away either.
  window.addEventListener("drop", (e) => {
    e.preventDefault();
    if (carriesFiles(e) && e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
  });
  $("#clear").addEventListener("click", () => location.reload());
  $("#copy").addEventListener("click", async () => {
    if (!state.selected) return;
    const failed = "Nie udało się skopiować JSON-a. Pobierz plik przyciskiem obok.";
    try {
      await navigator.clipboard.writeText(jsonText(state.selected));
      $("#copy").title = "Skopiowano";
      if ($("#notice").textContent === failed) notice("");
    } catch {
      $("#copy").title = "Kopiuj JSON";
      notice(failed);
    }
  });
  $("#download").addEventListener("click", () => {
    if (!state.selected) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([jsonText(state.selected)], { type: "application/json" }));
    a.download = state.selected.file.name.replace(/\.pdf$/i, "") + ".json";
    a.click();
    URL.revokeObjectURL(a.href);
  });
}

wire();
