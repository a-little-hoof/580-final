"""Extract explicit public fields from pinned source ASTs; never import plugin code.

Research-side preparation only. This file and references.json must never enter an
evaluated agent's package or workspace. Re-running deterministically replaces the
generated fixtures and private references; it makes no model or network calls.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]
CONTROLLED = Path(__file__).resolve().parents[1]
SPECS = [
    ("log-triage", "triage-log", "edge-proxy", "EDGE_PROXY", "432a4b9ac4a26487d3350c92a31809e3b4ba93f0", "incidents"),
    ("cipher-crack", "crack-cipher", "telegram", "TELEGRAM", "6b31efa773128ef9d6469541a15bbca2cac0cc88", "cases"),
    ("path-probe", "find-route", "quarry", "QUARRY", "96b2b4192a9ae6933db834a796553ad868beaaf6", "maps"),
    ("regex-infer", "infer-pattern", "widget-code", "WIDGET_CODE", "3fc05876e6e3fc37d3544fe87a15fc3d1f2123da", "cases"),
    ("stat-pick", "answer-question", "sensor-drift", "SENSOR_DRIFT", "5fcfedf4507d779e918a87d8aa299ca51f1ae45c", "tables"),
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def assignment(tree: ast.Module, name: str) -> ast.expr:
    values = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    if len(values) != 1:
        raise ValueError(f"expected exactly one assignment to {name}")
    return values[0]


def selected(tree: ast.Module, name: str, member: str) -> ast.expr:
    table = assignment(tree, name)
    if not isinstance(table, ast.Dict):
        raise ValueError(f"{name} is not a literal dictionary")
    values = [value for key, value in zip(table.keys, table.values)
              if isinstance(key, ast.Attribute) and isinstance(key.value, ast.Name)
              and key.value.id == "Case" and key.attr == member]
    if len(values) != 1:
        raise ValueError(f"expected one {name}[Case.{member}]")
    return values[0]


def enums(tree: ast.Module, name: str) -> dict[str, str]:
    [node] = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name]
    return {target.id: ast.literal_eval(item.value) for item in node.body if isinstance(item, ast.Assign)
            for target in item.targets if isinstance(target, ast.Name)}


def enum_literal(node: ast.expr, table: dict[str, str], class_name: str) -> str:
    if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == class_name):
        raise ValueError(f"expected {class_name} enum literal")
    return table[node.attr]


def schema(case: str, fields: dict) -> dict:
    properties = {"case": {"type": "string", "enum": [case]}, **fields}
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def extract(plugin: str, case: str, member: str, tree: ast.Module, contract: ast.Module):
    """Return public input, private reference, public output schema, instructions, provenance recipe."""
    string = {"type": "string"}
    if plugin == "log-triage":
        incident = selected(tree, "INCIDENTS", member)
        if not isinstance(incident, ast.Call) or not isinstance(incident.func, ast.Name) or incident.func.id != "Incident" or incident.args:
            raise ValueError("expected a keyword-only Incident declaration")
        parts = {kw.arg: kw.value for kw in incident.keywords}
        lines = list(ast.literal_eval(parts["lines"]))
        faults = enums(contract, "Fault")
        fault = enum_literal(parts["fault"], faults, "Fault")
        evidence = [lines[index] for index in ast.literal_eval(parts["evidence"])]
        public = {"case": case, "lines": lines}
        private = {**public, "fault": fault, "evidence": evidence}
        output = schema(case, {"fault": {"type": "string", "enum": list(faults.values())}, "evidence": string})
        instructions = (
            "Diagnose the cause shown by the log in input.json, rather than merely naming a downstream symptom. "
            "Each line is true. Select one fault: disk-full (a write failed because a volume is full), "
            "auth-rejected (credentials were refused), timeout (something waited and gave up, with no other cause), "
            "bad-config (a service rejected its configuration), rate-limited (a quota or request limit was reached), "
            "or out-of-memory (a process exceeded its memory allowance). Cite one diagnostic log line exactly, "
            "including timestamp and level. The full original log is supplied as a readable input file."
        )
        recipe = "INCIDENTS[Case.EDGE_PROXY].lines only; private fault/evidence/decoy metadata excluded"
    elif plugin == "cipher-crack":
        key, plaintext = ast.literal_eval(selected(tree, "PUZZLES", member))
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        ciphertext = "".join(alphabet[(ord(char) - ord("A") + ord(key) - ord("A")) % 26]
                             if char in alphabet else char for char in plaintext)
        public = {"case": case, "ciphertext": ciphertext}
        private = {**public, "key": key, "plaintext": plaintext}
        output = schema(case, {"key": string, "plaintext": string})
        instructions = (
            "Find the Caesar-shift key and English plaintext of the ciphertext in input.json. "
            "Letters are uppercase A-Z; spaces were left unchanged. A key is one letter: A shifts by zero, "
            "B by one, through Z by twenty-five. Encryption moves letters forward and decryption moves them back "
            "with wraparound. Exactly one key gives the intended English message. Submit the key and plaintext "
            "that agree with one another. You may compute candidate shifts yourself; no solution is provided."
        )
        recipe = "derive ciphertext from selected PUZZLES literal by independent Caesar arithmetic; emit case/ciphertext only"
    elif plugin == "path-probe":
        start, goal, links = ast.literal_eval(selected(tree, "MAPS", member))
        public = {"case": case, "start": start, "goal": goal,
                  "links": [{"start": a, "end": b, "cost": cost} for a, b, cost in links]}
        private = dict(public)
        output = schema(case, {"route": {"type": "array", "items": string}, "cost": {"type": "integer"}})
        instructions = (
            "Find a minimum-total-cost route from start to goal in input.json. Each link is listed once, "
            "can be travelled in either direction, and has positive integer cost. Submit the route as node names "
            "in travel order, starting at start and ending at goal, with no repeated node, and its exact summed cost. "
            "Any minimum-cost route is acceptable; matching a particular reference route is not required. "
            "This is a full-information adaptation: the complete graph is available in the input file, "
            "instead of discovering incident edges through the original plugin's neighbours tool."
        )
        recipe = "MAPS[Case.QUARRY] start/goal/edge literals; no shortest-route computation or answer included"
    elif plugin == "regex-infer":
        positive, negative = ast.literal_eval(selected(tree, "VISIBLE", member))
        visible = [{"text": value, "matches": True} for value in positive] + [{"text": value, "matches": False} for value in negative]
        yes, no = ast.literal_eval(selected(tree, "HOLDOUT", member))
        public = {"case": case, "examples": visible}
        private = {"case": case, "rule": ast.literal_eval(selected(tree, "RULES", member)),
                   "heldout": [{"text": value, "matches": True} for value in yes] + [{"text": value, "matches": False} for value in no]}
        output = schema(case, {"pattern": string})
        instructions = (
            "Infer the hidden string rule from the labelled visible examples in input.json. Return a Python "
            "regular expression, evaluated with re.fullmatch, which describes the entire string. Anchors are optional. "
            "Do not simply list the accepted examples: grading uses a separate held-out set. You may test a candidate "
            "on the visible examples. The pattern must be nonblank, have no surrounding whitespace, and contain "
            "at most 120 characters. The verifier also rejects a group containing a quantifier when that group "
            "is itself quantified with *, +, or a counted repetition. The hidden rule and held-out examples are not supplied."
        )
        recipe = "VISIBLE[Case.WIDGET_CODE] only, accepted then rejected; RULES/HOLDOUT excluded from public output"
    elif plugin == "stat-pick":
        parts = selected(tree, "TABLES", member)
        if not isinstance(parts, ast.Tuple) or len(parts.elts) != 4:
            raise ValueError("expected four-field TABLES tuple")
        column, question, numbers = [ast.literal_eval(parts.elts[index]) for index in (0, 1, 3)]
        statistics = enums(contract, "Statistic")
        expected = enum_literal(parts.elts[2], statistics, "Statistic")
        public = {"case": case, "column": column, "question": question, "numbers": numbers}
        private = {**public, "statistic": expected}
        output = schema(case, {"statistic": {"type": "string", "enum": list(statistics.values())}, "value": {"type": "number"}})
        instructions = (
            "Choose the statistic that answers the question in input.json and compute its value from the readings. "
            "The available statistics are mean (sum divided by count), median (middle after sorting, averaging the "
            "two middle values for even count), mode (unique most frequent value), range (maximum minus minimum), "
            "spread (population standard deviation, with divisor equal to the number of readings), smallest, largest, "
            "and total. Submit both the chosen statistic and its numerical value. Grading uses a tolerance of "
            "1e-6 times max(1, absolute expected value). This is a raw-data adaptation: the original plugin hides "
            "the readings and provides a summarise tool; here the original readings are public and you may compute freely."
        )
        recipe = "TABLES[Case.SENSOR_DRIFT] tuple fields 0,1,3 (column/question/readings); expected statistic field2 excluded"
    else:
        raise ValueError(plugin)
    return public, private, output, instructions, recipe


def build(reference_root: Path = PROJECT / "references", output_root: Path = CONTROLLED) -> dict:
    cases, references, licenses = [], {}, []
    for plugin, task, case, member, commit, module in SPECS:
        repo = reference_root / plugin
        actual = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True)
        if actual != commit or dirty:
            raise ValueError(f"{plugin}: require clean pinned commit {commit}")
        source_path = f"src/plugin/{module}.py"
        source = ast.parse((repo / source_path).read_text(encoding="utf-8"))
        contract = ast.parse((repo / "contract.py").read_text(encoding="utf-8"))
        public, private, answer_schema, instructions, recipe = extract(plugin, case, member, source, contract)
        identifier = f"{plugin}/{case}"
        prompt = (f"Task: {task}; case: {case}.\n\n{instructions}\n\n"
                  "Read input.json using any available tools. Work efficiently; no particular tool or full-data display is required. "
                  "Do not modify input.json or prompt.txt. Write only the final answer object to answer.json, then stop. "
                  "Use these exact fields and types; do not add fields.\n\nAnswer JSON Schema:\n"
                  + json.dumps(answer_schema, ensure_ascii=False, separators=(",", ":")))
        payloads = {"input.json": encoded(public), "prompt.txt": prompt.encode("utf-8")}
        directory = output_root / "fixtures" / identifier
        directory.mkdir(parents=True, exist_ok=True)
        for name, data in payloads.items():
            (directory / name).write_bytes(data)
        used = [source_path, "contract.py", "nanoagent.yaml", "LICENSE"]
        used += [str(path.relative_to(repo)) for path in sorted((repo / "verifier").glob("*.py"))]
        licenses.append((repo / "LICENSE").read_bytes())
        cases.append({
            "id": identifier, "plugin_id": plugin, "task": task, "case": case, "directory": identifier,
            "source": {"repository": f"https://github.com/a-little-hoof/{plugin}", "commit": commit,
                       "version": "0.1.0", "files": {name: digest((repo / name).read_bytes()) for name in used}},
            "extraction": {"method": "explicit AST literal allowlist; no plugin execution", "recipe": recipe},
            "files": {name: {"sha256": digest(data), "bytes": len(data)} for name, data in payloads.items()},
            "answer_schema": answer_schema,
            "adaptation": {"path-probe": "full graph replaces partial discovery", "stat-pick": "raw readings replace summary-only access"}.get(plugin, "public data fixture replaces plugin tool access"),
        })
        references[identifier] = private
    if len(set(licenses)) != 1:
        raise ValueError("upstream licenses differ; retain each separately")
    license_path = output_root / "fixtures" / "LICENSE.upstream-MIT.txt"
    license_path.write_bytes(licenses[0])
    manifest = {
        "schema_version": 1, "study": "controlled course-task public adaptations",
        "status": "prepared; no custom-agent runs represented", "cases": cases,
        "license": {"file": license_path.name, "sha256": digest(licenses[0]), "applies_to": "source-derived case inputs from all five plugins"},
        "generator": {"path": "study/controlled/validators/build_fixtures.py", "sha256": digest(Path(__file__).read_bytes()),
                      "serialization": "input JSON indent=2, ensure_ascii=false, final LF; prompt UTF-8 with internal LF and no outer whitespace; allow_nan=false"},
        "agent_upload_allowlist": ["input.json", "prompt.txt"],
        "private_reference_policy": "Only one case directory enters an agent workspace. Never upload validators, tests, references, source checkouts or trace graphs.",
    }
    (output_root / "fixtures" / "manifest.json").write_bytes(encoded(manifest))
    private_root = output_root / "validators"
    private_root.mkdir(parents=True, exist_ok=True)
    (private_root / "references.json").write_bytes(encoded({"schema_version": 1, "visibility": "researcher only; never agent-visible", "cases": references}))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path, default=PROJECT / "references")
    parser.add_argument("--output-root", type=Path, default=CONTROLLED)
    args = parser.parse_args()
    built = build(args.reference_root, args.output_root)
    print(json.dumps({"cases": len(built["cases"]), "output_root": str(args.output_root), "model_calls": 0}))
