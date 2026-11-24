# Local platform compatibility patch

The native benchmark publication returned `pin_failed` because the platform's answer skeleton reader rejected enum-only scalar properties such as `case`. All five public plugin contracts generate this form with the currently installed NanoAgent schema compiler. `actual-output-schemas.json` records those generated schemas, source commits and contract hashes. No plugin tools, private verifiers or models were invoked to generate them.

`scalar-enum-skeleton.patch` changes only `nanoagent/uploaded/outcome.py`: a nonempty `enum` containing only finite JSON scalar values, with no explicit `type`, gets an unfilled `null`. It does not choose an enum answer. Existing object, array, scalar, reference and union behavior remains in place; unsupported unions and object/array enum values remain rejected. Plugin schemas and validators are unchanged.

The patch was prepared against runtime `2026-11-23T03-56-59-663Z-7ac1754`, whose original file is byte-identical to upstream commit `189454718dad10404b92147b52dc07b3e6a8e598`. The original SHA-256 is `1aa2d30a6e1099a3954211c9aeb2a2f39c3634a27ab1b1d1e24378833ad70d91`; the patched SHA-256 is `7c342f5fac0f6641725c66acec9fd24e73694db0604596edeb9dec7f3bfa2b69`. Full artifact fingerprints are in `provenance.json`.

Seven targeted unittest checks pass, including all five actual generated plugin schemas before and after the patch, invalid enum values, root-object enforcement, reference behavior and unchanged union rejection. The untouched upstream `test/uploaded/test_outcome.py` was run with explicit `sys.modules['nanoagent.uploaded.outcome']` injection of the patched copy. `test-results.json` and `upstream-test-output.txt` record its result, Python/pytest versions and offline dependency locations. This test process neither altered the installed runtime nor used network/model calls.

For local application, first preserve the installed original outside the application bundle and verify its original hash. Stop RUSH Lab normally, replace only the installed `nanoagent/site/nanoagent/uploaded/outcome.py` with the reviewed patched bytes, verify the patched hash, then reopen RUSH Lab normally. The runner's `nanoagent.pth` imports this local `site/` tree; a fresh process loads the change. Record the application and restart separately. For rollback, stop the app normally, restore the verified original bytes, verify the original hash, and reopen. An app update can replace the runtime; do not assume this patch persists or apply it to an unknown file hash.

This is a local platform compatibility modification, separate from the original COMP580 agent and its experimental conditions. The agent wheel contains only `src/comp580_agent`; neither this patch nor platform source copies belong in that wheel. The before/after copies are locally ignored and must not enter a public submission.

Upstream license notice (`references/nanoagent/LICENSE`):

> Copyright (c) 2026 RUSH Lab. All rights reserved.
>
> This software and its documentation (the "Software") are the property of
> RUSH Lab. Without RUSH Lab's prior written permission, no one may copy,
> modify, distribute, sublicense, or reverse engineer, decompile, or
> disassemble the Software, in whole or in part.
>
> Plugins are excepted: helpinghands/plugins/ and every NanoAgent plugin carry
> their own MIT LICENSE, which governs them.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED. IN NO EVENT SHALL RUSH LAB BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR ITS USE.
