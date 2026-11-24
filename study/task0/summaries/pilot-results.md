# Initial pilot results

One observed pilot per captured task. Token columns include outer and nested graph model-call records; latency comes from the native export. Cached input is already part of input tokens.

| Task | Case | Model | Input tokens | Cached input | Output tokens | Verifier | Latency, s |
|---|---|---|---:|---:|---:|---|---:|
| crack-cipher | telegram | deepseek/deepseek-v4-flash-0731 | 11,581 | 6,912 | 1,952 | pass | 27.4156 |
| triage-log | edge-proxy | deepseek/deepseek-v4-flash-0731 | 3,699 | 1,024 | 794 | pass | 19.9971 |
| find-route | quarry | deepseek/deepseek-v4-flash-0731 | 10,178 | 5,632 | 1,069 | pass | 22.3384 |
| infer-pattern | widget-code | deepseek/deepseek-v4-flash-0731 | 6,643 | 2,560 | 769 | pass | 16.1301 |
| answer-question | sensor-drift | deepseek/deepseek-v4-flash-0731 | 4,793 | 2,048 | 1,280 | pass | 29.1667 |

Verifier success uses the recorded valid boolean, not score or assistant prose. These preliminary single-run observations do not estimate a success rate or establish a cross-model comparison.

See graph-accounting.json for source hashes, per-call coverage, failed/unknown records, and comparisons with native outer-only counters and captured UI totals. Missing measurements must remain unknown.
