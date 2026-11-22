# Process the evaluation documents

From `/opt/solution`, run this command once the PDFs are in `/opt/solution/input`.

```sh
sudo env PYTHONPATH="$PWD/repo" "$PWD/.venv/bin/python" -P -m kio2json --input "$PWD/input" --output "$PWD/output" --jobs 2
```

The command reads every PDF recursively. For example, `input/case A/appeal.pdf`
produces `output/case A/appeal.json`. It exits automatically with status 0 on
success. UZP requires `{}` for unrelated documents. Releases predating the fix
for issue #57 write a zero-byte JSON file for those documents.

The default rules-only profile uses **no external services**. Its Python runtime,
OCR models and dependencies are installed on the VM. Each invocation starts
the CLI directly from disk.

For the optional keyed profile, the deployment owner supplies the provider's
`KIO_LLM_BASE_URL`, `KIO_LLM_MODEL` and `KIO_LLM_API_KEY` in
`/opt/solution/.env` before evaluation. With the regional Mistral profile the
external service is Mistral’s API at `https://api.eu.mistral.ai/v1`, and the
model is `ministral-3b-2512`. The same command then needs network access.
