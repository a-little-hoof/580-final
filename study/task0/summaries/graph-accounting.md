# Pilot graph accounting

Observed model-call records, counted once per graph node and record index. These are pilot descriptions, not success-rate estimates or provider billing totals.

| Plugin / turn | Calls outer / nested | Outer input / output | Nested input / output | All input / output | Cached input, all | UI input/output match |
|---|---:|---:|---:|---:|---:|---|
| regex-infer / 1 | 2 / 4 | 1,157 / 119 | 5,486 / 650 | 6,643 / 769 | 2,560 | True / True |
| stat-pick / 1 | 2 / 6 | 1,237 / 132 | 3,556 / 1,148 | 4,793 / 1,280 | 2,048 | True / True |
| log-triage / 1 | 2 / 4 | 1,086 / 119 | 2,613 / 675 | 3,699 / 794 | 1,024 | True / True |
| path-probe / 1 | 2 / 6 | 1,245 / 147 | 8,933 / 922 | 10,178 / 1,069 | 5,632 | True / True |
| cipher-crack / 1 | 2 / 5 | 1,224 / 103 | 10,357 / 1,849 | 11,581 / 1,952 | 6,912 | True / True |

| Plugin / turn | Graph cost, USD | Graph model seconds | Export latency, s | Export model, s | Export tool, s |
|---|---:|---:|---:|---:|---:|
| regex-infer / 1 | 0.00040905 | 8.9021 | 16.1301 | 8.9021 | 7.22691 |
| stat-pick / 1 | 0.00036765 | 21.5744 | 29.1667 | 21.5744 | 7.59145 |
| log-triage / 1 | 0.00026435 | 13.9588 | 19.9971 | 13.9588 | 6.03749 |
| path-probe / 1 | 0.0006158 | 12.9678 | 22.3384 | 12.9678 | 9.36978 |
| cipher-crack / 1 | 0.00077425 | 16.5731 | 27.4156 | 16.5731 | 10.8416 |

| Plugin / turn | Raw-text data results | Missing raw-byte sizes | Known total UTF-8 bytes | Largest known result, bytes |
|---|---:|---:|---:|---:|
| regex-infer / 1 | 2 | 0 | 653 | 535 |
| stat-pick / 1 | 0 | 2 | — | — |
| log-triage / 1 | 0 | 1 | — | — |
| path-probe / 1 | 4 | 0 | 692 | 303 |
| cipher-crack / 1 | 9 | 0 | 1,254 | 147 |

Data-result sizes exclude submit acknowledgments, hidden reference outputs, and the outer task wrapper. Structured graph values have unknown original wire size; they are not reserialized to manufacture a raw byte count.

Cached input is included in input tokens; reasoning is included in output tokens. Missing fields remain unknown in JSON. Tables show known subtotals; inspect per-field missing counts and unmeasured model nodes before treating them as complete.

Graph cost is the runtime's token-price calculation. Display-rounded UI timing/cost strings are preserved without treating them as exact numbers. Exported calls[] and repeated ATIF history are never added.

Failed records, unknown statuses, unmeasured model nodes, source hashes, and export/UI comparisons are retained in the accompanying JSON. Runtime context is supplied by the operator; it is not inferred from graph contents.
