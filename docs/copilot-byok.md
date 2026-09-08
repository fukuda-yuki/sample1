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
