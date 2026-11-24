# Controlled experiment results

Captured 50/50 logical trials; 50 actual attempts. Freeze `7301cf30de5307b76458758b5d8c6df778737684024440ca5f163c419374214a`.

Native pass counts include every planned logical trial. Metric entries are mean ± sample SD (n) for successful, independently audited trials; unknown measurements are excluded explicitly by n. Every attempt and failed or unscored trial remains in the CSV/JSON evidence.

| Task / condition | Native pass / planned | Captured | Actual attempts | Input tokens (n) | Cached subset (n) | Output tokens (n) | Native seconds (n) | Agent seconds (n) | Settled USD (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cipher-crack/telegram / full | 4/5 | 5 | 5 | 4418.50 ± 16.82 (4) | 2816.00 ± 512.00 (4) | 305.00 ± 28.01 (4) | 11.44 ± 1.93 (4) | 7.47 ± 2.34 (4) | 0.000290 ± 0.000030 (4) |
| cipher-crack/telegram / compact | 5/5 | 5 | 5 | 4387.60 ± 22.19 (5) | 2867.20 ± 457.95 (5) | 324.60 ± 23.54 (5) | 12.56 ± 3.45 (5) | 8.88 ± 3.89 (5) | 0.000301 ± 0.000060 (5) |
| log-triage/edge-proxy / full | 5/5 | 5 | 5 | 2970.00 ± 161.00 (5) | 2457.60 ± 228.97 (5) | 195.80 ± 27.01 (5) | 8.31 ± 0.79 (5) | 5.04 ± 0.96 (5) | 0.000154 ± 0.000012 (5) |
| log-triage/edge-proxy / compact | 5/5 | 5 | 5 | 3073.40 ± 188.52 (5) | 2355.20 ± 280.43 (5) | 213.00 ± 22.27 (5) | 8.60 ± 0.85 (5) | 5.24 ± 0.83 (5) | 0.000175 ± 0.000021 (5) |
| path-probe/quarry / full | 5/5 | 5 | 5 | 2619.00 ± 8.94 (5) | 1996.80 ± 420.65 (5) | 231.00 ± 11.47 (5) | 8.60 ± 1.49 (5) | 5.54 ± 1.40 (5) | 0.000175 ± 0.000056 (5) |
| path-probe/quarry / compact | 5/5 | 5 | 5 | 2511.00 ± 10.95 (5) | 1382.40 ± 530.85 (5) | 236.60 ± 15.71 (5) | 9.52 ± 2.11 (5) | 6.32 ± 1.92 (5) | 0.000221 ± 0.000056 (5) |
| regex-infer/widget-code / full | 4/5 | 5 | 5 | 3074.50 ± 873.00 (4) | 2240.00 ± 1052.92 (4) | 545.25 ± 178.00 (4) | 12.42 ± 3.46 (4) | 9.35 ± 3.26 (4) | 0.000273 ± 0.000085 (4) |
| regex-infer/widget-code / compact | 5/5 | 5 | 5 | 2825.20 ± 713.75 (5) | 2457.60 ± 642.55 (5) | 537.20 ± 209.58 (5) | 13.54 ± 1.98 (5) | 10.33 ± 1.76 (5) | 0.000233 ± 0.000062 (5) |
| stat-pick/sensor-drift / full | 5/5 | 5 | 5 | 4519.80 ± 360.96 (5) | 2969.60 ± 642.55 (5) | 645.60 ± 65.14 (5) | 13.39 ± 2.29 (5) | 10.03 ± 2.27 (5) | 0.000408 ± 0.000071 (5) |
| stat-pick/sensor-drift / compact | 5/5 | 5 | 5 | 4207.00 ± 332.91 (5) | 3020.80 ± 662.64 (5) | 625.00 ± 92.86 (5) | 17.37 ± 4.68 (5) | 14.08 ± 4.74 (5) | 0.000356 ± 0.000072 (5) |

Paired ratios are Compact/Full; deltas are Compact minus Full. Only pairs in which both conditions pass and satisfy the audit contribute. SD is sample SD; with n ≤ 5 these are descriptive results, not a significance test.

| Task | Eligible pairs | Input ratio mean ± SD [range] | Native-time ratio mean ± SD [range] | Agent-time ratio mean ± SD [range] |
|---|---:|---|---|---|
| cipher-crack/telegram | 4/5 | 0.99 ± 0.01 [0.98, 1.00], n=4 | 1.12 ± 0.15 [0.97, 1.30], n=4 | 1.20 ± 0.18 [1.04, 1.43], n=4 |
| log-triage/edge-proxy | 5/5 | 1.04 ± 0.10 [0.88, 1.11], n=5 | 1.05 ± 0.17 [0.86, 1.28], n=5 | 1.07 ± 0.26 [0.79, 1.43], n=5 |
| path-probe/quarry | 5/5 | 0.96 ± 0.00 [0.96, 0.96], n=5 | 1.12 ± 0.24 [0.83, 1.38], n=5 | 1.17 ± 0.36 [0.74, 1.55], n=5 |
| regex-infer/widget-code | 4/5 | 0.86 ± 0.19 [0.57, 0.95], n=4 | 1.13 ± 0.26 [0.87, 1.48], n=4 | 1.16 ± 0.31 [0.83, 1.57], n=4 |
| stat-pick/sensor-drift | 5/5 | 0.94 ± 0.12 [0.83, 1.12], n=5 | 1.35 ± 0.53 [0.75, 2.15], n=5 | 1.50 ± 0.70 [0.66, 2.55], n=5 |

Unsuccessful captured trials remain part of the experiment. Known usage subtotals below are partial evidence, not complete totals or savings. The full trial time includes the failure; all-trial latency statistics are also retained in analysis.json.

| Trial | Native / agent outcome | Native seconds | Agent seconds | Known input / cached / output | Settled cost known subtotal (USD) |
|---|---|---:|---:|---|---:|
| regex-infer/widget-code/full/rep03 | fail / request_timeout | 107.391 | 104.370 | 2638 (total unknown) / 2304 (total unknown) / 3827 (total unknown) | 0.001115 (total unknown) |
| cipher-crack/telegram/full/rep02 | fail / completed | 10.417 | 6.781 | 4433 / 3328 / 293 | 0.000253 |

- Native latest-attempt verdict is primary; independent local validation is an audit.
- Token, cost and duration totals include all attempts, not only the latest attempt.
- Cached tokens are a subset of input tokens, not an additional token total.
- Costs are admission settlement totals only; provider generation/accounting copies are not added.
- Provider routing statuses may show retries despite zero agent-level retries.
- Paired savings exclude failed or unaudited pairs and incomplete metrics; failures remain in trial tables.
- Five paired repetitions per task support descriptive SD/range only; no broad generalization or significance claim.
