# Copilot / Zen experiment infrastructure

The bounded Go acceptance path uses `provider=opencode-go`,
`base_url=https://opencode.ai/zen/go/v1`, and exact model
`muse-spark-1.3-contributor` or `muse-spark-1.2-contributor`. GPT and other Go
models are rejected in this bounded path. The gateway reads the Go credential from its
gateway-only secret mount, retains its honest User-Agent and stable Run session
header, and never falls back to Zen. Use new start authority and experiment IDs;
the historical Zen Free settings and failed originals remain unchanged.
This support does not itself establish live acceptance or authorize comparison.

For the unscored, at-most-300-second `copilot-smoke`, a restored
`copilot-smoke-readiness` package may replace the full evaluator restoration gate.
It pins the smoke settings and execution sources and retains the non-model real
CLI edit/tool/continuation/native-usage evidence. Its verified restore receipt is
registered as `preservation.smoke_readiness`. This does not authorize validation
or comparison starts; those retain the full restoration/acceptance checks.
Unchanged evaluator calibration can run independently of this short smoke.

This path measures GitHub Copilot CLI, separately from historical Codex pilots.
The public specs, common instructions and 57 ID / 58 case definition are unchanged.
No command below purchases credits or changes account settings. Real inference is opt-in.

[Post-PR #21 live acceptance record](copilot-acceptance-20260908.md): a new bounded
management inference diagnostic returned provider HTTP 429. Its originals were
archived and restored; real Copilot smoke, both implementation validations and
comparison remain unstarted. Diagnostic restoration is not the full Copilot
preservation gate. Current progress remains in Issues #16–#19.

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
or `copilot-smoke` or `copilot-validation`, condition, planned_run, execution_order, tool_versions,
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
the diagnostic at that point classified HTTP 429 as `rate_limited`. Originals
remain unchanged under `results/zen-live-diagnostics/<UUID>/`. The response body
and Retry-After were not retained, so the precise quota reason and retry time are
unknown. No further model call was made in this check. Live Copilot/Muse editing,
tool continuation, usage reconciliation and downstream independent acceptance
remain unverified. No actual comparison Run was started.

### Diagnostic success and bounded implementation validation

The diagnostic now exits zero only for HTTP 200, the exact model, nonempty
`output_text`, and nonnegative integer input/output/total usage whose sum agrees.
Empty responses, invalid/missing usage and model mismatches are explicit failures.
HTTP status and cause are separate. Allowlisted response headers (including
Retry-After and available request identifiers) and bounded, redacted upstream
error code/type/message are retained; arbitrary headers and credentials are not.
An HTTP 429 alone does not identify the quota or a retry time. A successful
diagnostic saves the response text and numerical usage. Historical results are
not rewritten to the new result shape.

For a new, separate acceptance batch, copy the existing config and set
`phase` to `copilot-validation` and a distinct `copilot-` experiment version.
The existing `plan/check/run/status/resume/evaluate/export` commands then operate
on exactly one normal and one anti slot, with the seed-fixed pair order.
The absent phase still means the original 20+20 comparison; existing plans
are neither migrated nor edited. Use a separate authorization file and batch
directory for validation. Issue #16 authorizes the researcher to register the
finite validation slots and opt in; it does not authorize comparison starts.

Validation uses the full implementation prompt, the same isolation, freeze,
gateway, native telemetry, independent evaluator and preservation gates.
It requires explicit single-use starts and restoration prerequisites, but does
not require the comparison's pre-existing live acceptance record. Comparison
continues to require that record. Validation uses the collector/aggregator's
explicit `validation=True` mode; default analysis rejects it and validation
analysis rejects comparison, pilot, diagnostic and smoke data. Export refuses
to reuse a directory belonging to a different phase or experiment.

The intended real sequence is one direct diagnostic, then one `copilot-smoke`
(300 seconds), then the two validation implementations (3600 seconds each).
Only proceed after each prior stage succeeds. A fresh verified preservation
protocol for the current sources/image is required; do not relabel a historical
Codex proof or clear its retired flag. Pin the calibrated private evaluator and
verify account/free/data terms before the implementation starts. No fallback,
automatic reimplementation, or comparison grant is added.

Run with `--private-root`, `--evaluator-image`, `--validity` and the explicit
monitor locator so each submission is independently evaluated before the next
start. The linked Run and evaluation archives are restored and hash checked.
Validation exports after each evaluation and stops if export fails; valid zero
quality continues, while incomplete usage or evaluator/isolation failures stop.
After the last Run, export again for the final status and independently reproduce
the CSV/SQLite from preserved originals. Only actual edit/tool/continuation,
usage/DB/evaluation/restore evidence may support a hash-bound live acceptance
record; this command does not manufacture successful acceptance booleans.

Non-model verification of the two-slot path uses an actual monitor with
synthetic CLI/usage/E2E-shaped data:

```sh
python scripts/check_copilot_batch.py --output results/new-validation-fixture --validation dotnet /absolute/ConfigCli.dll
```

This checks two starts, restart after one, archive restoration, valid zero,
missing usage, wrong submission rejection and identical re-exports. It is not
a real Muse implementation or a private E2E execution.

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

#### Acceptance compatibility and relocated analysis

`copilot_scope.settings_hash()` still binds start authority to its exact experiment
ID/version and existing execution settings. A comparison authority's
`live_acceptance` additionally contains `path`, `sha256`, and `target_experiment`
(`experiment_id`, `experiment_version`, `phase=comparison`). It does not reuse the
validation experiment's start authorization.

The hash-pinned acceptance document uses `schema_version=1`,
`kind=real-copilot-muse`, `synthetic=false`, `source_config` (the original complete
validation configuration), `source_experiment` (its ID/version/phase), and
`settings_sha256` computed from that source configuration. Existing seven acceptance
checks must all be true. Source phase must be `copilot-validation`.
The separate compatibility contract requires equal agent/provider/endpoint/wire API,
exact model/CLI, budget, environment image and other environment settings, effort,
subagent policy, tool versions, all input hashes, score version and evaluator file
hashes. Missing input/evaluator pins are rejected. The start result retains both
experiment identities and the evidence hash in the Run's authorization provenance.
Old evidence without these bindings fails closed. Create this document only from
actual accepted observations; the format tests do not register real acceptance.

For offline analysis, explicitly preserve the fixed batch/index, selected Run and
evaluation originals, input files and validity snapshot. This is a private analysis
package, not a full runtime/image backup or a shareable export. The packager retains
the complete validity registry and its hash-pinned relative adjudication and legacy
binding files without rewriting their paths. Absolute or out-of-tree dependencies
are rejected rather than silently omitted. Restoration checks cover these files too.

```sh
python scripts/copilot_analysis_archive.py pack /research/batch /research/validity.json /archive /research/new-reference.json
python scripts/copilot_analysis_archive.py restore /archive /research/new-reference.json /research/new-restoration
python scripts/copilot_batch.py export /research/new-restoration/payload/batch --validity /research/new-restoration/payload/validity.json --restoration-map /research/new-restoration/restoration-map.json
python scripts/check_copilot_analysis_restore.py results/bounded-validation-final results/new-relocation-drill --archive /archive
```

The restoration map and hash-pinned package index stay outside the immutable
payload; original absolute references, IDs and hashes remain unchanged. Export
verifies every restored file, resolves selected evaluation locations within the
payload, and writes beside the payload. It uses the preserved validity snapshot to
reproduce that historical analysis, not to grant current start permission. No live
monitor or model is contacted. The drill renames its trial source and rejects source,
archive and repository-input reads using a Python audit hook in a separate export
process. This tests this exporter; it is not an OS sandbox for arbitrary programs.

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
on a separate DB. Those non-model checks do not establish live inference,
account availability, long-run behavior, or implementation-to-E2E acceptance.
Current live evidence and remaining acceptance work are tracked in Issue #19;
forty real comparison Runs still require separate authorization.
