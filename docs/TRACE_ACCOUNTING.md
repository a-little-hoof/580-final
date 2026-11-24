# RUSH Lab trace accounting audit

Audited locally on November 23, 2026 (America/Chicago). No model requests, credential reads, or app changes were made for this audit.

The exported NanoAgent chat turn's token and cost fields follow the **outer chat loop**, even though the current runtime's detailed profiler also accounts for the plugin task's inner model calls. Do not label the exported token/cost totals as the complete cost of solving the task. Preserve the provenance graph alongside the JSONL export to retain inner calls.

## Sources and scope

- Installed runtime root (`R`): `/Users/wangyifei/Library/Application Support/lab.mochi.lab/app/2026-11-23T03-56-59-663Z-7ac1754/mochi-lab`.
- Installed NanoAgent source root (`N`): `R/nanoagent/site/nanoagent`.
- Reference repository root (`S`): `/Users/wangyifei/Downloads/comp580_assignment/rush_lab_project/references/nanoagent`, commit `189454718dad10404b92147b52dc07b3e6a8e598`.
- All source citations below are `root/relative/path:line`. The installed versions of `web/plugin_agent.py`, `core/agent.py`, `harness/base.py`, `profiler/__init__.py`, `trajectory/atif.py`, and `plugin/provenance.py` are byte-identical to their counterparts in `S/nanoagent/src/nanoagent`.
- The installed Python behavior was inspected directly. Hosted RUSH serialization was inspected in the pinned reference source, then checked against one existing successful historical export and its own member's synced files. The initial audit had only two current authentication failures. Subsequently all five fresh successful pilots on this runtime were checked end to end: native exported tokens/cost equal outer graph calls; UI input/output equal inclusive graph totals; exported model time equals inclusive model-call durations. See `study/task0/summaries/graph-accounting.md` and `pilot-results.md`, including evidence hashes and coverage checks.

## Why the two totals differ

| Stage | Exact behavior | Source |
|---|---|---|
| Inner task returns | `TaskTool.run` copies successful and failed calls from the task's profile, marks them `kind="tool"`, and attaches them to `ToolText`. | `N/web/plugin_agent.py:114`, especially 126–132 |
| Outer tool dispatch | Adds these attached records to the outer step profiler. | `N/core/agent.py:628`, especially 636–637 |
| Detailed profile | Sums successful call usage/cost, including `kind="tool"`; sums step totals into the run. Failed model attempts contribute time but not usage/cost. | `N/profiler/__init__.py:315`, `:351`, `:409` |
| Legacy agent result | Independently accumulates `usage` and `cost` from the outer loop's `reply` objects. `AgentResult` returns these alongside, rather than replacing them with, the detailed profile. Inner task calls are not added to this accumulator. Compaction is recorded only in the profile as well. | `N/core/agent.py:342`, `:346`, `:460`, `:551` |
| Runtime response | `RunnerResult` retains legacy `result.usage`/`result.cost` separately from `result.profile`. The web `done` event sends both. | `N/harness/base.py:70`; `N/web/runtime.py:363` |
| Saved turn | `answerMetrics` prefers top-level `usage`/`cost` over `metrics.usage`/`metrics.cost`, then copies timing fields from the profile. It drops detailed `steps`. | `S/helpinghands/src/server/ai.js:472`; `S/helpinghands/src/server/app-runs.js:11` |
| JSONL export | Reads the saved chat turns, adds their outer ATIF `messages`, and attaches the separate app-call ledger. It does not attach the provenance graph. | `S/helpinghands/src/server/postgres/trace-export.js:99`; `S/helpinghands/src/server/fs/chats.js:79`; `S/helpinghands/src/server/benchmark/export.js:144` |

This is an accounting omission in the audited serialization path, not evidence that the inner task made no model calls. The five current successful exports subsequently confirmed this behavior against their graphs; retain this check for later versions.

## Timing, tokens, and cost

- **Latency:** `duration_s` is run wall-clock duration. Do not add it to model or tool time.
- **Current detailed model time:** `model_s` sums durations of outer and inner model requests, including failed attempts. Concurrent calls can therefore make this sum exceed elapsed wall time. `tools_s` is tool-dispatch wall time minus the union of nested model-request intervals, so nested inference is not also charged as tool time. Sources: `N/profiler/__init__.py:341`, `:356`, `:362`, `:198`.
- **Historical timing differs:** the checked October run's `model_s` equals only its outer calls; its task's inference remains within `tools_s`. Do not apply the new runtime's time partition retroactively.
- **First-token and generation times:** these are not full nested-call totals. Run `generation_s` explicitly excludes `kind="tool"` calls. Source: `N/profiler/__init__.py:194`, `:210`.
- **Cached tokens:** `cached_tokens` is a subset of `prompt_tokens`; `reasoning_tokens` is a subset of `completion_tokens`. Do not add either to `total_tokens`. Preserve missing values as unknown, rather than manufacturing zeros. Source: `N/profiler/__init__.py:49`.
- **Cost:** this native OpenRouter chat backend computes cost from configured prices and token counts: `(prompt_tokens * input_price + completion_tokens * output_price) / 1e6`. It is not the provider's invoiced charge, and this formula does not apply a separate cache-read discount. Sources: `N/inference/providers.py:51`, `N/inference/backends/sglang.py:404`, `N/inference/backend.py:116`.
- **Ledger:** `calls[]` contains app-turn accounting rows, not an additional set of provider calls to add. For local-computer runs the server explicitly records `cost_usd=0`, while retaining reported usage and timing. Dashboard summaries sum those ledger fields and count non-null measurements per field. Sources: `S/helpinghands/src/server/ai-metering.js:32`, `S/helpinghands/src/server/postgres/tenancy.js:154`, `S/helpinghands/src/server/postgres/sessions.js:10`, `:55`.
- **Failed turns:** app-run failures save `metrics:null`. ATIF's fallback zeros do not establish zero usage or zero cost. Sources: `S/helpinghands/src/server/app-runs.js:163`; `N/trajectory/atif.py:92`.

## One observed export round trip

Only one historical successful turn was inspected for this comparison; it is descriptive evidence, not a new experimental run.

- Plugin: Log Triage; session `1ddb6b46-d67c-4775-8a8b-0d2189f1f35c`; first turn.
- Export: `study/observations/historical/exports/log-triage.jsonl`.
- Preserved comparison artifacts: `study/observations/historical/accounting-audit/log-triage-turn-001-graph.json`, `provenance.json` (source paths and SHA-256 hashes), and `comparison.json` (exact numeric comparison and round-trip checks).
- Graph SHA-256: `0b764c376cce1f7afd72de8718e97acb9a9ac132520431489eb72d44d1f5064a`.
- Synced folder: `/Users/wangyifei/rushlab/a-little-hoof/comp-480-580/plugins/log-triage/chats/2026_10_27_run_the_triage_log_task_on_the_night_batch_case`.
- The local `chat.json` first turn equals the exported first turn after removing the export's added `messages` field. Local `turns/001/messages.json` equals that exported `messages` object exactly.

| Source | Completed model calls | Prompt tokens | Completion tokens | Total tokens | Reported cost | Model-call seconds |
|---|---:|---:|---:|---:|---:|---:|
| Graph outer nodes | 2 | 1,259 | 157 | 1,416 | 0.00007865 | 4.0106335422 |
| Graph inner task nodes | 4 | 3,477 | 208 | 3,685 | 0.00019465 | 6.8008776251 |
| Exported `turn.metrics` | not a call count | 1,259 | 157 | 1,416 | 0.00007865 | 4.0106335422 |

Both graph groups report zero cached tokens. The exported usage and cost equal the outer group exactly and omit the inner group. The first `calls[]` ledger row likewise reports 1,259 input and 157 output tokens, but `cost_usd=0`. The export's latency is 17.6809276671 seconds and tool time is 13.6696507500 seconds.

## Minimal evidence capture and summary labels

Keep the existing supported `rushlab nanoagent export plugin=<id> out=<file>.jsonl` export. In addition, copy each successful pilot's synced chat folder, including `chat.json`, `turns/001/graph.json`, and `turns/001/messages.json`, into its evidence directory and hash those files. Match the session using `chat.json.session`, rather than relying solely on the folder title. No extra inference call is necessary.

The graph is the built-in saved record of nested task work: `GraphRunner` merges task graphs under the enclosing task node (`N/web/plugin_agent.py:197`); decision nodes carry `modelCalls` (`N/plugin/provenance.py:257`); agent-loop nodes carry their own model calls but exclude attached `kind="tool"` calls to avoid duplication (`N/plugin/provenance.py:370`). RUSH saves that graph as `turns/<n>/graph.json` (`S/helpinghands/src/server/fs/chats.js:51`). The graph can include task reference answers, so retain it as evidence and do not feed it to benchmark agents.

Recommended minimal summarizer change, without changing its arithmetic:

- Keep summing `turn.metrics` once and do not add `calls[]` or ATIF totals.
- Label token/cost fields **reported outer chat-loop totals; nested task calls excluded in the audited NanoAgent path**. For other engines or trace formats, leave coverage unspecified until checked.
- Keep historical timing interpretation separate from the current runtime's source-defined timing partition.
- Link this audit and state whether each record has an accompanying graph. Complete graph accounting for the five current pilots is now implemented in `study/task0/analyze_graphs.py`; its results remain separate from the outer-only summary.

This audit did not change the summarizer's arithmetic. The parent task applied the label corrections and regenerated the summaries separately.

## API-key refresh note

A successful Settings **Save** is already the supported live refresh. `R/runner/lab.mjs:841` writes the replacement, calls `PUT /v1/keys`, and requires a 200 response. `N/web/app.py:325` updates the environment, clears the model catalog, retires the existing plugin model and forgets runner models. `N/harness/nanoagent.py:143` documents that the next run builds a model with the current credentials. Runs already in flight may retain their old model; a new run after acknowledged Save should not need an app restart.

A masked saved key proves only that a nonempty value is stored (`R/runner/lab.mjs:291`). Save checks syntax, not provider validity. The Settings credit request tests the active key against OpenRouter without inference, but the current UI hides credit-request failures (`S/helpinghands/src/pages/settings/_ApiKeys.js:25`; `N/web/app.py:358`). Consequently, a saved-looking key and a subsequent 401 can coexist. The two earlier authentication failures remain preflight failures with unknown metrics, not task failures or scored trials. A later user-saved key successfully authenticated all five fresh pilots.
