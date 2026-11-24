# Harness contract audit — 2026-11-23

**Current evidence:** Computer Use and the supported host CLI reached own Harness session `2f2c8d4c-186c-4cf3-8379-a5124e0d5428`. The VM reported Python 3.12.16, model `deepseek/deepseek-v4-flash-0731`, and an output cap of 32768. Original CLI v0.2.0 was installed; full/compact development runs and native scored Log Triage smoke `b8c33b34-30f8-4884-a576-37995327cdc8` are captured. All five cases were published before the seed-580 freeze at `2026-11-24T04:39:38Z`. The study completed 50 logical trials/50 attempts, with 48 native passes and both failures retained. See [the frozen record](../study/controlled/final/freeze.json), [final analysis](../study/controlled/final/analysis/analysis.json) and [workflow](BENCHMARK_WORKFLOW.md).

The supported path for an original CLI is **install it in a Harness terminal and run `rush <program>`**. A recorded terminal session is unscored; automatic deterministic scoring requires a published benchmark and a separate benchmark run. A custom CLI does **not** receive NanoAgent's plugin tools. These facts must shape the adapter and evaluation design before implementation.

The original audit below was read-only and preceded those live actions. Its source fingerprints describe the **pre-patch** installed runtime. Subsequent native publication exposed an enum-only answer-template compatibility issue; only `uploaded/outcome.py` was patched and the app restarted, as recorded in [platform-fix/applied.json](../study/controlled/development/platform-fix/applied.json). That change is frozen, shared by both conditions, and does not alter plugin verifiers or references. Other inspected source hashes retain their original audit scope.

## Evidence and version scope

- Course guide and server source: local reference commit `189454718dad10404b92147b52dc07b3e6a8e598`, in `references/nanoagent`. The [course guide](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/rush-lab-student-guide.md#L1) says to run NanoAgent first, compare the same user prompt with other agents, and record success and efficiency. Its five repetitions inform the controlled comparison; the five prerequisite Session pilots are complete.
- Inspected engine: `2026-11-23T03-56-59-663Z-7ac1754`, under `/Users/wangyifei/Library/Application Support/lab.mochi.lab/app/2026-11-23T03-56-59-663Z-7ac1754/mochi-lab/nanoagent`. Eight inspected Python runtime files and the bundled worker configuration were byte-identical to the pinned reference before the separately recorded `outcome.py` patch (hashes below).
- The installed engine does not include the course-guide Markdown or the web server source in the inspected resource tree. Server/API source findings describe the pinned source, not a separately verified server deployment hash. Later native publication, smoke and trial captures verify the exercised routes without establishing the entire deployed server revision.
- The older [uploaded-harness document](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/nanoagent/docs/contracts/uploaded-harness-v1.md#L5) still describes custom source ZIPs and builds. Current server/runtime source instead uses installed terminal CLIs. Likewise, some API examples retain removed fields. Prefer the concrete route validation and current worker implementation below.

## Terminal and custom CLI contract

In the app, open **Harness**. The existing commands are `nanoagent`, `claude`, `codex`, `pi`, `hermes`, and `dsh`; `mgen -p "<request>"` is a one-shot NanoAgent invocation. These are distinct agents: the app's generic chat uses Pi, while plugin Session uses NanoAgent.

A host terminal with the installed NanoAgent environment can open the same free-form terminal using:

```sh
nanoagent harness plugin=log-triage harness=shell home=<new-output-folder>
```

This requires an interactive terminal and the signed-in running app. The CLI itself uses the app's connection without asking the user to paste the provider key. It joins an existing terminal session if one is active. Do not supply `prompt=` or `task=` to `harness=shell`.

Inside the Harness terminal, the original package installs the bare executable `comp580-agent` through `pip install <pinned-package-location>`. Then `rush comp580-agent <arguments>` records the process and its gateway calls under that program. `rush help` describes the interface. Installed packages go under `.rush/python` or `.rush/npm`; after the terminal is ended and kept, the worker can pin that installation for benchmark cases. A loose host script path is not an installed benchmark agent. Missing installation fails `agent_not_installed`.

For an original agent's model client, consume the supplied values without printing them:

| Input | Meaning |
| --- | --- |
| `OPENAI_BASE_URL`, `OPENAI_API_KEY` | Attempt gateway and scoped token for an OpenAI-compatible client |
| `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY` | Equivalent Anthropic-compatible gateway configuration |
| `RUSH_MODEL` | Exact permitted model identifier; do not replace it with a provider default |
| `RUSH_MAX_OUTPUT_TOKENS` | Effective per-call output cap |
| `RUSH_REQUEST`, `RUSH_WORKSPACE` | Request JSON path and bounded workspace |
| `RUSH_PROMPT` | Exact published case prompt in a scored case |

`rush` assigns each subprocess run its own scoped token so simultaneous programs' model calls remain distinguishable. A simple custom CLI can use Chat Completions at the provided base URL. The gateway records forwarded requests, responses, usage and provider accounting. It rejects another model (`model_not_pinned`), sets provider routing, adds usage reporting, and adds the benchmark answer-format system text when applicable. Preserve the published user prompt exactly; wrapping it in additional text can fail `first_prompt_rewritten`.

Sources: [shell environment and headless launch](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/nanoagent/src/nanoagent/uploaded/reference_harnesses/shell/shell.py#L41), [rush wrapper/help](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/nanoagent/src/nanoagent/uploaded/reference_harnesses/shell/rush.py#L29), [kept installation requirement](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/nanoagent/src/nanoagent/uploaded/runner.py#L338), [gateway policy](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/nanoagent/src/nanoagent/uploaded/policy.py#L100).

## Scored benchmark API and public input boundary

The pinned server accepts `POST /api/workspaces/{wid}/benchmark/sessions` only with `harness: "shell"` and `interactive: true`. Its optional `model` applies to that unscored terminal. The installed `nanoagent harness` code still advertises `harness=codex prompt=...` and sends it to this route; that example conflicts with current server validation and should not be used as the scored-run recipe.

The supported scored route is:

1. Publish a case folder using `POST /api/workspaces/{wid}/benchmark/benchmarks/pinned` with `{name, plugin_id, case_file, files, limits}`. `case_file` is YAML text; `files` maps relative filenames to base64 bytes. The app's benchmark publishing UI drives the same workflow. The worker obtains the installed plugin and pins references privately.
2. Submit `POST /api/workspaces/{wid}/benchmark/runs` with **only** `{benchmark_id, harness, idempotency_key}`. `harness` can be `nanoagent` or an installed original command such as `rush comp580-agent --condition full --prompt`. The exact case prompt is appended as its final argument. The route runs the entire published suite; use a one-case suite for a one-case smoke test. The older example containing `cases` and `interactive` is inconsistent with the validator.
3. Retain the immutable benchmark/package/case digests, run and attempt IDs, final answer, verifier decision, raw events, accounting and workspace snapshot. Re-running creates new evidence; re-reading evidence does not.

A minimal case file has this shape (illustrative, **not yet sufficient public input for a custom agent**):

```yaml
plugin: log-triage
task: triage-log
cases:
  - prompt: Run the triage-log task on the edge-proxy case.
    arguments: {case: edge-proxy}
    fixtures: null
refuse: []
```

The request visible to a case agent includes task identity/description, case ID, exact prompt/hash, answer-format instructions, limits and gateway endpoints. Typed `arguments`, input schema, reference answers and verifier code remain outside its workspace. `tools.available` starts empty; plugin tools are opened separately for NanoAgent alone with its own broker token. An original CLI cannot invoke the Session task merely by copying its case-only prompt.

For coding agents, the worker seeds `answer.json` with the public output schema. The agent fills every field, preserves the shape and stops; `{"refused":"<reason>"}` is reserved for an unanswerable input. The frozen workspace answer is passed to the plugin's deterministic verifier. A free-form terminal has no case or verifier and ends `ended`, not passed.

**Adapter implication:** supply explicitly public fixtures and original read/search/execute tools before evaluating the custom CLI. Case names alone do not reveal the log, ciphertext, graph, visible regex examples or statistical readings. Keep hidden solutions and researcher source audits out of agent workspaces. Exposing the complete graph or logs upfront changes the information-access task relative to Session's tool-mediated version; report that adaptation and rerun both custom conditions on identical adapted inputs. Do not present those trials as an exact reproduction of the Session pilots. The implemented formatting intervention operates at the custom CLI's public-data tool boundary; no preview feature is included.

Sources: [session route](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/helpinghands/src/server/routes/benchmark.js#L167), [run validation](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/helpinghands/src/server/benchmark/harness.js#L8), [API publication and run contract](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/nanoagent/docs/contracts/rush-benchmark-api.md#L125), [case-file types](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/nanoagent/src/nanoagent/uploaded/case_sets.py#L38), [public request and NanoAgent-only tools](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/nanoagent/src/nanoagent/uploaded/runner.py#L1409), [answer instructions](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/nanoagent/src/nanoagent/uploaded/outcome.py#L69).

## Model selection: no usable second model established

Session model selection is fixed to `deepseek/deepseek-v4-flash-0731`. A shell session has a supported `model=` CLI/API parameter, but the server checks it against the worker's advertised priced models. The current installed `deploy/worker/worker.openrouter.yaml` prices **only that same model**, so the source-defined path rejects another model as `unknown_model`. Changing an SDK model alone also fails at the gateway. Joining an existing terminal returns that session, so it does not create a different-model experiment.

Published benchmarks are fixed by the server's `RUSH_BENCHMARK_MODEL`/endpoint/provider configuration; callers cannot override `model` in benchmark publication or run requests. The environment override is a deployment setting, not a member setting. Thus no ordinary supported second-model route is established in the current setup. Record this limitation; a separately authorized deployment/worker configuration or independent provider workflow would be a different setup requiring its own validation.

Sources: [Session model](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/helpinghands/src/server/ai-settings.js#L13), [shell model checks](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/helpinghands/src/server/benchmark/service.js#L63), [worker allowlist validation](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/helpinghands/src/server/benchmark/plan.js#L7), [benchmark model configuration](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/helpinghands/src/server/benchmark/limits.js#L49), [installed-equivalent worker configuration](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/nanoagent/deploy/worker/worker.openrouter.yaml#L18).

## Metrics and evidence requirements

| Evidence | Interpretation and limits |
| --- | --- |
| Attempt `metrics` | `input_tokens`, `output_tokens`, `total_tokens`, `cache_read_tokens`, `cache_write_tokens` are known subtotals; retain corresponding `missing_calls`, `usage_complete` and `model_calls`. A numeric zero with missing calls is not a complete measured zero. |
| Attempt timing | `elapsed_ms/ns` is attempt elapsed time. Advanced `outside_waits_ns`, `cpu_ns`, `no_request_ns`, `estimated_ns` can be null with explicit reasons; `estimated_ns` is a reference-rate estimate, not observed latency. Keep `timing_method`. |
| Trace `coverage` | Preserve missing sources, rejected/lost events and truncation; source code promising collection is not evidence that a run's collection succeeded. |
| Gateway accounting | Preserve raw per-call usage and settlement state. Unsettled cost is unknown. Do not add ledger copies to request metrics. |
| Final verification | For benchmark attempts retain `execution.status`, `verdict` (`pass`/`fail`), `explanation`, `verifier_error` and checks. Session plugin tool verdicts instead use `valid`; `score` alone is insufficient. |
| Custom local tools | Record complete raw output bytes, visible bytes, hashes, elapsed time in original-agent logs. No retrieval events exist in the implemented formatting-only condition. Gateway requests show what the model saw, but do not by themselves establish the complete underlying output of in-process tools. |

The host `nanoagent harness ... harness=shell home=...` command writes `result.json`, `events.jsonl`, `accounting.json` and `terminal.log` once the session seals. Its small `result.json` omits cached-token and completeness fields, so keep the full attempt/trace evidence as well. The Dashboard's derived CLI chat rows deliberately leave end-to-end latency and tool time unknown; process duration, model-call duration and Session agent latency are different measurements. Our existing `summarize_traces.py` supports NanoAgent chat exports only; it must not silently parse Harness attempts as that schema.

Sources: [metric serialization](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/nanoagent/src/nanoagent/uploaded/projection_model.py#L307), [host output files](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/nanoagent/src/nanoagent/cli/harness.py#L363), [Dashboard CLI timing limitation](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/helpinghands/src/server/benchmark/terminal-sessions.js#L92), [attempt finalization fields](https://github.com/RUSH-LAB/nanoagent/blob/189454718dad10404b92147b52dc07b3e6a8e598/nanoagent/docs/contracts/rush-benchmark-api.md#L491).

## Implemented baseline and current study

The five authentic Session pilots preceded implementation. The original full-output CLI, public adaptations and private host validators were then built and tested. A full-mode terminal smoke preceded compact formatting. The installed v0.2.0 CLI now selects full or lossless compact JSON with one flag; it preserves the prompt, tools and typed data and saves raw/model-visible evidence. A scored native smoke passed after the platform compatibility fix. All five immutable benchmark publications and the exact evaluated wheel are in the final freeze. See [REPRODUCE.md](REPRODUCE.md) for installation and offline analysis, and [progress.json](../study/controlled/final/progress.json) for execution state. No preview or retrieval feature is part of this experiment.

## Installed source fingerprints

All paths below are under the installed engine's `nanoagent/site/nanoagent/`, except the final configuration under `nanoagent/`. Every file matched the pinned reference byte for byte during the original audit. The later `outcome.py` patch changes its hash from the value below to `7c342f5fac0f6641725c66acec9fd24e73694db0604596edeb9dec7f3bfa2b69`; the application record preserves both hashes.

| Path | SHA-256 |
| --- | --- |
| `cli/harness.py` | `bc85262e75b6e296c3cc83e8adc2060e2dbd1fc70dc372e1f8e1a85815938b42` |
| `uploaded/runner.py` | `dddb52c6d24748cb0410c4a18ff0e4a8ad3f53a90a110fb6ec4d31e5af909464` |
| `uploaded/policy.py` | `48968c715c91d750362de9b33185389e83abfd7dc64cf52ce1002b5a7a583dc2` |
| `uploaded/projection_model.py` | `9d8fbc62ae5cf669a9c29f7aefceefed25ab0e863f45ce195c9099bd3ae06849` |
| `uploaded/reference_harnesses/shell/shell.py` | `060a1e026967660f665ced1ee8f1656c07ee0937255bec0268892c288ad13eb1` |
| `uploaded/reference_harnesses/shell/rush.py` | `0bb8fc533ad92037af4fc9d5d2479d05711e81945fdbab801ee6dc4e28c8b0b8` |
| `uploaded/outcome.py` | `1aa2d30a6e1099a3954211c9aeb2a2f39c3634a27ab1b1d1e24378833ad70d91` |
| `uploaded/case_sets.py` | `cbc1a1c4b2e6e2b1aa0c89ad932358284fb5fe9100e5352a0df0ea727651fb7b` |
| `deploy/worker/worker.openrouter.yaml` | `cf45cbbbf8be2c9a0ea4900dde59a6a94d5354dccb3c4f63b3f4371bdfb72283` |
