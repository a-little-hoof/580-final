# Final study status and limitations

Yifei Wang — **yw251** — solo submission. The frozen study has completed **50 logical trials and 50 actual attempts**. Final [analysis.json](../study/controlled/final/analysis/analysis.json) and [results_summary.md](../study/controlled/final/analysis/results_summary.md) retain every trial: full passed **23/25**, compact passed **25/25**, with matching native and independent host outcomes. The [freeze](../study/controlled/final/freeze.json) records seed 580, exact package/source/fixture/validator identities, common settings and all development exclusions. No frozen file was changed by the documentation review.

## Results and retained failures

- Full Regex repetition 3 timed out on its third model request at the shared 60-second request limit. Its total input, cached input, output and cost remain unknown; known subtotals and observed elapsed time remain in the evidence.
- Full Cipher repetition 2 completed but failed key/plaintext consistency. Its correct plaintext received partial score 1, which does not override `valid=false` or the native failure.
- Success counts and all-trial elapsed summaries include both failures. Paired efficiency summaries use 23 pairs with two successful audited outcomes: four Cipher, five Log, five Path, four Regex and five Stat pairs. Sample sizes and exclusions are explicit.
- Token changes vary across cases, and the study does not establish a latency improvement. Five repetitions per fixed case support descriptive variability, not a broad reliability or significance claim. Provider caches, model/tool-choice variability and routing delays remain relevant.

## Scope and assignment limitations

Only `deepseek/deepseek-v4-flash-0731` was exposed by the audited deployment. The five Task 0 pilots and final comparisons therefore do not fulfill a multi-model exploration; no second model or course exception is claimed. Two earlier Task 0 authentication failures retain unknown measurements. Task 0 uses graph-inclusive nested inference, while final trials use their own native gateway/accounting evidence; historical corrected sessions and development smokes are excluded.

Both controlled modes share the same original CLI, model, exact prompts, inputs, limits and typed JSON data. Path exposes a complete graph and Stat exposes raw readings in both modes; these adaptations differ from native Session access. Regex correctness is finite held-out agreement, and Log correctness is fixed reference label/evidence agreement. Private references, validators and saved graphs were kept outside evaluated workspaces. The shared local enum-only answer-template compatibility patch is documented and frozen; it changes no plugin verifier.

## Delivery and reproduction

- [Report source](../report/report.md), with assignment sections 0–9 and the author/NetID.
- Report PDF delivery path: [comp580-yw251-report.pdf](../output/pdf/comp580-yw251-report.pdf).
- Chosen assignment fallback: the local `output/comp580-yw251-source.zip`, with code, Makefile, run instructions, main-plot script and a per-file hash manifest. The ZIP itself is ignored by Git; [GitHub also provides a source ZIP](https://github.com/a-little-hoof/580-final/archive/refs/heads/main.zip).
- [Reproduction instructions](REPRODUCE.md), [benchmark workflow](BENCHMARK_WORKFLOW.md), [main plot](../report/figures/main-comparison.pdf), [validator development prompts](../study/controlled/validators/DEVELOPMENT.md) and [machine-readable prompt record](../study/controlled/development/prompts.jsonl).
- Repository: <https://github.com/a-little-hoof/580-final>. Code publication uses the existing SSH access. The current CLI/browser session cannot create the assignment's requested PR, so the permitted source-ZIP fallback is provided; no PR is claimed.
- [Clean-extraction verification](../report/reproduction-qa.json): core tests, all final analysis values, main plot, PDF text and a wheel rebuild followed by analysis reproduced successfully without the original build folder or upstream reference checkouts.

The six-page PDF was rendered and visually checked on every page after the prose revision. The numerical tables and recorded development prompts are unchanged. Only the report PDF belongs on Canvas; no Canvas submission is performed by generating these files or pushing code. The study itself is complete; the limitations above remain part of the final report rather than unfinished experiments to hide or replace.
