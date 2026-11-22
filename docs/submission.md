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

The VM has Python 3.12 and the project needs 3.13, so the Compose `cli` service is the likely `RUN.md` command,
with the repository's files directly in `/opt/solution` so that `./input` and `./output` are the evaluators'
folders. `/opt/solution` already holds `input/` and `output/`, which must not be deleted, so `git clone` into it
fails. Clone elsewhere and copy the files in, or check out in place:

```sh
cd /opt/solution
git init -q
git remote add origin https://github.com/00200200/HackNation2026-2.git
git fetch --depth 1 origin main
git checkout -t origin/main
```

The repository is private: when git asks for a password, paste a read-only fine-grained token at the prompt and
never put it in the URL, because the evaluators can read `/opt/solution/.git/config`. The checkout brings the
repository's sample `input/case1/`, and the rehearsals leave JSON files in `output/`. UZP may clear both folders
before grading, but does not promise to. The VM setup, `RUN.md` and a 2-vCPU timing run belong to #66 (session
install-docker).

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
| Quality test results (optional) | `WORKLOG.md` "Last eval" and `evals/results/round3.json` | Numbers and sources in `docs/pitch/README.md` |
| LLM used | None in the default configuration | Rules only unless the team decides otherwise on #38 |
| API key | Leave empty for a rules-only submission | Only if a model is used. UZP mentioned a form field on Discord (issue #64); `VM.md` says `/opt/solution/.env` |
| Presentation or video | `docs/pitch/doc2json-pitch.pdf` | UNCONFIRMED whether the form asks for either |

## Before the team submits

- [ ] Request the VM with the form in `VM.md` (one request per team) and hand the login to #66.
- [ ] Pick the title (#48).
- [ ] Grant the three UZP accounts read access, after reading the audit on #48.
- [ ] Decide rules only or Ministral 3B (#38), and record the decision in `WORKLOG.md`.
- [ ] Merge the output contract: `{}` for unrelated documents (#57) and account numbers as printed (#58).
- [ ] Run the full eval on the final commit and push with `HN_FINAL=1 git push`.
- [ ] Deploy that final pushed commit to `/opt/solution` (`git -C /opt/solution rev-parse HEAD` shows its SHA), write `RUN.md`, build or pull the images, and rehearse the run and the reboot as `VM.md` describes (#66).
- [ ] Last step on the VM, before 11:00: empty `input/` and `output/` (the sample `input/case1/`, every rehearsal output and both `.gitkeep` files) but keep both folders, so `find /opt/solution/input /opt/solution/output -mindepth 1` prints nothing. Check that `git -C /opt/solution remote -v` and `~/.git-credentials` hold no token.
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

The install downloads the Polish and English Tesseract data (8.88 MB) from a pinned revision and checks their
SHA-256 hashes. The Run section of the README covers offline installs.

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
http://127.0.0.1:8000/api/docs.

Optional model, only if the team submits with one: the measured Ministral 3B profile needs the full set of
`KIO_LLM_*` settings from the README section on model endpoints, in the shell or in an ignored `.env` file for
Docker Compose. Setting only `KIO_LLM_BASE_URL`, `KIO_LLM_MODEL` and `KIO_LLM_API_KEY` selects a different,
unmeasured profile.

## Checked on 22.11.2026

On macOS with Python 3.13 and `main` merged into the pitch branch:

- `python -m kio2json --input input --output <tmp>` wrote the appeal JSON for `input/case1` and an empty file for
  its unrelated PDF.
- Six PDFs (organizer case `przyklad_04` and two organizer scans) took about 15 s. Both scans matched the
  organizer's reference JSON exactly.
- The GUI analyzed the same folder in about 7 s. After `enabled = true` in a copy of `participation.toml`, it
  showed the fourth class without a restart (`docs/pitch/demo.md`).

Not checked here: Windows (PR #67 measures hosted Windows and Linux runners), Docker and the evaluation VM.
