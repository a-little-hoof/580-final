# Installed-source contract audit: Path Probe, Regex From Examples, Stat Pick

Source inspection on 2026-11-23 (America/Chicago). The primary agent supplied
these exact Source on GitHub URLs from the current Rush Lab UI. The corresponding
repositories were cloned to ignored `references/` directories and checked out at
the commits below. This audits those advertised sources; it is not an independent
hash measurement of the app's installed package bytes. All three manifests say
version `0.1.0`, spec `nanoagent.plugin/v0001`, runtime
`uv run --frozen python -m plugin`, and no permitted network hosts.

| Plugin ID | Source commit | Local reference |
| --- | --- | --- |
| `path-probe` | [`96b2b4192a9ae6933db834a796553ad868beaaf6`](https://github.com/a-little-hoof/path-probe/tree/96b2b4192a9ae6933db834a796553ad868beaaf6) | `references/path-probe` |
| `regex-infer` | [`3fc05876e6e3fc37d3544fe87a15fc3d1f2123da`](https://github.com/a-little-hoof/regex-infer/tree/3fc05876e6e3fc37d3544fe87a15fc3d1f2123da) | `references/regex-infer` |
| `stat-pick` | [`5fcfedf4507d779e918a87d8aa299ca51f1ae45c`](https://github.com/a-little-hoof/stat-pick/tree/5fcfedf4507d779e918a87d8aa299ca51f1ae45c) | `references/stat-pick` |

No model calls or app actions were made by this source audit. Tests were read,
not executed. This document contains no submitted answers, hidden regex rules,
or holdout strings. It is researcher-side evidence, not a task fixture or model
prompt. The reference checkouts include answers and must remain outside the
evaluated agent's filesystem access.

## Path Probe

- Task: `find-route`, runner `agent`. Input: `{"case":"quarry"}`. All cases:
  `orchard`, `quarry`, `foundry`, `harbour`.
- Output contract: `{"case":<Case>,"route":<list[str]>,"cost":<int>}`.
- Visible tools: `read_map({case})` supplies start, goal and node count;
  `neighbours({case,nodes})` supplies links touching requested nodes. The hidden
  reference is `best_route({case})`, which supplies the complete map and an
  optimal route to the verifier.
- The installed `quarry` case matches the pinned NanoAgent example's start,
  goal, six node names and all seven weighted undirected links. **The prepared
  example prompt is not an equivalent exploration prompt:** it reveals the
  entire map, whereas the installed task deliberately requires partial-map
  discovery. Invoke the installed task using its case argument.
- `verifier/route.py` validates reference consistency and independently searches
  its link list for the minimum cost. A submission must name the requested
  case, start/end correctly, use existing links, visit each node at most once,
  contain at most 100 nodes, and report its summed link cost. Any optimal route
  passes; a feasible but dearer route has `valid=false` and
  `score=optimal_cost/submitted_cost`. Other invalid routes score zero.
- Scope: optimality is checked against **reference-provided** links; the
  verifier does not independently authenticate those links against plugin
  `MAPS`. Tool checks establish structural plausibility and that returned links
  touch requested nodes, not completeness of the returned adjacency list.

Sources: `nanoagent.yaml`, `contract.py`, `src/plugin/maps.py`,
`src/plugin/routes.py`, `verifier/{checks,route,puzzle,looking}.py`.

## Regex From Examples

- The display name is unchanged, but the installed ID is **`regex-infer`**, its
  task is **`infer-pattern`**, and its runner is `agent`. Input uses `case`,
  whose choices are `widget-code`, `shelf-tag`, `batch-ref`, `seat-label`.
  Output: `{"case":<Case>,"pattern":<str>}`.
- The archived `regex-from-examples` / `write-regex` / `{"format":"octet"}`
  example does **not** map to this source. Its octet rules, 80-character cap,
  restricted dialect and ASCII semantics are not this task's contract.
- Proposed replacement for observed exploration: `regex-infer` /
  `infer-pattern` / `{"case":"widget-code"}`. It has 13 visible examples and
  10 held-out examples. This is a replacement case, not a renamed octet run.
- Visible tools: `sample_examples({case})` and
  `try_pattern({case,pattern})`. Both use the visible set. Hidden reference:
  `holdout_examples({case})`.
- `verifier/patterns.py` requires a matching case and a pattern accepted by
  `pattern_problem`: nonblank, no surrounding whitespace, at most 120
  characters, compilable by Python `re`, and no nested-quantifier shape
  detected by the verifier's heuristic. It validates reference labels against
  a separate copy of the case rule, then applies Python `re.fullmatch` to the
  held-out set. Score is the fraction correctly labelled; only a clean sweep
  gives `valid=true`.
- Scope: a pass means agreement on the finite held-out set, **not** proven
  equivalence to the intended language. The heuristic is not a comprehensive
  regex complexity bound. The source does not impose the archived octet
  example's broad bans on anchors, flags or lookarounds.

Sources: `nanoagent.yaml`, `contract.py`, `src/plugin/{cases,examples,patterns}.py`,
`verifier/{checks,examples,patterns}.py`.

## Stat Pick

- Task: `answer-question`, runner **`decide`**. Input:
  `{"case":"sensor-drift"}`. Cases: `delivery-delays`, `class-sizes`,
  `sensor-drift`, `rainfall`.
- Output: `{"case":<Case>,"statistic":<Statistic>,"value":<float>}`.
  `Statistic` is one of `mean`, `median`, `mode`, `range`, `spread`, `smallest`,
  `largest`, `total`.
- Visible tools: `read_question({case})` returns the question, column and
  reading count; `summarise({case,column,statistic})` returns the requested
  summary. Hidden reference: `solution({case})`. The source describes the
  `decide` runner as making the model choose tool arguments while NanoAgent
  constructs returned values; actual runtime behavior still needs trace
  confirmation.
- `sensor-drift` matches the pinned example's question, column and all eleven
  readings. The prepared example exposes readings, whereas the installed
  task keeps them behind its tools. Use the case-only task invocation.
- `verifier/answer.py` checks both case IDs and the reference's arithmetic,
  then requires the chosen statistic to match the reference and independently
  recomputes its value from the reference readings. Acceptance tolerance is
  `abs(submitted - expected) <= 1e-6 * max(1.0, abs(expected))`.
  Wrong choice scores zero; correct choice with a wrong value scores `0.5`
  with `valid=false`; both correct score one with `valid=true`.
- Scope: arithmetic is independently recomputed, but the semantic choice and
  underlying readings are trusted from the reference rather than independently
  established from the question or plugin table. The `summarise` tool verifier
  checks metadata consistency and a positive count, not the numeric value;
  numeric verification occurs at task level.

Sources: `nanoagent.yaml`, `contract.py`, `src/plugin/{tables,summaries}.py`,
`verifier/{checks,answer,question,summary}.py`.

## SHA-256 of inspected contract files

```text
4f2229340d5809ed348827df0373e103ff42b2eaa5ae0927bc1c9d773d2633ce  references/path-probe/nanoagent.yaml
0508dd622e61dc273e03b8afda407808fbcbb2218f33ac40857c0c3024785bc4  references/path-probe/contract.py
9f2437a85356e5fc3716722966bdab0c9c4a970641ea0db217a72868c31936e6  references/regex-infer/nanoagent.yaml
d64656c3c1507b16bd658ea0f0247bd52c282500ea9b7472bcc021fca254030e  references/regex-infer/contract.py
b5daad5efe0519e17b64572191fdce88603b02cbba96f9fdad0d8fdd916bf3a4  references/stat-pick/nanoagent.yaml
433c0739e8d02e806704f1fa4502b16b6864a67bac1542d1a4c6a54c4fc0a2d1  references/stat-pick/contract.py
```

The original `study/baseline/` proposed package is unchanged. Future observed
manifests should cite these sources and the corrected IDs, and retain actual
dispatched prompts and run evidence separately from these source findings.
