# Process the evaluation documents

From `/opt/solution`, run this command once the PDFs are in `/opt/solution/input`.

```sh
sudo env PYTHONPATH="$PWD/repo" "$PWD/.venv/bin/python" -P -m kio2json --input "$PWD/input" --output "$PWD/output" --jobs 2
```

The command reads every PDF recursively. For example, `input/case A/appeal.pdf`
produces `output/case A/appeal.json`. It exits automatically with status 0 on
success. A document outside the three known classes produces `{}`, as UZP
requires.

## Jury configuration

The CLI reads `/opt/solution/.env` when it starts in `/opt/solution`.
Setup creates the file with mode 600 and a blank key on first install. Before
handover, the deployment owner supplies the team's Mistral API key in that file.

| Variable | Value on the VM |
|---|---|
| `KIO_LLM_BASE_URL` | `https://api.eu.mistral.ai/v1` |
| `KIO_LLM_MODEL` | `ministral-3b-2512` (3.85 billion parameters including vision weights) |
| `KIO_LLM_API_KEY` | The team's credential, stored only in the private file |

Use just these three model settings for evaluation. Explicit mode or routing
overrides select an experimental profile. OCR, routing and rules run on
the VM. For a recognized document, the CLI can send page text to Mistral to
fill a field the rules left null. Every populated rule value is final, even
when the document contains conflicting text. The CLI checks the quoted evidence and the
party it belongs to before using an answer. Counsel contact details require a
representation flag already established by the rules. A first-act date needs
a quote tying that date to the act or its notification.

The two workers share one API slot. Each PDF can trigger one request, with a
10-second timeout and no retry. Requests start at least one second apart.
For 150 PDFs the workers share five minutes of model time. HTTP 429 pauses
further calls for one minute. If the file or key is missing,
the same command runs offline. A timeout, quota limit or API failure leaves
the rule result in place.

UZP specifies servers in the EU or EEA. Mistral lists EU and EFTA data centers
for inference at this endpoint. The specific country serving this model is
unconfirmed. Mistral describes its
handling of personal data and its terms for processing customer documents in
the following sources. [Regional inference](https://docs.mistral.ai/inference/regional-inference) ·
[Privacy policy](https://legal.mistral.ai/terms/privacy-policy/) ·
[Data Processing Addendum](https://legal.mistral.ai/terms/data-processing-addendum/)
