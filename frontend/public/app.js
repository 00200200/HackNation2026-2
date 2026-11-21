// doc2json: drop PDFs on the left, read the JSON on the right.
// Files go to the extraction API only when /api/health answers; otherwise nothing leaves the browser.

const MAX_MB = 25;
const API_TIMEOUT_MS = 180000;
const CLASS_LABEL = {
  odwolanie: "Odwołanie",
  pelnomocnictwo: "Pełnomocnictwo",
  przelew: "Przelew",
  negatywny: "Inny dokument",
};

const $ = (sel) => document.querySelector(sel);
const state = { items: [], selected: null };

function notice(text) {
  $("#notice").textContent = text;
  $("#notice").hidden = !text;
}

function hasJson(item) {
  return item.data && Object.keys(item.data).length > 0;
}

function jsonText(item) {
  return hasJson(item) ? JSON.stringify(item.data, null, 2) : "";
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
    status.textContent = item.cls ? CLASS_LABEL[item.cls] ?? item.cls : item.status;
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
  const name = item.file.name.replace(/\.pdf$/i, "") + ".json";
  if (hasJson(item)) showOutput(name, "", jsonText(item), true);
  else showOutput(name, "Pusty plik", "Dokument spoza trzech rodzajów. Plik JSON zostaje pusty.", false);
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
  if (!res.ok) throw new Error(`serwer odpowiedział ${res.status}`);
  return res.json();
}

async function handleFiles(fileList) {
  const files = [...fileList];
  const pdfs = files.filter((f) => (f.type === "application/pdf" || /\.pdf$/i.test(f.name)) && f.size <= MAX_MB * 1048576);
  const skipped = files.length - pdfs.length;
  const skipNote = skipped ? `Pominięto ${skipped}: tylko PDF do ${MAX_MB} MB. ` : "";
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
    for (const item of fresh) {
      const hit = results.find((r) => r.file === item.file.name);
      Object.assign(item, { busy: false, cls: hit?.class, data: hit ? hit.data ?? {} : undefined, status: hit ? "" : "Brak wyniku" });
    }
    notice(skipNote);
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
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
  });
  $("#clear").addEventListener("click", () => location.reload());
  $("#copy").addEventListener("click", async () => {
    if (!state.selected) return;
    await navigator.clipboard.writeText(jsonText(state.selected));
    $("#copy").title = "Skopiowano";
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
