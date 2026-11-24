# Controlled benchmark workflow

`study/controlled/rush_benchmark.py` prepares publication payloads offline, then exposes `publish`, `start`, and `collect`. The original CLI v0.2.0 implements full and compact conditions. Both modes completed development Harness terminal runs; those exploratory runs are excluded from the final comparison. The first Log Triage publication failed before model dispatch with HTTP 422 `pin_failed` because `answer_skeleton()` rejected an enum-only `$.case` schema. The recorded local compatibility patch now handles finite scalar enum placeholders without changing plugin schemas or verifiers; see [platform-fix](../study/controlled/development/platform-fix/README.md) and [its application record](../study/controlled/development/platform-fix/applied.json).

All five cases were then published and verified. Native scored Log Triage smoke run `b8c33b34-30f8-4884-a576-37995327cdc8` passed with complete captured source coverage. The study was frozen at `2026-11-24T04:39:38Z` and completed all 50 logical trials in 50 actual attempts. [freeze.json](../study/controlled/final/freeze.json) pins the common model, providers, limits, wheel/module hashes, case identities and seed-580 schedule; [progress.json](../study/controlled/final/progress.json) records the completed execution. These commands document the interface; existing final trial IDs and state files are evidence, not a request to start additional trials.

The final [analysis](../study/controlled/final/analysis/analysis.json) records 23/25 full and 25/25 compact native passes, with matching host audit outcomes. Full Regex repetition 3 timed out on the third model request, leaving its total usage/cost unknown; full Cipher repetition 2 returned an inconsistent key/plaintext answer. Both failures remain in all-trial tables. Paired efficiency summaries use only the 23 pairs with two successful audited trials and keep those sample counts explicit. [results_summary.md](../study/controlled/final/analysis/results_summary.md) reports the measurements; success differences in five repetitions per case do not establish a general reliability advantage.

## Public fixture boundary

The helper reads `study/controlled/fixtures/manifest.json` and requires each selected case directory to contain exactly `input.json` and `prompt.txt`, with matching manifest byte lengths and SHA-256 hashes. It rejects symlinks, traversal, extra files, mismatched content, and prompts with leading or trailing whitespace. It never trims prompts silently. Source code, private references, validators, provenance manifest, and the upstream license file are not uploaded as agent fixtures.

The pinning API's `case_file` is **YAML text**, while `files` is a map of relative filenames to base64 bytes. JSON is a YAML subset, so the helper emits this JSON document as the YAML string without adding a YAML dependency:

```json
{
  "plugin": "log-triage",
  "task": "triage-log",
  "cases": [{
    "prompt": "<exact prompt.txt content>",
    "arguments": {"case": "edge-proxy"},
    "fixtures": "public"
  }],
  "refuse": []
}
```

The only upload keys are `public/input.json` and `public/prompt.txt`. `fixtures` names the directory; it is not a map of files. The worker mounts that directory's contents as `input.json` and `prompt.txt` at the agent workspace root. The platform pins the plugin's native reference privately. No expected answer is included in this payload.

Controlled plans require `internet_access=false` because the upstream public repositories contain private solution tables or holdouts. The gateway still supplies the permitted model path. The two-file boundary and network closure do not establish an independent hidden test set: these are five public course-task adaptations, as recorded in the fixture manifest.

## Offline preparation and review

Run from the project root. `prepare` uses the Python standard library, loads no connection credentials, and sends no request. The approved common limits in `study/controlled/limits.json` are:

| Field | Value |
| --- | ---: |
| `wall_time_ms` | 180000 |
| `max_model_calls` | 12 |
| `max_output_tokens_per_call` | 32768 |
| `max_cost_usd` | 0.05 |
| `internet_access` | false |

The output cap was raised before publication from 4096 to the current RUSH default, 32768, because upstream `limits.js` documents DeepSeek Flash reasoning truncation at 4096. Both conditions use the same cap. The cost value is a per-attempt admission ceiling, not an estimate or measured charge. Other server defaults become part of the immutable published benchmark and must be inspected in the saved publication detail. The run API does not accept a model override. The server pins model, endpoint, providers, and limits; collection checks that the run matches that publication.

```sh
python3 study/controlled/rush_benchmark.py prepare \
  --fixtures study/controlled/fixtures/manifest.json \
  --case log-triage/edge-proxy \
  --namespace comp580-yw251-compact-v1 \
  --limits study/controlled/limits.json \
  --out study/controlled/plans/log-triage.json
```

The five generated plans are `plans/log-triage.json`, `cipher-crack.json`, `path-probe.json`, `regex-infer.json`, and `stat-pick.json`. Each records the source manifest hash, exact prompt and fixture hashes, full request payload, and payload hash. Names begin `comp580-` and include a content-derived suffix. `prepare` refuses to overwrite a different existing plan; choose a new plan path and namespace when changing a frozen design. Identical reruns are harmless.

Review the decoded public files, exact prompt, limits, task/case IDs, and planned custom command before publishing. Offline tests cover credential-free preparation, fixture isolation, state replay after a lost response, every attempt's evidence, nullable accounting, and safe answer extraction:

```sh
python3 -m unittest discover -s study/controlled/tests -p test_rush_benchmark.py -v
```

All five generated payloads also passed the current installed NanoAgent's **offline** `parse_case_file`, `lint`, `fixture_files`, and `archive` functions, including byte-identical prompt and unpacked fixture hashes. No reference tool, model, or connection helper was executed in that check.

## Publish and start after review

Use the installed Python so the helper can import the official NanoAgent client and its runtime dependencies. The helper lazily invokes `nanoagent.cli.harness.connection`, `find_lab`, and `find_plugin` only for live commands. The official helper uses the app's saved member session. It does not read the provider API key. Session tokens and request headers are never serialized, printed, or passed on the command line. Do not run these commands until the prepared payload and installed agent have been reviewed.

```sh
RUSH_PY='/Users/wangyifei/Library/Application Support/lab.mochi.lab/app/2026-11-23T03-56-59-663Z-7ac1754/mochi-lab/nanoagent/.venv/bin/python'
"$RUSH_PY" study/controlled/rush_benchmark.py publish \
  --plan study/controlled/plans/log-triage.json \
  --state study/controlled/state/log-triage.json \
  --workspace comp-480-580
```

Publishing posts `{name, plugin_id, case_file, files, limits}` to the selected workspace's `/benchmark/benchmarks/pinned`. It verifies the installed plugin version before publication, then verifies the published task, exact prompt, fixture hashes, and every explicit limit against the plan. The complete publication detail records the actual pinned model and all defaults. If a request times out, preserve the state and retry this command. The deterministic benchmark name makes identical publication replay immutable; changed server defaults can instead produce a name conflict, which requires investigation rather than silently publishing different settings.

Install and keep the CLI first. Any installed custom program whose command matches the server's `rush <program> [safe arguments]` grammar is supported; the case prompt is appended as the last argument. No shell expressions, quotes, environment assignment, or arbitrary executable path is accepted. For the current full baseline:

```sh
"$RUSH_PY" study/controlled/rush_benchmark.py start \
  --plan study/controlled/plans/log-triage.json \
  --state study/controlled/state/log-triage.json \
  --harness 'rush comp580-agent --condition full' \
  --replicate smoke-full-01
```

`start` posts only `{benchmark_id, harness, idempotency_key}`. Its key is derived from the publication payload hash, benchmark ID, exact command, and replicate label. The key is written to state **before** the request. Repeating the same command resumes the same logical trial, even if the first response was lost; changing the replicate or command intentionally creates a different trial. Use a distinct, frozen label for each final replication. The helper does not install software, start shell sessions, cancel existing work, or request reruns.

A single exclusive lock protects each state file. A crash may leave `.lock`; remove it only after confirming no helper still uses that state. Preserve state files because they are the local manifest linking reviewed plans to published benchmark IDs, exact start requests, run IDs, observations, and capture indexes.

## Collect complete evidence

Use the run ID printed by `start`. Polling waits at most 60 seconds per invocation. An unfinished run returns `pending:true` without capturing an incomplete export; repeat `collect` with the same state.

```sh
"$RUSH_PY" study/controlled/rush_benchmark.py collect \
  --plan study/controlled/plans/log-triage.json \
  --state study/controlled/state/log-triage.json \
  --run-id <run-uuid> \
  --out study/controlled/evidence \
  --wait-seconds 30
```

The helper accepts only a run recorded in that state. It requires complete/canceled status and all recorded attempts sealed, verifies the run's pinned configuration and public case against the publication, and creates a new timestamped capture directory. Existing evidence is never replaced.

Each capture retains:

- Full run detail and its original native export bytes, plus the exact selected run record.
- Every attempt, including failed attempts and automatic worker retries: execution status, native verdict, checks, verifier error, coverage, and raw nullable metrics.
- All paginated events and pages, referenced payload bytes with verified hashes, accounting, spans/links, and terminal recording. Native export also retains model request/response bodies and their redaction metadata.
- The worker's observed `result.read` answer, preserving whether that event was absent; when uploaded, the workspace archive with verified byte length/SHA-256 and the root regular `answer.json` bytes. No archive files are extracted onto the host.
- A capture index with hashes and byte lengths, actual attempt count, and explicit issues for missing workspace/answer, event cursor mismatch, or truncated span listings.

A missing artifact or metric remains missing. A sealed attempt does not guarantee provider cost settlement. A later `collect` creates another snapshot to retain updated accounting without erasing the earlier evidence. `capture_issues` must be reviewed before analysis. The helper does not convert absent cost into zero, infer total provider charges, or automatically substitute local validator success for the native verdict. Host-side validators can additionally check the captured answer after collection.

The trace export API filters by plugin/time, not run ID. The helper requests the signed-in member's default export with **no `member` parameter**, saves its exact bytes, and selects the intended run locally. Consequently `native-export.jsonl` may contain other records belonging to the same user in that time window; do not publish it without reviewing that scope. It never requests another member's data. Workspace download paths are constructed from the selected attempt UUID rather than following arbitrary URLs.

## Logical trials and automatic worker retries

A plan of five cases × two conditions × five replications is **50 logical trials**, not necessarily 50 attempts. The worker converts a failed execution whose model calls all returned 429/5xx or were unreachable into `worker_error`; lease expiry can also produce a worker error. The server automatically queues another attempt up to three consecutive worker-error attempts, retaining the earlier attempts. The helper creates no extra logical trials for these errors and captures every attempt, not just the latest scored one.

Each capture records `logical_trial_count:1` and `actual_attempt_count`. Report logical trials, all attempts, failures, and any unsettled accounting separately. The $0.05 limit applies per attempt, so 50 × $0.05 is not a total-study charge ceiling when automatic retries occur. Runtime and cost reporting must include the chosen retry-accounting policy explicitly and retain the raw values.

## Contract provenance

Read-only source audit used pinned NanoAgent repository commit `189454718dad10404b92147b52dc07b3e6a8e598` and the installed app engine `2026-11-23T03-56-59-663Z-7ac1754`. Relevant source contracts:

- `nanoagent/src/nanoagent/uploaded/case_sets.py`: `CaseSetSpec`, `parse_case_file`, `lint`, fixture directory mapping, reserved answer paths, exact prompt restrictions.
- `helpinghands/src/server/routes/benchmark.js` and `server/benchmark/validate.js`: pinned publication, run start, attempt reads, events, accounting, recording, and payload routes.
- `helpinghands/src/server/benchmark/harness.js` and `limits.js`: custom command grammar, limit validation, and `MAX_WORKER_ATTEMPTS=3`.
- `helpinghands/src/server/postgres/benchmark.js`: immutable names, idempotency, full run/attempt/public fixture fields; benchmark attempts support terminal recording by attempt ID.
- `helpinghands/src/server/routes/trace-export.js` and `server/benchmark/export.js`: own-member export, raw call/trace data, workspace URL/hash.
- `nanoagent/src/nanoagent/cli/harness.py`: official connection discovery and current attempt/event interfaces.
- `nanoagent/src/nanoagent/uploaded/runner.py:479–485,1322–1326` and `helpinghands/src/server/postgres/benchmark-sweep.js`: provider failure classification and automatic retry policy.

Offline checks established payload/client-contract compatibility. Live publication and the captured native smoke subsequently verified installed-agent readiness, Log Triage's native verdict and the capture path. The completed final trials exercised all five published native verifiers. The original pre-patch source audit remains the provenance baseline; `platform-fix/applied.json` records the single installed runtime change. Comparative results come from final evidence and analysis, not smoke success or the existence of a publication.
