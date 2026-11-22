# Submission checklist

Nothing in this file has been submitted. The team submits only after an explicit go.

## Timeline for 22.11.2026

| Time | What | Source |
|---|---|---|
| about 08:30 | Open PRs reviewed and merged | coordinator plan |
| about 10:00 | Final deploy on the evaluation VM, `RUN.md` rehearsed, reboot rehearsed | coordinator plan |
| 11:00 | Team access to the VM ends; the solution is judged as left there | organizer `VM.md` |
| 11:00 | HackNation submission window closes | HackNation general rules, as recorded in `.claude/skills/hacknation-judging/SKILL.md` (UNCONFIRMED against the form) |

## How the jury runs the solution

The organizer's `VM.md` (upstream commit `eadffbc`, 21.11.2026 23:38 UTC) describes the evaluation:

- Each team can request one Azure VM through the form linked in `VM.md`: Ubuntu 24.04, 2 vCPU, 16 GB RAM, 64 GB
  disk, no GPU, Docker with Compose v2, Python 3.12. Ports 80, 443, 8000 and 8080 are open.
- The evaluators copy the secret set into `/opt/solution/input`, run the command from `/opt/solution/RUN.md` in
  `/opt/solution` with `sudo`, and take the files from `/opt/solution/output`. The command must need no
  interaction and must exit by itself. Background services keep running.
- Images, models and dependencies must already be on the VM. API keys, if any, go into `/opt/solution/.env`, and
  `RUN.md` names the services that use them.
- `VM.md` asks teams to rehearse exactly that: sample documents in `input/`, an empty `output/`, the command copied
  from `RUN.md`, and the same again after `sudo reboot`.

The deployment kit from #77 follows that layout ([README, Deploy on the evaluation VM](../README.md#deploy-on-the-evaluation-vm)):
the deployment account clones the repository into `~/kio-release` over SSH, `deploy/vm_setup.sh` copies the
checked-out commit into `/opt/solution/repo`, installs Python 3.13 and the pinned requirements next to the VM's
Python 3.12, smoke-tests a transfer and a scanned appeal outside the evaluator folders and installs `RUN.md`.
`deploy/rehearse_vm.sh` then compares all 226 organizer files in a network-disabled run and after a container
restart. Docker Compose is the fallback `RUN.md` profile. On the development host Docker did not start, so the
Ubuntu offline run, the 2-vCPU time and the reboot are unverified; on the shared Apple M1 the network-denied run
matched all 226 files with two workers at extraction revision `7a1c45b`, before #57; the kit extrapolates that run to
about 4 min 25 s for 150 PDFs, an estimate rather than a measurement ([rehearsal measurements](../evals/results/vm-2vcpu.json)).
A later two-worker run on the same Mac processed the same 226 files in 161 s
([first-pass watchdog measurements](../evals/results/first-pass-watchdog.json)). Setup and the rehearsal belong to #66.

UNCONFIRMED: whether a team without a VM is judged from its GitHub link, and whether the API key goes into the form
field or `/opt/solution/.env`.

## Form fields we know

The organizer README (section 4) and FAQ 15 require a title and a GitHub link. Documentation and test results are
optional. We have not seen the form itself, so its exact field names are UNCONFIRMED.

| Field | Value | Status |
|---|---|---|
| Project title (required) | `doc2json`, subtitle "Odwołania2json (UZP)" | Recommended on #48; the team decides |
| GitHub link (required) | https://github.com/00200200/HackNation2026-2 | The repository is private. Grant read access to DominikOlczak, MateuSzSz-Sz and rkrol-dev first (UZP request, 21.11.2026 16:23); audit on #48 |
| Technical documentation (optional) | `README.md` and `docs/pipeline/pipeline.pdf` | The organizer README (section 4) lists a description of the LLM used as part of this documentation |
| Quality test results (optional) | `evals/results/p0-conventions.json` (newest UZP-formula and strict F1, after #57 and #58); earlier runs in `case-siblings.json`, `uzp-metric.json` and `round3.json` | Numbers and sources in `docs/pitch/README.md` |
| LLM used | None in the default configuration | Rules only unless the team decides otherwise on #38 |
| API key | Leave empty for a rules-only submission | Only if a model is used. UZP mentioned a form field on Discord (issue #64); `VM.md` says `/opt/solution/.env` |
| Presentation or video | `docs/pitch/doc2json-pitch.pdf` | UNCONFIRMED whether the form asks for either |

## Before the team submits

- [ ] Request the VM with the form in `VM.md` (one request per team) and hand the login to #66.
- [ ] Pick the title (#48).
- [ ] Grant the three UZP accounts read access, after reading the audit on #48.
- [ ] Decide rules only or Ministral 3B (#38), and record the decision in `WORKLOG.md`.
- [x] Merge the output contract: `{}` for unrelated documents (#57) and account numbers as printed (#58).
- [ ] Merge #76 (classes from one TOML file, `--classes`, `--explain`); the deck and the demo rely on it.
- [ ] Run the full eval on the final commit and push with `HN_FINAL=1 git push`.
- [ ] Check out that final pushed commit in `~/kio-release`, run `deploy/vm_setup.sh` from `/opt/solution` and the offline rehearsal, then run the command from `RUN.md` on sample PDFs and again after `sudo reboot`, as `VM.md` describes (#66).
- [ ] Last step on the VM, before 11:00: remove every sample input and output but keep both folders, so `find /opt/solution/input /opt/solution/output -mindepth 1` prints nothing.
- [ ] There is no `LICENSE` file (#48). Decide together with the copyright transfer in `docs/task/regulamin.pdf`, § 4.

## Commands for a local run

For a jury member who runs the GitHub version on their own machine: Python 3.13 (64-bit), no GPU, no API key.
Commands run from the repository root. Section names refer to `README.md` on main; PR #36 moves the detailed
sections to `docs/readme/reference.md`.

Install, Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell refuses to run `Activate.ps1` (the default policy on Windows client machines), run
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first. It applies to that window only.

Install, macOS or Linux:

```sh
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

pip downloads only from PyPI. The Polish and English Tesseract models (8.88 MB) ship in `kio2json/tessdata/`, and
the CLI checks their SHA-256 hashes before the first OCR page.

CLI on the jury folders: each `input/<case>/<name>.pdf` gets `output/<case>/<name>.json`.

```sh
python -m kio2json
python -m kio2json --input some/input --output some/output
```

The same through the start scripts: `.\start.bat` on Windows, `./start.sh` on macOS or Linux.

GUI with the source PDF beside the JSON, at http://127.0.0.1:8000:

```sh
python -m kio2json.gui
```

The same through the start scripts: `.\start.bat gui` or `./start.sh gui`.

Docker Compose (merged in #68; container byte parity UNCONFIRMED):

```sh
docker compose run --rm cli
docker compose up gui
```

The `gui` service serves the upload page at http://127.0.0.1:8000 and the API docs at
http://127.0.0.1:8000/api/docs. The root `compose.yaml` sets `pull_policy: build`, so it builds the image on every run (fast with the layer
cache) and the first run needs the network. The VM kit's `deploy/compose.vm.yaml` uses a prebuilt image instead.

Optional model, only if the team submits with one: the measured Ministral 3B profile needs the full set of
`KIO_LLM_*` settings from the README section on model endpoints, in the shell or in an ignored `.env` file for
Docker Compose. Setting only `KIO_LLM_BASE_URL`, `KIO_LLM_MODEL` and `KIO_LLM_API_KEY` selects a different,
unmeasured profile.

## Checked on 22.11.2026

On macOS with Python 3.13, rerun after merging `main` at `4222472` (#54, #57, #58, #77, #79):

- `python -m kio2json --input input --output <tmp>` wrote the appeal JSON for `input/case1` and `{}` for its
  unrelated PDF.
- Six PDFs (organizer case `przyklad_04` and two organizer scans) were routed to the right classes, and the scanned
  appeal matched the organizer's reference JSON exactly.
- With `KIO_CLASSES_DIR` on a copy of `config/classes`, the invented `karta-uczestnika.pdf` gave `{}` and, after
  `enabled = true`, the fourth-class JSON. The viewer's analysis function reloads the class files on each call; the
  click-through in the browser was done on the earlier `main` (`docs/pitch/demo.md`).

Not checked here: Windows and Linux (the hosted run in PR #67 was blocked by GitHub billing,
`evals/results/jury-batch.json`), Docker and the evaluation VM.
