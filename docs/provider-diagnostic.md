# Management provider diagnostic

`scripts/provider_diagnostic.py` sends the five fixed combinations requested for
provider troubleshooting, separate from Copilot starts and research comparison:
Zen Muse Responses, Zen MiMo/Nemotron Chat Completions, and OpenAI's exact
`gpt-4.1-mini-2025-04-14` through each API. It never changes account settings.

```powershell
.venv/Scripts/python.exe scripts/provider_diagnostic.py --output results/new-provider-diagnostic --execute-real-model
```

Use a new output directory. Each provider retrieves its model list once, then
checks exact IDs. The two providers run in parallel; requests within one provider
are serial, with no automatic retry. Prompt: `Reply with OK.`; output cap: 256.
Every HTTP operation runs in a subprocess killed and reaped at a 30-second overall
deadline, including DNS/connect/TLS/body receipt. It does not follow redirects.
Windows user environment keys are read inside that subprocess and routed only to
the corresponding fixed provider host. Authentication headers are not saved.

OpenAI inference is held by default. `--openai-free-evidence <file>` can supply a
researcher record with `key_organization_verified`, `model_eligible`, and
`quota_remaining_verified` all true, supported by current observations. Do not
set these solely because a model is listed or a browser organization is enrolled.
The credential/model-list gate still applies. No evidence file was used in the
2026-09-08 diagnostic: OpenAI model listing returned 401 `invalid_api_key`.

Each request receives a new diagnostic UUID. Zen sends that UUID as its stable
session header and the existing honest diagnostic User-Agent. Request metadata,
safe HTTP headers, sanitized response body and result have separate JSON files.
Timeouts retain already-received headers; absent status/usage remains null.
`results.json` includes all five planned combinations, including unsent entries,
and points to the provider's model-list diagnostic ID. Model-list success, text
receipt, usage validity, output cap and HTTP rejection are distinct observations.

Local recorded results: `results/provider-diagnostic-sanitized-20260908/report.md`.
These probes do not establish Copilot file editing, tools, independent evaluation,
or comparison acceptance. Further inference requires a new requested diagnostic;
the command is not a monitor or automatic recovery loop.
