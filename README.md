# Less Formatting, Same Information

COMP580 final project by Yifei Wang (solo, NetID **yw251**): test whether
lossless compact JSON tool results reduce agent input tokens while preserving
correctness on five course tasks.

The original `comp580-agent` CLI provides full and compact modes. Both use the
same model, prompts, tools, limits and public input bytes. Compact mode changes
only JSON presentation whitespace; it does not remove fields or shorten strings.

**Completed:** all 50 frozen trials were captured. Full passed **23/25** and
compact **25/25**, with native and independent validators agreeing on every
trial. Path input tokens fell about **4.1%** across five successful pairs;
other tasks had mixed or trajectory-dependent savings. Successful paired runs
showed no consistent latency benefit. Both full-mode failures are retained.
Five cases and one available model limit generalization.

- [Final report PDF](output/pdf/comp580-yw251-report.pdf)
- [Report source](report/report.md)
- [Main comparison figure](report/figures/main-comparison.png)
- [Final results and failures](study/controlled/final/analysis/results_summary.md)
- [Reproduction instructions](docs/REPRODUCE.md)
- [Public task adaptations and private validation](docs/ADAPTERS.md)
- [Frozen experiment identity and schedule](study/controlled/final/freeze.json)
- [Trial progress](study/controlled/final/progress.json)
- [Native benchmark API workflow](docs/BENCHMARK_WORKFLOW.md)
- [Initial app pilots and token-accounting audit](study/task0/summaries/pilot-results.md)
- [Task 0 measurement scope](docs/TRACE_ACCOUNTING.md)

## Offline reproduction

Use Python 3.12 or newer:

```sh
make build-env
make analysis-env
make test PYTHON=.venv/bin/python
make analyze
make report
```

`make analyze` regenerates tables and the main plot from captured attempts;
`make report` renders the report source as a PDF. Neither makes model calls.
The CLI itself has no runtime dependencies. `make wheel` builds an installable
wheel. See the reproduction guide for installation inside RUSH Lab and the
separate live benchmark workflow.

## Experimental scope

The matched comparison has five cases, two formatting conditions, and five
repetitions per condition. It uses `deepseek/deepseek-v4-flash-0731`, the only
model available in this deployment. The initial app exploration therefore does
not establish a multi-model result. Path Probe exposes the full graph and Stat
Pick exposes raw readings in both controlled conditions; native Session pilots
are descriptive exploration, not the causal formatting baseline.

Every final command checks the installed source fingerprint. Private answers,
validators and saved traces remain outside evaluated workspaces. Native scoring
and an independent deterministic host validator are recorded separately. Failed
attempts and missing measurements remain in the evidence.

The project also records a small local platform compatibility patch needed to
prepare enum-only answer schemas. It changes no plugin verifier and is shared
by both conditions. The original agent contains no NanoAgent implementation.
Reference checkouts, copied platform source and historical personal chat handoff
files are excluded from the submission. Public task fixtures retain their
upstream MIT notice.

The assignment requests only the report PDF on Canvas. A separate source ZIP
with code, Makefile, instructions and the plot generator is the specified
fallback because the current GitHub CLI/browser session cannot create a PR.
SSH can publish the code repository; a push is not represented as a PR.
[Download this repository as ZIP](https://github.com/a-little-hoof/580-final/archive/refs/heads/main.zip).
The local packaged ZIP also includes a per-file SHA-256 manifest. Creating these
artifacts does not submit the report to Canvas.
