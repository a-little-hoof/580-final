# Validator development record

Research-side record, 2026-11-23. Never mount this directory in an evaluated agent workspace. No provider/model evaluation call was made to develop or test these checkers. The assistant read the pinned contracts/verifiers, wrote independent selected-case checks, and exercised them with synthetic answers.

The implementation request received from the parent agent was:

> User approved lossless compact formatting. Implement public fixtures + private deterministic validators and meaningful tests, exclusively under study/controlled/{fixtures,validators,tests} and docs/ADAPTERS.md. Read draft and contracts. Use AST literal extraction explicit allowlist; no plugin execution or model calls. Each case directory input.json plus prompt.txt with public task definitions/schema/case exact data. Same tasks/cases as pilots; clearly fullgraph/rawstats adaptation. Keep private validator reference data outside publicfixtures/package. Validate typed answer and integrity, reproduce upstream acceptance nuances. Need manifest input hashes/source versions/extraction provenance/license. Do not edit projectroot plan/README. Communicate interface/files for baselineagent. Do not include known answer/hiddenlabels in prompts or fixture files.

The parent then confirmed:

> Interface approved. Coordinate manifest shape with inspect_path_stat_regex agent implementing dryrun benchmarkhelper. Fixtureprompt identical conditions; original Session caseprompt difference declared. Need do not force full outputs or use read_json specifically; natural prompt says input file. Ensure license source notices and private truthisolated.

The parent review added this concrete edge case:

> Early validatorreview looks good. Please test huge integer stat.value (e.g10**1000) causing OverflowError subtractfloat; should deterministicreject false notuncaughtcrash. Sourceinterface metadata/hashesgood. Root wrote study/controlled/prepare_workspace.py twofileallowlist newdironly, noconflict. Final testsinclude missing/modifiedpromptinput, extra fields andtypeboolcost, syntacticinvalidduplicate/NaN/overflowJSON.

Source review established the acceptance nuances tested: alternate log citations; exact fault enums; cipher outer-whitespace/case normalization with internal spacing preserved; a wrong key retaining partial score 1; both optimal graph routes; statistics population rather than sample deviation and relative tolerance; regex finite held-out agreement, length/whitespace/syntax and lexical quantifier restrictions. The current copied reference values are isolated in references.json. Source identities and file hashes are in the public fixture manifest; no upstream plugin or NanoAgent implementation was imported or executed.

Independent cross-checks use hand-worked graph routes with a separate exhaustive-search validator, statistics.pstdev in test expectations versus explicit arithmetic in the validator, alternative regex forms and visible-example memorization counterexamples, every cipher key with the correct plaintext, and input-integrity mutations independent of semantic correctness. Exact error prose need not match upstream; boolean acceptance and partial-score behavior do for the selected fixed cases. Operational JSON/size/isolation failures are separately labelled local checks.

The benchmark-helper review identified that the pinned publication validator requires `prompt == prompt.strip()`. The generator was corrected to omit a final prompt newline, regenerated all public prompt hashes, and added a publication-whitespace assertion. Both conditions still use exactly the same prompt bytes.

Validation command: `python3 -m unittest discover -s study/controlled/tests -p 'test_validators.py' -v` — 23 tests passed after that correction. Tests and fixture regeneration do not count as experimental runs.
