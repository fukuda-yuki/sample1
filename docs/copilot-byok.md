# Copilot / Zen experiment infrastructure

This path measures GitHub Copilot CLI, separately from historical Codex pilots.
The public specs, common instructions and 57 ID / 58 case definition are unchanged.
No command below purchases credits or changes account settings. Real inference is opt-in.

## Worker and single Run

Run Docker commands on the Docker host (WSL), using a newly prepared image digest:

```sh
docker build -f scripts/Dockerfile.copilot --build-arg BASE_IMAGE=<prepared-common-image-digest> -t sample1-copilot:1.0.83-5 scripts
python3 scripts/run_copilot.py check /research/copilot-config.json
python3 scripts/run_copilot.py run /research/copilot-config.json --distribution /research/distribution --output /research/run --secret-file /private/zen-key --execute-real-model
```

`check` performs no network/model request. Required configuration includes agent
`github-copilot-cli`, provider `opencode-zen`, base_url `https://opencode.ai/zen/v1`,
wire_api `responses`, agent_version `1.0.83-5`, model_id (explicitly confirmed exact
Muse Contributor Free ID), effort `null`, subagent_policy `disabled`, a new opaque
experiment_id UUID, experiment_version beginning `copilot-`, phase `comparison`
or `copilot-smoke`, condition, planned_run, execution_order, tool_versions,
environment.image (digest), budget (positive wall_clock_seconds / container),
and authorization_file (researcher-owned absolute path).

The separate authorization file requires settings_sha256 from
`copilot_scope.settings_hash`, explicit allowed_starts/do_not_start, current
account_terms_confirmed/exact_model_confirmed, and the existing preservation
gate contract. Comparison additionally requires a hash-bound live_acceptance
record for the same settings and edit/tool/continuation/usage/monitor/E2E/archive
checks. This repository does not create that evidence or authorize starts.
Old pilot reservations and stop records are not modified. New reservations are
exclusive and consumed even if setup fails. No automatic retries of Run slots.

Only the gateway mounts the real key; it accepts the pinned Responses model and
function/custom tools, preserves numeric start/end inventories, and rejects
fallback response models. The worker has a private internal network, fresh HOME,
neutral workspace and persistent OTel spool. Native JSONL is not Codex usage.
Tool availability excludes delegation, web fetch, skills and MCP. The fixed
image must pass dependency restoration before a real start; a cached dependency
probe does not establish that every arbitrary dependency can restore offline.

## Non-model checks

```sh
python -m unittest discover -s scripts -p 'test_*.py'
python evaluation/validate-requirements.py
python3 scripts/check_copilot_native.py --image <copilot-image-digest> --output /research/new-synthetic-cli-check
python3 scripts/check_offline_runtime.py --image <copilot-image-digest> --evidence /research/offline-runtime.json
python3 scripts/check_copilot_lifecycle.py --evidence /research/copilot-lifecycle.json
```

The native check uses the actual CLI against a synthetic Responses server on an
internal network. It never contacts Zen or another real model. Synthetic success
is not Copilot/Muse acceptance. `copilot-smoke` is a separate real opt-in probe:
write a file, execute/read it with a tool, and continue the model response.

## References and limits

Local `copilot --version`, `--help`, `help providers`, and `help monitoring` were
inspected for 1.0.83-5. See [GitHub CLI reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference),
[BYOK](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models),
[native Responses](https://github.github.io/gh-aw/guides/azure-openai-byok/), and
[Zen](https://dev.opencode.ai/docs/zen). Model listing alone does not establish
free use, availability for an account, or free completion of forty Runs. Confirm
current free/data-training terms and account limits before explicit real use.

Real Copilot/Zen/Muse connectivity, usage semantics (including cache/reasoning),
and same-path end-to-end acceptance remain unverified until separately executed.
This documentation does not declare production execution readiness.

### Authorized diagnostic and session headers (2026-09-08)

Issue #16 authorizes necessary live validation and revalidation using
`OPENCODE_ZEN_API_KEY`; this does not authorize forty comparison starts. The
management diagnostic reads the process environment, then Windows user
environment when needed. It does not write the credential to disk:

```powershell
python scripts/zen_diagnostic.py --output results/zen-live-diagnostics --execute-real-model
```

Each invocation creates a new diagnostic UUID before any request, permits one
model-list request and at most one model request (128 output tokens, 30-second
HTTP operation timeout), and preserves failures. It has no automatic retries,
redirects or model fallback. A failed diagnostic exits nonzero. This is a direct
HTTP diagnostic, not a Copilot implementation or a comparison Run.

Both diagnostic and Zen gateway send an honest, task-specific User-Agent and
`x-opencode-session` equal to the preissued UUID. The gateway keeps it constant
within a Run and records `provider_session_id` in its numerical request inventory.
The runner's native CLI session ID is also the Run UUID. No OpenCode client
impersonation headers are added. The session-header convention is documented for
external coding agents in [OpenCode Go](https://dev.opencode.ai/docs/go/#where-can-i-use-it);
that Go documentation alone does not prove free Zen/Muse account access.

Live diagnostic evidence on this date:

| Diagnostic UUID | Header | Models | Responses | Usage |
|---|---|---|---|---|
| c6ffc17b-765d-40f4-82b8-90a3ebd16b9f | absent | exact ID listed, 200 | 400, free-tier restriction | null |
| 70075fed-73b9-4fda-8705-221e4df0d157 | same UUID | exact ID listed, 200 | 429 | null |

The second request changed the observed status, but did not prove a successful
model response. Its original result uses the generic `upstream_rejected` label;
the diagnostic now classifies HTTP 429 explicitly as `rate_limited`. Originals
remain unchanged under `results/zen-live-diagnostics/<UUID>/`. The response body
and Retry-After were not retained, so the precise quota reason and retry time are
unknown. No further model call was made in this check. Live Copilot/Muse editing,
tool continuation, usage reconciliation and downstream independent acceptance
remain unverified. No actual comparison Run was started.

## Run / monitor linkage

```sh
python scripts/check_monitor_link.py --output results/new-monitor-check dotnet /absolute/path/CopilotAgentObservability.ConfigCli.dll
python scripts/telemetry_link.py /research/run /research/monitor-locator.json --ingest
```

The locator JSON contains `instance_id`, the actual absolute `database_path`, and
`import_command` (an argument array, e.g. `["dotnet", "/absolute/ConfigCli.dll"]`).
An absent DB fails unless `--initialize --ingest` explicitly creates a new test
instance. Importer binary hashes and the DB's actual schema versions are saved.
Import uses official `ingest-raw`; read-back uses a read-only SQLite transaction,
including WAL, and examines every raw record. Run/session/trace/span/response IDs
are exact keys; no time/repo/model filtering. Reimported spans deduplicate by
native identity; conflicts and missing calls invalidate the complete total.

`telemetry-link.json` records native/converted hashes, monitor receipts, native
sessions/traces, parent relationships, gateway-request/response/chat-span links,
and submission hash. Only chat request usage is summed. Unreceived usage and
corrupt tails remain null with observed_tokens separate. Native metric records
are counted as ignored signals, never added to span totals. Projection completion
is recorded independently of committed raw read-back; start the matching monitor
instance to let its normal projection worker catch up, then rerun the command.
Do not copy a live DB without WAL; this command neither copies nor resets a DB.

## Fixed batch and independent evaluation

Use the repository's analysis environment (`.venv/Scripts/python.exe` on this
Windows checkout; install `analysis/requirements.txt` in a dedicated environment
if needed). The example deliberately leaves model, budget, image, start authority
and evaluator version unset. Copy and complete it privately before creating a
real plan. It does not silently choose a Muse release or a budget.

```sh
python scripts/copilot_batch.py plan /research/new-batch --config /research/copilot-config.json --seed 123
python scripts/copilot_batch.py status /research/new-batch
python scripts/copilot_batch.py check /research/new-batch
python scripts/copilot_batch.py run /research/new-batch --locator /research/monitor-locator.json --secret-file /private/zen-key --execute-real-model --limit 1
python scripts/copilot_batch.py evaluate /research/new-batch --slot normal-001 --private-root /research/private-eval --evaluator-image <digest> --validity /research/private-eval/evaluation-validity.json
python scripts/copilot_batch.py resume /research/new-batch --locator /research/monitor-locator.json --secret-file /private/zen-key --execute-real-model --private-root /research/private-eval --evaluator-image <digest> --validity /research/private-eval/evaluation-validity.json
python scripts/copilot_batch.py export /research/new-batch --validity /research/private-eval/evaluation-validity.json
```

Choose the actual started slot from `run-index.json`; seed 123 does not imply
normal starts first. `run/resume` is serial. Without private-root it stops at the
first fixed submission awaiting evaluation. With private-root it evaluates each
submission independently before the next start. It stops on incomplete usage or
invalid/pending evaluation; valid zero quality continues. It never replaces a
failed attempt. An exclusive batch.lock prevents concurrent starts; an abrupt
host kill leaves it for inspection. Verify its recorded host/PID and the named
Run containers have stopped before manually removing a stale lock. Resume never
turns an uncertain started slot back into an unstarted slot.

Pin `score_version` and `evaluator_files` from the actual calibrated private
`version.json` in the plan. The evaluator must retain the public case manifest.
The collector uses that attempt's frozen private ledger, including its audit
metadata, rather than relabeling a historical public version. Current researcher
validity decisions remain required. `evaluate` appends a hash-bound record only
for its new pinned independent attempt: completed or application-unavailable is
valid, evaluator/isolation errors stay pending/null. Existing adjudications are
never replaced. Manually imported results without a decision stay pending/null.
`evaluate` creates a fresh evaluation ID, preserves earlier attempts
and replaces only the explicit selected reference. It never resumes implementation.
Do not mark an evaluator error as valid simply to advance the batch.

`export` verifies Run/submission/usage/original hashes and selected evaluation
bindings. It writes 40 rows including unstarted slots, 58 case statuses per
selected evaluation, sanitized provenance, one derived analysis.sqlite and the
existing plot. Case evidence/screenshots/private paths/raw payloads are excluded.
Token counts are aggregated before joining cases. Null coordinates stay outside
the chart. plot-input.csv uses `unstarted:<slot>` solely as an unstarted plot label;
the main CSV/SQLite keep the Run UUID null. Exports do not upload anything.

### Reproducible acceptance checks

```sh
python scripts/check_copilot_batch.py --output results/new-synthetic-40 dotnet /absolute/path/CopilotAgentObservability.ConfigCli.dll
python -m unittest discover -s scripts -p 'test_*.py'
python -m unittest discover -s analysis -p 'test_*.py'
python evaluation/validate-requirements.py
```

The forty-run test uses separate fake CLI processes, numeric fixture usage and
synthetic 58-case result files with the existing collector/validity/aggregator.
It uses the actual monitor importer and read-back, verifies 40 archive restores,
resumes after seven starts, rejects double launch, keeps valid zero scores,
introduces one missing observation, and regenerates matching CSV/SQLite/PNG.
Those case files are format fixtures, **not hidden E2E executions or real model
results**. Real private evaluator calibration is a separate non-model operation:
on this checkout `python3 ../sample1-private-eval-linux/calibrate-isolated.py
--variant self-registration` ran in WSL using its existing independent containers.

The actual CLI synthetic test established edit/tool/continuation and the native
span+metric JSONL layout. The actual dependency probe established cached .NET
restore/SQLite query, npm ci and Vite/React startup in the prepared Copilot image.
Actual monitor fixture ingestion/read-back and projection catch-up were checked
on a separate DB. Real Zen/Muse inference, account/free terms, long-run behavior,
and full real-implementation-to-E2E acceptance were not performed. No additional
pilot or forty real comparison Runs were started.
