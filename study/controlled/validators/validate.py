"""Private deterministic checks for the five controlled course-task adaptations.

Run outside the evaluated VM. `validate_case(case_id, workspace)` returns separate
input-integrity and semantic decisions; it never contacts a model or imports a
plugin. A result is a local adapter check, not an official RUSH verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGEX_TIMEOUT_S = 2.0
ANSWER_LIMIT_BYTES = 64 * 1024


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def strict_json(data: str | bytes):
    def invalid_constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    value = json.loads(data, object_pairs_hook=_object, parse_constant=invalid_constant)
    def finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("nonfinite JSON number")
        if isinstance(item, dict):
            for child in item.values(): finite(child)
        if isinstance(item, list):
            for child in item: finite(child)
    finite(value)
    return value


def schema_error(value, schema: dict, path: str = "$input") -> str | None:
    """The small closed schema vocabulary actually used in the public manifest."""
    kind = schema["type"]
    finite_number = False
    if type(value) in (int, float):
        try: finite_number = math.isfinite(float(value))
        except OverflowError: pass
    matches = {
        "object": type(value) is dict, "array": type(value) is list,
        "string": type(value) is str, "integer": type(value) is int,
        "number": finite_number,
    }
    if kind not in matches:
        raise ValueError(f"unsupported trusted schema type {kind}")
    if not matches[kind]:
        return f"{path}: expected {kind}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path}: value outside enum"
    if kind == "object":
        properties = schema["properties"]
        if set(value) != set(schema["required"]):
            return f"{path}: fields must be exactly {', '.join(properties)}"
        for key, child in properties.items():
            problem = schema_error(value[key], child, f"{path}.{key}")
            if problem: return problem
    if kind == "array":
        for index, item in enumerate(value):
            problem = schema_error(item, schema["items"], f"{path}[{index}]")
            if problem: return problem
    return None


def verdict(valid: bool, code: str, score: float | None = None) -> dict:
    return {"valid": valid, "score": float(valid) if score is None else score, "code": code}


def _log(answer: dict, reference: dict) -> dict:
    lines, evidence = reference["lines"], reference["evidence"]
    if (not lines or len(lines) > 500 or any(not line.strip() or len(line) > 500 for line in lines)
            or not evidence or any(line.strip() not in {s.strip() for s in lines} for line in evidence)):
        raise ValueError("incoherent private log reference")
    cited = answer["evidence"].strip()
    if not cited: return verdict(False, "empty_evidence")
    if answer["fault"] != reference["fault"]: return verdict(False, "wrong_fault")
    if cited not in {s.strip() for s in lines}: return verdict(False, "invented_evidence", 0.25)
    if cited not in {s.strip() for s in evidence}: return verdict(False, "nondiagnostic_evidence", 0.5)
    return verdict(True, "fault_and_citation_match")


def _decrypt(ciphertext: str, key: str) -> str:
    shift = ord(key) - ord("A")
    return "".join(chr((ord(char) - ord("A") - shift) % 26 + ord("A"))
                   if "A" <= char <= "Z" else char for char in ciphertext)


def _cipher(answer: dict, reference: dict) -> dict:
    key, text = answer["key"].strip().upper(), answer["plaintext"].strip().upper()
    if len(key) != 1 or not "A" <= key <= "Z": return verdict(False, "invalid_key")
    if not text or len(text) > 400 or any(char != " " and not "A" <= char <= "Z" for char in text):
        return verdict(False, "invalid_plaintext")
    expected = reference["plaintext"]
    if _decrypt(reference["ciphertext"], reference["key"]) != expected:
        raise ValueError("incoherent private cipher reference")
    score = sum(a == b for a, b in zip(text, expected)) / max(len(text), len(expected))
    if _decrypt(reference["ciphertext"], key) != text: return verdict(False, "key_plaintext_disagree", score)
    if text != expected: return verdict(False, "wrong_plaintext", score)
    return verdict(True, "cipher_solved")


def _graph(reference: dict):
    graph = {}
    seen = set()
    for edge in reference["links"]:
        a, b, cost = edge["start"], edge["end"], edge["cost"]
        pair = frozenset((a, b))
        if not a or not b or a == b or type(cost) is not int or cost <= 0 or pair in seen:
            raise ValueError("incoherent private graph reference")
        seen.add(pair)
        graph.setdefault(a, {})[b] = cost
        graph.setdefault(b, {})[a] = cost
    if not graph or reference["start"] not in graph or reference["goal"] not in graph:
        raise ValueError("missing private graph endpoints")
    return graph


def _shortest_cost(graph: dict, start: str, goal: str) -> int:
    """Exhaustive simple paths on the fixed six-node case, independent of upstream Dijkstra."""
    costs = []
    def walk(node, visited, cost):
        if node == goal:
            costs.append(cost)
            return
        for other, weight in graph[node].items():
            if other not in visited: walk(other, visited | {other}, cost + weight)
    walk(start, {start}, 0)
    if not costs: raise ValueError("private graph has no route")
    return min(costs)


def _path(answer: dict, reference: dict) -> dict:
    graph = _graph(reference)
    route = answer["route"]
    if not route or len(route) > 100: return verdict(False, "route_length")
    if len(set(route)) != len(route): return verdict(False, "repeated_node")
    if route[0] != reference["start"] or route[-1] != reference["goal"]: return verdict(False, "route_endpoints")
    cost = 0
    for a, b in zip(route, route[1:]):
        if b not in graph.get(a, {}): return verdict(False, "nonexistent_edge")
        cost += graph[a][b]
    if answer["cost"] != cost: return verdict(False, "wrong_route_cost")
    cheapest = _shortest_cost(graph, reference["start"], reference["goal"])
    if cost > cheapest: return verdict(False, "nonoptimal_route", cheapest / cost)
    return verdict(True, "optimal_route")


def _nested_quantifier(pattern: str) -> bool:
    """Match the pinned verifier's lexical restriction, including its conservative braces rule."""
    stack, in_class, index = [], False, 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            index += 2
            continue
        if in_class:
            in_class = char != "]"
        elif char == "[": in_class = True
        elif char == "(": stack.append(False)
        elif char == ")":
            inner = stack.pop() if stack else False
            following = pattern[index + 1:index + 2]
            if inner and following in ("*", "+", "{"): return True
            if stack and (inner or following in ("*", "+", "?", "{")): stack[-1] = True
        elif char in "*+{" and stack: stack[-1] = True
        index += 1
    return False


def _regex(answer: dict, reference: dict) -> dict:
    pattern = answer["pattern"]
    if not pattern.strip(): return verdict(False, "empty_pattern")
    if pattern != pattern.strip(): return verdict(False, "pattern_surrounding_whitespace")
    if len(pattern) > 120: return verdict(False, "pattern_too_long")
    try: re.compile(pattern)
    except re.error: return verdict(False, "invalid_pattern")
    if _nested_quantifier(pattern): return verdict(False, "nested_quantifier")
    heldout = reference["heldout"]
    if not heldout or any((re.fullmatch(reference["rule"], e["text"]) is not None) != e["matches"] for e in heldout):
        raise ValueError("incoherent private regex reference")
    checked = subprocess.run([sys.executable, str(Path(__file__).with_name("regex_worker.py"))],
                             input=json.dumps({"pattern": pattern, "examples": heldout}),
                             text=True, capture_output=True, timeout=REGEX_TIMEOUT_S, check=True)
    counts = strict_json(checked.stdout)
    if counts["total"] != len(heldout): raise ValueError("regex worker count mismatch")
    return verdict(counts["right"] == counts["total"], "heldout_agreement", counts["right"] / counts["total"])


def _stat(answer: dict, reference: dict) -> dict:
    values = reference["numbers"]
    if not values or len(values) > 10000: raise ValueError("invalid private readings")
    if answer["statistic"] != reference["statistic"]: return verdict(False, "wrong_statistic")
    # Selected fixed case asks for population deviation. Explicit arithmetic is
    # independent of the upstream statistics.pstdev implementation.
    if reference["statistic"] != "spread": raise ValueError("unsupported private statistic case")
    mean = math.fsum(values) / len(values)
    expected = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / len(values))
    if abs(answer["value"] - expected) > 1e-6 * max(1.0, abs(expected)):
        return verdict(False, "wrong_statistic_value", 0.5)
    return verdict(True, "statistic_and_value_match")


CHECKERS = {"log-triage": _log, "cipher-crack": _cipher, "path-probe": _path, "regex-infer": _regex, "stat-pick": _stat}


def validate_case(case_id: str, workspace: str | Path) -> dict:
    manifest = strict_json((ROOT / "fixtures" / "manifest.json").read_bytes())
    matches = [entry for entry in manifest["cases"] if entry["id"] == case_id]
    if len(matches) != 1: raise ValueError(f"unknown controlled case {case_id!r}")
    entry = matches[0]
    references = strict_json(Path(__file__).with_name("references.json").read_bytes())["cases"]
    reference = references[case_id]
    if reference["case"] != entry["case"]: raise ValueError("private reference case mismatch")
    workspace = Path(workspace)
    errors = []
    for name, expected in entry["files"].items():
        path = workspace / name
        if path.is_symlink() or not path.is_file(): errors.append(f"{name}: missing or not a regular file")
        elif path.stat().st_size != expected["bytes"]: errors.append(f"{name}: byte length changed")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]: errors.append(f"{name}: content changed")
    result = {"schema_version": 1, "case_id": case_id, "validator": "local-controlled-v1",
              "integrity": {"valid": not errors, "errors": errors}, "answer_schema": None,
              "task_verdict": None, "valid": False, "status": None}
    try:
        path = workspace / "answer.json"
        if path.is_symlink() or not path.is_file(): raise ValueError("answer.json is missing or not a regular file")
        if path.stat().st_size > ANSWER_LIMIT_BYTES: raise ValueError("answer.json exceeds 64 KiB local limit")
        answer = strict_json(path.read_bytes())
        problem = schema_error(answer, entry["answer_schema"], "$answer")
        if problem: raise ValueError(problem)
        result["answer_schema"] = {"valid": True, "error": None}
    except (ValueError, OSError, UnicodeError) as error:
        result["answer_schema"] = {"valid": False, "error": str(error)}
        result["status"] = "integrity_failed" if errors else "invalid_answer"
        return result
    try:
        result["task_verdict"] = CHECKERS[entry["plugin_id"]](answer, reference)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        result.update(valid=None if not errors else False, status="verifier_error" if not errors else "integrity_failed",
                      verifier_error=f"{type(error).__name__}: {error}")
        return result
    result["valid"] = not errors and result["task_verdict"]["valid"]
    result["status"] = "integrity_failed" if errors else "passed" if result["valid"] else "failed"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    try: result = validate_case(args.case, args.workspace)
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "validator_setup_error", "valid": None, "error": str(error)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["valid"] else 2 if result["valid"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
