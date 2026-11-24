# Log Triage: installed-source audit

Inspected November 23, 2026 (America/Chicago). The parent agent observed Log Triage v0.1.0 and its Source on GitHub link in the current Rush Lab UI:

<https://github.com/a-little-hoof/log-triage/tree/432a4b9ac4a26487d3350c92a31809e3b4ba93f0>

The unchanged local checkout at `references/log-triage` matches that exact commit. This establishes advertised source provenance, not an independently measured hash of the installed package. No model call or app action was performed by this source audit. Tests were inspected, not run.

- Plugin ID: `log-triage`; manifest version: `0.1.0`.
- Task: `triage-log`, runner `decide`.
- Allowed case inputs: `night-batch`, `api-gateway`, `report-worker`, `edge-proxy`; selected pilot input: `{"case":"edge-proxy"}`.
- Visible task tool: `read_log({case})`, returning `case`, `lines`, `count`.
- Hidden reference tool: `incident({case})`. It supplies the reference label and accepted evidence lines and is not an agent task tool.
- Output: `{"case":<Case>,"fault":<Fault>,"evidence":<str>}`. The fault enum contains `disk-full`, `auth-rejected`, `timeout`, `bad-config`, `rate-limited`, `out-of-memory`.

The verifier in `verifier/finding.py` checks submitted and reference case identity, a nonblank citation, and reference coherence. The reference log must be nonempty, have at most 500 lines, contain no blank line or line longer than 500 characters, and contain every reference evidence line. It compares the fault to the pinned reference label and the citation to the accepted evidence lines, trimming surrounding whitespace. Internal text, timestamps and level labels remain significant.

Wrong fault gives `valid=false, score=0`; correct fault with a citation absent from the log gives `0.25`; correct fault with a real but nondiagnostic line gives `0.5`; correct fault with accepted evidence gives `valid=true, score=1`. The selected edge-proxy reference accepts two distinct evidence lines. A reviewer must not reject a valid alternate citation merely because a manual expectation names only one.

Correctness scope is label and citation agreement with a coherent pinned reference. The verifier does not independently derive incident causality. Logs are fixed literal text; there is no generation seed. These limitations should be stated in the report.

An AST-only comparison verified that all eight edge-proxy log lines exactly match the archived NanoAgent `step1_log_triage_cases.json` context. That does not make the archived prompt an appropriate Session pilot: it includes the complete log. The current pilot uses a case-only invocation, leaving the installed task to obtain data through its actual tools.

Inspected source: `nanoagent.yaml`, `contract.py`, `src/plugin/incidents.py`, `src/plugin/triage.py`, `verifier/{checks,finding,log}.py`, `tests/test_verifier.py`, and `README.md`. Exact contract/verifier SHA-256 values are recorded in [manifest.json](manifest.json). This audit is researcher-side evidence, not model-visible task material.
