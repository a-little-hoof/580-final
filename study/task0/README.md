# Task 0: initial installed-task pilots

**Five initial NanoAgent Session pilots have completed, each with a passing task verdict.** This is one successful fresh run per installed task, followed by review of actual traces before deciding additional repetitions and final task selection. Two earlier authentication failures are retained separately. The older `../baseline/` package remains unchanged as proposed source examples; its data-filled prompts are not these Session prompts.

The user saved a fresh key privately before these five runs. Successful live model responses establish that authentication now works; no credential content was inspected. The [pilot results](summaries/pilot-results.md) and [graph accounting](summaries/graph-accounting.md) distinguish exported outer-loop usage from nested task calls. These initial pilots do not establish a comparative success rate or an improvement benefit. The user has approved lossless compact formatting as the next intervention; implementation and evaluation remain pending.

| Installed plugin | Successful session | Saved evidence |
| --- | --- | --- |
| Log Triage | `ada61e74-781e-4e83-b918-82cc7da14490` | [Provenance](evidence/ada61e74-781e-4e83-b918-82cc7da14490/provenance.json) |
| Cipher Crack | `fb61b2be-3336-416d-8d1c-7480aae5e544` | [Provenance](evidence/fb61b2be-3336-416d-8d1c-7480aae5e544/provenance.json) |
| Path Probe | `e4b4cb31-44c9-47a5-b390-300076d4c9b1` | [Provenance](evidence/e4b4cb31-44c9-47a5-b390-300076d4c9b1/provenance.json) |
| Regex From Examples | `52ef7dc7-3011-4f67-8972-c07f6dde7d5c` | [Provenance](evidence/52ef7dc7-3011-4f67-8972-c07f6dde7d5c/provenance.json) |
| Stat Pick | `68441299-e93a-43e2-a8b4-61bd06864a31` | [Provenance](evidence/68441299-e93a-43e2-a8b4-61bd06864a31/provenance.json) |

Each evidence folder preserves the synced `chat.json`, `turns/001/graph.json`, `turns/001/messages.json`, UI screenshots/accessibility snapshots and file hashes. Session IDs, exact prompts and system-prompt hashes are recorded in the manifest. All five actual task names and case inputs match the plan. Sampling settings and effective task limits were not captured by these exports and remain unknown.

## Preserved authentication failures

Two earlier fresh Log Triage sessions encountered **401: API key expired** before a model response or task invocation. These are authentication failures, not incorrect task answers; their correctness, token counts and timings remain unknown. The second failure followed an earlier report that the key was replaced. Both remain intact alongside the later successful fresh-key run.

| Attempt | Session | Evidence |
| --- | --- | --- |
| First request | `9e89c81d-4e2e-41ee-bdec-16e36ff4c9b0` | [Original export](exports/log-triage-2026-11-23.jsonl), [screenshot](../observations/2026-11-23/log-triage-auth-expired.png), [accessibility snapshot](../observations/2026-11-23/log-triage-auth-expired.txt) |
| Fresh session after reported key replacement | `5d975327-6f72-4bed-8dbd-2cc61eb39266` | [Combined export containing both errors](exports/log-triage-after-key-replacement-2026-11-23.jsonl), [screenshot](../observations/2026-11-23/log-triage-key-retry.png), [accessibility snapshot](../observations/2026-11-23/log-triage-key-retry.txt) |

Evidence and exact prompt hashes are recorded in the manifest. The final `log-triage-pilots-completed-2026-11-23.jsonl` export contains both errors and the successful pilot. Use **only that latest Log Triage export** when summarizing current pilots; the two older overlapping exports remain preserved as original evidence.

The [source diagnosis](../../docs/TRACE_ACCOUNTING.md) found that a successful Settings Save updates the environment and clears cached model, catalog and registry state; the next new run builds a fresh model. That path does not require an app restart. A masked saved value and format validation alone do not establish provider validity; the later successful live responses provide evidence that authentication recovered.

## Current task configuration

Current Settings UI shows `deepseek/deepseek-v4-flash-0731` with no model selector. Record this single-model limitation; it does not satisfy the assignment's multiple-model requirement. No preview improvement has been implemented.

| Installed plugin, all v0.1.0 | Task | Case | Planned prompt |
| --- | --- | --- | --- |
| Log Triage (`log-triage`) | `triage-log` | `edge-proxy` | Run the triage-log task on the edge-proxy case. |
| Cipher Crack (`cipher-crack`) | `crack-cipher` | `telegram` | Run the crack-cipher task on the telegram case. |
| Path Probe (`path-probe`) | `find-route` | `quarry` | Run the find-route task on the quarry case. |
| Regex From Examples (`regex-infer`) | `infer-pattern` | `widget-code` | Run the infer-pattern task on the widget-code case. |
| Stat Pick (`stat-pick`) | `answer-question` | `sensor-drift` | Run the answer-question task on the sensor-drift case. |

The installed regex task is a different task from the archived `write-regex` / `octet` example. Case-only requests preserve each installed task's tool-mediated access to its data. Keep hidden reference tools, source checkouts and researcher-side audits outside evaluated agents' task workspaces.

For the first Log Triage attempt, the intended submitted text was `Run the triage-log task with input {"case":"edge-proxy"}.`; native UI smart quotes changed a closing quotation mark. The exact exported prompt and its hash are recorded in the manifest. The natural-language prompts above avoid that quoted-JSON input issue for subsequent attempts.

## Recording each pilot

1. Use the plugin Dashboard's **nanoagent → New session**. Generic chat defaults to PI and is not this baseline. Submit one task request, retaining the exact actual prompt, session ID, plugin/source version, model and settings.
2. Save every attempt, including infrastructure errors. A task attempt needs the matching task invocation and its verifier result; a prose answer alone is insufficient. Record success from `verdict.valid`, not just a numeric score: Cipher Crack can give `score: 1` with `valid: false`.
3. Save **Dashboard → Download traces (JSON)**. The file is JSONL and includes the user's historical sessions. Preserve its original bytes and SHA-256, then select these pilot session IDs for analysis. Keep supporting screenshots and any final outputs. Record export provenance and missing evidence explicitly.
4. NanoAgent chat records have `type: "chat"`, `kind: "nanoagent"`, `session_id` and `turns`. Parse each relevant `turns[].tools[].output` JSON string for `{output, verdict}`. Retain `turns[].error`, actual `prompt`, version and model. Use `turns[].metrics.usage` for available input/output/cached tokens and `duration_s`, `model_s`, `tools_s` for time. Missing values stay unknown. ATIF `messages.final_metrics` may default missing token data to zero, so it is not proof of a measured zero.
5. Inspect task behavior, tool-output sizes, failures and evidence completeness after these initial pilots. Choose additional repetitions before collecting that comparison, and retain all attempts. Do not use Dashboard averages that include historical sessions as project averages. Complete the required initial exploration before implementing the preview feature.

The [manifest](manifest.json) records exact advertised source commits, local contract/verifier hashes, case inputs, planned prompt hashes and observed attempt status. Advertised source provenance was checked against clean local Git checkouts; installed package bytes were not independently hashed. Audits: [Log Triage](log-triage-audit.md) and [Path Probe, Regex From Examples, Stat Pick](../observations/2026-11-23/plugin-contracts-path-regex-stat.md).

## Offline trace summaries

[summarize_traces.py](summarize_traces.py) uses only the Python standard library and explicit JSONL files. It makes no model calls. The public outputs cover the [seven current attempts: five completed pilots and two authentication errors](summaries/current-pilot.md), with accompanying JSON preserving provenance, exact prompts, model metadata, verdicts and unknown metrics. Older historical-session exports and descriptive summaries are local continuation material excluded from this repository and source ZIP; the historical observations below are scope context, not additional submitted experimental evidence.

The five historical October 26 sessions (America/Chicago) contain 27 turns and 23 task invocations: 20 valid task verdicts and three tool errors without verdicts. Five turns contain no task invocation. Several turns are corrections or retries in a continuing conversation. These are historical observations, not new matched pilots or independent repetitions. The exports show NanoAgent `0.7.0` and plugin `0.1.0`, but do not pin those historical deployments' source hashes.

The script counts reported usage once. It does not add the duplicate `calls` ledger or repeated ATIF history. A source audit and one historical graph comparison establish that exported token/cost totals cover the outer chat loop and exclude nested task model calls. These are not full task totals. Historical nested task activity exposes tool names and error flags, but no separate usage or raw internal tool-output bodies. Preserve each successful session's `chat.json`, `turns/001/graph.json`, and `turns/001/messages.json` (and corresponding files for additional turns) for fuller per-call accounting. Returned task-wrapper lengths are labelled accordingly. Cost records differ between turn metrics and the ledger and are preserved separately without asserting actual provider spend. See [TRACE_ACCOUNTING.md](../../docs/TRACE_ACCOUNTING.md) for the audited scopes and version-dependent timing behavior.

From the project root, reproduce the summaries and offline regression checks with:

```sh
python3 study/task0/summarize_traces.py --dataset-role current_pilot \
  --json-out study/task0/summaries/current-pilot.json \
  --markdown-out study/task0/summaries/current-pilot.md \
  study/task0/exports/log-triage-pilots-completed-2026-11-23.jsonl \
  study/task0/exports/cipher-crack-pilots-completed-2026-11-23.jsonl \
  study/task0/exports/path-probe-pilots-completed-2026-11-23.jsonl \
  study/task0/exports/regex-infer-pilots-completed-2026-11-23.jsonl \
  study/task0/exports/stat-pick-pilots-completed-2026-11-23.jsonl

python3 -m unittest discover -s study/task0 -p 'test_summarize_traces.py' -v
```

Seven synthetic regression checks cover unknown metrics versus ATIF zeros, `valid=false` with `score=1`, duplicate accounting/history, preserved error/retry calls, Unicode byte lengths, unverified prose answers, partial metric sums and duplicate-session rejection. These checks are software validation, not experimental runs.
