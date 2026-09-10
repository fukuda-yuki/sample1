# Report construction notes

- Primary artifact: Japanese Markdown report, explicitly requested by the user; this overrides the analytics skill's default MCP/HTML surface. No Sites publishing requested.
- Audience: technical research/experimental analysis. Scope: the fixed normal/anti 10-pair experiment, including the retained first anti Run. Older experiments are excluded.
- Spine: whether the promised starts were acquired and retained; what token and first-v6 measurements are available; what can be reprocessed and rescored without another generation.
- Structure mapping: technical summary and acquisition status lead; definitions precede token and raw-result evidence; fixed experimental design, preservation and verification describe methods; nearby missingness caveats and final interpretation cover limitations; reproduction steps and Issues cover next steps/open questions.
- Unit: Run UUID with immutable submission hash. Starts consume the fixed slots even when unsuccessful. Gateway accounting, native-call correspondence, hierarchy and monitor are separate dimensions. Raw v6 pass IDs / 57 is distinct from valid quality.
- Source hierarchy: fixed plan/config and Run manifests; raw gateway/native evidence and versioned measurement selection; evaluation-ref and pinned v6 results; per-evaluation validity registry; independent preservation/restore receipts. GitHub #44 is the progress record.
- Source tables: public SQLite runs, case_results, telemetry_refs, evaluations, provenance. Full raw/evaluator/ordinary-UI sources remain private in the archive. Notebook checks public JSON against SQLite and recomputes summaries.
- Identifier scope: `runs.evaluation_id` and `evaluations.evaluation_id` identify the selected evaluation attempt UUID. `case_results.evaluation_id` and the public `test-results.jsonl` field identify the fixed test ID (for example T-006-01). Join case rows to their selected attempt through `run_id`; these are different kinds of identifier.
- Each export selects one evaluation attempt per Run. A future selection produces a new export/SQLite, while older exports and the private evaluation history remain preserved. `missing-runs.csv` includes missing token or quality values; it does not mean those implementation Runs were unstarted or discarded.
- Token column lineage: total_tokens, observed_tokens and usage_complete use the explicitly selected v2 measurement (processing_id / total_tokens_basis). input_tokens, output_tokens and usage_hash remain the legacy usage projection fields; a missing legacy component is not a contradiction of a separately verified v2 gateway total. Exact current gateway components and native provider usage are in the retained measurement/raw originals. Do not combine fields from different projection versions to recompute a total.
- `telemetry_state` also retains the legacy link status. For the selected v2 processing, use the separate `native_calls_verified`, `trace_structure_complete`, and `monitor_status` fields and the referenced measurement record. A legacy blocked status does not erase independently verified gateway tokens.
- export-complete.json is the immutable source export's file inventory, not the inventory of the expanded report directory. The final delivery preservation reference covers the full report bundle.

## Chart map

| File | Question / family | Grain and fields | Limits / QA |
| --- | --- | --- | --- |
| token-distribution.png | Distribution: individual dot plot and median by condition | One 1.2 Run; complete gateway total; missing totals omitted | At most 10 points per condition; no histogram bins. Blue circles / ochre triangles with neutral median; zero origin. Check exported labels. |
| tokens-quality.png | Relationship: user-requested total-token × valid-quality scatter | One 1.2 Run, complete total + valid quality | Empty state is necessary when no effective-quality value is valid; do not invent points. |
| tokens-raw-v6.png | Relationship: raw v6 pass results against total tokens | One 1.2 Run, complete total + evaluated raw pass IDs / 57; label each slot | Explicitly unvalidated raw y-axis; at most 20 points, no fitted line; missing x excluded. Blue circles / ochre triangles. Check overlaps. |

No trend chart: generation order is randomized within pairs and a single batch is not historical trend evidence. No causal claim or significance claim is planned. Complete-case token differences may be selection-biased. The user-requested scatter is retained even when few or no valid coordinate pairs exist; accompanying exact tables and null counts state the limitation.

Report QA must use actual completed data, evaluate uniqueness/counts/allowed types/null rates/JSON-SQLite joins, verify isolated restored-only aggregation, inspect all exported charts in the Markdown context, and scan intended public artifacts for secrets. Preparation of this note is not evidence that those final checks have passed.
## Gitへの保存

この環境は `core.autocrlf=true` のため、提出フォルダの `.gitattributes` で改行変換を無効にします。CSV・JSON・Notebook・図・SQLiteなどの保存済みバイト列を、そのままGitへ登録するためです。原本と提出物のhashは別々に保持します。
