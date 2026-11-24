# Reproduce the controlled comparison

The evaluated agent is an original Python CLI. Its full and compact conditions
differ only in tool-result JSON whitespace. The five public fixtures adapt the
course tasks; `ADAPTERS.md` explains the full-graph and raw-reading changes.

## Offline checks and build

Use Python 3.12 or newer from the project root:

```sh
make build-env
make analysis-env
make test PYTHON=.venv/bin/python
make wheel
```

The fixture-regeneration provenance test is optional: it skips when the five
ignored Git checkouts under `references/` are absent. All other fixture hashes,
input isolation and validator checks run offline from the repository artifacts.
To exercise that one additional rebuild check, obtain each public plugin
repository at the exact commit recorded in `fixtures/manifest.json` under
`references/<plugin-id>`; existing checkouts with a wrong commit or dirty tree
fail rather than skip. The generator makes no network or model calls.

The agent has no runtime dependencies. Build dependencies and analysis/report
dependencies are pinned separately. A rebuilt wheel can have different ZIP
timestamps; the recorded source-module fingerprint identifies evaluated code.
The exact evaluated wheel is retained under
`study/controlled/development/artifacts/`.
The five generated files under `src/comp580_agent.egg-info/` are also retained
because they were part of the pre-run source freeze. The package builder rejects
an archive that would omit a frozen input; analysis verifies their exact bytes.

## Inspect the saved experiment without making model calls

```sh
make analyze
make report
```

Analysis reads the frozen schedule, progress, every attempt and the captured
workspace archives. It verifies saved content hashes and runs private validators
on the host. It never invokes a model. The figure is regenerated from measured
trials, not from hand-entered values. The PDF renderer reads `report/report.md`.
The historical freeze retains the original machine's absolute paths; the
analyzer resolves those paths relative to the checked-out project for portability.
For wheel verification, analysis first uses the exact evaluated wheel retained in
`study/controlled/development/artifacts/`, verifies its frozen SHA-256 and source
module hashes, and records that chosen path in `analysis.json`. A newly rebuilt
`dist/` wheel is not substituted for this evidence. Only when the retained wheel
is absent does analysis try the rebased original wheel path, with the same exact
hash requirements. No frozen record is rewritten.

## Install in RUSH Lab

Open a Harness terminal in RUSH Lab. Transfer only the built wheel into that
terminal, then install it with its local path:

```sh
pip install --no-index --no-deps /path/to/comp580_agent-0.2.0-py3-none-any.whl
comp580-agent --help
```

The saved development procedure transferred a base64-encoded wheel through the
official Harness terminal connection, checked its SHA-256 and installed it with
the command above. Use the app's supported file-transfer or terminal workflow.
Do not copy private validators, reference answers, source audits or old traces
into the evaluated workspace. Only a case's `input.json` and `prompt.txt` belong
there. `prepare_workspace.py` creates this exact two-file staging directory.

Invoke the program once using `rush comp580-agent ...` so the terminal records
the command, then end the terminal normally. RUSH keeps the installed package
for native benchmark runs. Use the gateway environment supplied by RUSH; do not
put a provider key in a command, source file or report. `run_python` is intended
for the isolated Harness VM, not as a sandbox for arbitrary host code.

## Publish a new experiment

The existing final run IDs are evidence, not a request to repeat paid calls.
Choose a new namespace, state directory and frozen schedule for a new study.
The supported publication/start/export API workflow is documented in
`BENCHMARK_WORKFLOW.md`. Its five prepared payloads contain only public input and
prompt bytes. Internet access is disabled for evaluated benchmark cases.

This experiment used the November 23, 2026 RUSH engine with a small local
compatibility patch for enum-only answer schemas. The patch, source hashes,
tests and rollback instructions are under
`study/controlled/development/platform-fix/`. It changes template preparation,
not scoring, and is identical across conditions. A future app may already
include a fix; check the recorded source hash rather than applying it blindly.

Use the official installed NanoAgent Python for live commands. Publish and
verify all five cases, install the package, and capture a scored smoke before
calling `run_experiments.py freeze`. The freeze checks matching model, provider,
limits and package identities and explicitly excludes development runs.

`execute_frozen.py --freeze <new-freeze> --progress <new-progress> --evidence
<new-evidence>` executes the already-frozen schedule sequentially. It preserves
idempotent requests and stops on a provenance/capture issue. Failed logical
trials remain in the results. Native worker retries are retained separately;
the per-attempt admission limit is not a total experiment spending limit.

## Submission

The assignment requests the report PDF alone on Canvas. The repository holds
code, test and analysis scripts, Makefile, reproducibility instructions and
the experimental evidence. A source ZIP is also prepared as the assignment's
fallback code package. Neither a Git push nor a report file submits to Canvas.
