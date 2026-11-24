# Less Formatting, Same Information

Updated November 23, 2026. Final report due December 15, 11:59 p.m. CT.
Local project: `/Users/wangyifei/Downloads/comp580_assignment/rush_lab_project`.

## Decision and evidence

The user approved **lossless compact formatting** after reviewing five fresh
NanoAgent pilots. All five task verifiers passed on
`deepseek/deepseek-v4-flash-0731`. See `study/task0/summaries/pilot-results.md`
for inclusive cached/input/output tokens and latency, and the preserved exports,
graphs and UI evidence for provenance. Two earlier expired-key failures are
retained separately; missing measurements are unknown. Authentication now works.
Only this one model is available through the audited deployment. That limitation
does not satisfy the assignment's request to explore different available models;
report it explicitly rather than invent a second model.

The original remote plan, “Read Less, Retrieve When Needed,” proposed bounded
previews and retrieval. Observed tool payloads are mostly below 1 KB, making that
mechanism unlikely to activate naturally. We will not pad inputs or force verbose
calls. The chosen initial treatment instead removes JSON presentation whitespace
while retaining every key, value, array order and whitespace inside strings.
No summarizer, omission, table encoding, retrieval feature or history rewriting
is included in this first comparison.

## Research question

Does deterministic compact JSON serialization of tool results reduce cumulative
model input tokens without reducing task success, compared with the same original
agent returning conventionally indented JSON? Latency and output tokens may not
improve: reasoning variance, cache use and changes in tool choices can dominate.
Byte savings are not a substitute for measured token or latency savings.

## Baseline and treatment

The original standard-library Python CLI, `comp580-agent` v0.2.0, is installed in
the RUSH Lab Harness terminal and invoked through `rush comp580-agent ...`.
The full-output baseline uses `json.dumps(..., ensure_ascii=False, indent=2)`;
the compact condition uses separators `(',', ':')`, with the same strict JSON
values and key order. Both reject nonfinite numbers. JSON decoding must reconstruct
the exact same typed data. Plain text held inside JSON strings is preserved.

Both conditions share the model loop, system prompt, exact user prompt, tools,
public inputs, model/version, parameters and limits. Tools are `read_json`,
`read_file`, literal unpaginated `search_file`, `run_python`, and `write_answer`.
The agent may read selectively or compute concise answers. No task-specific solver
is exposed. Model requests go only through the gateway supplied by RUSH.
The first real full-output smoke run preceded compact implementation. A later
native scored smoke passed before the final experiment was frozen.

This is an original baseline, not copied NanoAgent code. The five NanoAgent
Session pilots are a separate exploration, not a causal baseline for our format
switch. Custom CLIs do not receive plugin broker tools; adapted public fixtures
are necessary. The complete graph and raw statistical readings change information
access compared with Session. Describe this explicitly; do not attribute those
differences to formatting.

## Tasks, public data and validation

Use the five observed cases: Log Triage/edge-proxy, Cipher Crack/telegram,
Path Probe/quarry, Regex From Examples/widget-code, and Stat Pick/sensor-drift.
The regex plugin is `regex-infer`, task `infer-pattern`.

`study/controlled/fixtures/` contains only allowlisted public data and task prompts.
A manifest records source commits, extraction recipes and file hashes. Expected
answers, held-out regex examples, reference computations and validator code remain
under `study/controlled/validators/`, outside every evaluated agent workspace and
install package. Saved app graphs also contain private truth and must never enter
agent workspaces. Development prompts are recorded separately.

Deterministic private host checks validate exact schema and case, input integrity,
log label/evidence, Caesar decryption consistency, shortest-path feasibility and
optimality, finite held-out regex agreement, and statistic semantics/tolerance.
Malformed JSON, duplicate keys, nonfinite numbers and modified inputs are rejected.
Tests include adversarial invalid answers. RUSH's original plugin verifier remains
the authoritative in-app verdict; host integrity findings are reported separately.

## Execution stages

1. Completed: inspect app, source contracts and five fresh NanoAgent pilots.
2. Completed: public adapters, private validators, original full-output CLI and
   a live Harness smoke test; installation and scored benchmark capture verified.
3. Completed: reversible compact serialization and offline invariant tests.
4. Completed: freeze package/config/input hashes, prompts, budgets, model and
   randomized order at `2026-11-24T04:39:38Z`. Development runs are excluded.
5. Completed: five cases × two conditions × five repetitions = 50 logical
   trials and 50 actual attempts on the one available model. All were captured;
   full passed 23/25 and compact passed 25/25. Both failures remain in the evidence.
6. Completed analysis: per-task tables and main plot are generated from all
   captures. The primary agent is finalizing report sections 0–9, PDF verification
   and the selected source-ZIP submission fallback.

The authoritative identity and schedule are `study/controlled/final/freeze.json`;
completion state is `study/controlled/final/progress.json`, and final derived
results are `study/controlled/final/analysis/analysis.json`. Preserve frozen
source, fixtures, validators, plans and configuration with the completed evidence.
The common settings include temperature 0, at most 12 model calls, 180 seconds
per attempt, 60 seconds per model request, 10 seconds per tool, 32,768 output
tokens per call, a 64-KiB full-form tool-result limit and a separate 2-MiB gateway
response limit. Both modes reject an oversized full tool result before formatting.
The native publications pin `internet_access: false` and a $0.05 admission ceiling
per attempt; that is neither measured cost nor a total-study charge ceiling.

A local platform compatibility patch allows enum-only scalar output-schema
properties to produce unfilled answer templates. It changes no task verifier or
reference, is shared by both conditions, and is frozen with the experiment. Its
provenance and application record are under
`study/controlled/development/platform-fix/`.

## Experiment and measurements

The frozen schedule uses seed 580 and `sha256-sort-pairs-v1`, ordering 25 case/repeat
pairs and choosing condition order within each pair. Do not stop early because
results appear favorable. All 50 scheduled trials were retained. Equal workspace
resets do not clear provider prefix caches, so cached input and run order are
retained separately. Repetitions characterize these five cases, not generalization
to all agent tasks.

Primary metrics: verifier success, cumulative input tokens, and end-to-end wall
time. Also retain cached input, output tokens, model/tool counts, raw and visible
tool bytes, failures, timing coverage and available cost. Cached input is a subset
of input, never added twice. Missing usage remains unknown. Report all attempted
runs plus successful-run figures where helpful; fast failures are not savings.

NanoAgent native exports count outer tokens while graphs retain nested inference.
Current pilots verified the graph-inclusive totals against the UI. Keep both
sources; do not compare outer-only counts with complete custom-agent work.
Harness gateway/attempt accounting has a distinct schema and coverage fields.

The full Regex repetition 3 failed on its third model request's 60-second timeout;
its incomplete token/cost totals remain unknown. Full Cipher repetition 2
completed but failed key/plaintext consistency, even though its plaintext partial
score was 1. The final native and independent host verdicts agree. Paired
efficiency comparisons use the 23 pairs in which both conditions passed and were
audited; success and all-trial elapsed summaries retain all 50 trials. Compact
input-token changes vary by task, and the experiment does not establish a latency
improvement. See `study/controlled/final/analysis/results_summary.md`.

## Deliverables and remaining inputs

Installable original CLI, deterministic validators, public fixtures and provenance,
reproducible run/analysis scripts, actual traces, main plot, Makefile and a report
PDF following the supplied sections 0–9. Only the report PDF goes to Canvas.
The assignment's source/Makefile/instructions/plot ZIP fallback is selected because
the available CLI/browser session cannot create the requested authenticated PR.
The local fallback location is `output/comp580-yw251-source.zip`; the report PDF
location is `output/pdf/comp580-yw251-report.pdf`. Repository publication is a
separate action and is not implied by choosing the fallback. No Canvas submission
is performed by producing either artifact.

Confirmed author: Yifei Wang, solo submission, NetID `yw251`. Submission repository:
https://github.com/a-little-hoof/580-final (empty when inspected on November 23). Do not submit to Canvas or send messages to course staff on behalf
of the user without a specific instruction.

The original remote plan is under `/scratch/yw251/comp580` on host `range`.
The surrounding Assignment 1 files remain intact. Technical contracts and their
source/version limits are in `docs/HARNESS_CONTRACT.md`; live progress is in
`docs/LOCAL_PROGRESS.md`. The supplied `assignment.txt` governs submission.
