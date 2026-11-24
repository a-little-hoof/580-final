"""Offline synthetic correctness and leakage checks; these are not experiment runs."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import math
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "validators" / f"{name}.py")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


checker = module("validate")
builder = module("build_fixtures")
MANIFEST = json.loads((ROOT / "fixtures/manifest.json").read_text())
PRIVATE = json.loads((ROOT / "validators/references.json").read_text())["cases"]


class Validators(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def answer(self, identifier, answer):
        workspace = self.root / identifier
        if not workspace.exists():
            shutil.copytree(ROOT / "fixtures" / identifier, workspace)
        (workspace / "answer.json").write_text(json.dumps(answer), encoding="utf-8")
        return checker.validate_case(identifier, workspace)

    def correct(self, identifier):
        ref = PRIVATE[identifier]
        plugin, case = identifier.split("/")
        if plugin == "log-triage": return {"case": case, "fault": ref["fault"], "evidence": ref["evidence"][0]}
        if plugin == "cipher-crack": return {"case": case, "key": ref["key"], "plaintext": ref["plaintext"]}
        if plugin == "path-probe": return {"case": case, "route": ["A", "B", "D", "E"], "cost": 9}
        if plugin == "regex-infer": return {"case": case, "pattern": ref["rule"]}
        if plugin == "stat-pick": return {"case": case, "statistic": "spread", "value": statistics.pstdev(ref["numbers"])}
        raise AssertionError(identifier)

    def test_all_five_correct_answers(self):
        for entry in MANIFEST["cases"]:
            with self.subTest(case=entry["id"]):
                got = self.answer(entry["id"], self.correct(entry["id"]))
                self.assertTrue(got["valid"], got)
                self.assertEqual(got["status"], "passed")

    def test_log_alternate_evidence_and_surrounding_whitespace(self):
        identifier = "log-triage/edge-proxy"
        for line in PRIVATE[identifier]["evidence"]:
            answer = self.correct(identifier) | {"evidence": "\n " + line + " \t"}
            self.assertTrue(self.answer(identifier, answer)["valid"])

    def test_log_wrong_fault_and_three_citation_errors(self):
        identifier = "log-triage/edge-proxy"
        base = self.correct(identifier)
        cases = [({"fault": "timeout"}, 0), ({"evidence": "invented"}, 0.25),
                 ({"evidence": PRIVATE[identifier]["lines"][0]}, 0.5), ({"evidence": "  "}, 0)]
        for changes, score in cases:
            with self.subTest(changes=changes):
                got = self.answer(identifier, base | changes)
                self.assertFalse(got["valid"])
                self.assertEqual(got["task_verdict"]["score"], score)

    def test_cipher_normalization(self):
        identifier = "cipher-crack/telegram"
        answer = self.correct(identifier)
        answer.update(key=" " + answer["key"].lower() + "\n", plaintext="\t" + answer["plaintext"].lower() + "  ")
        self.assertTrue(self.answer(identifier, answer)["valid"])

    def test_cipher_wrong_key_correct_text_has_score_one_but_fails(self):
        identifier = "cipher-crack/telegram"
        base = self.correct(identifier)
        for key in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            got = self.answer(identifier, base | {"key": key})
            self.assertEqual(got["valid"], key == base["key"])
            self.assertEqual(got["task_verdict"]["score"], 1)

    def test_cipher_corrupted_text_key_and_internal_spacing(self):
        identifier = "cipher-crack/telegram"
        base = self.correct(identifier)
        for changes in [{"key": "AA"}, {"key": "1"}, {"plaintext": base["plaintext"] + "!"},
                        {"plaintext": base["plaintext"].replace(" ", "  ", 1)}, {"plaintext": "A" * 401}]:
            self.assertFalse(self.answer(identifier, base | changes)["valid"])

    def test_both_optimal_paths_pass(self):
        identifier = "path-probe/quarry"
        for middle in ("B", "C"):
            self.assertTrue(self.answer(identifier, {"case": "quarry", "route": ["A", middle, "D", "E"], "cost": 9})["valid"])

    def test_route_nonoptimal_repeated_and_invented_edges(self):
        identifier = "path-probe/quarry"
        got = self.answer(identifier, {"case": "quarry", "route": ["A", "E"], "cost": 10})
        self.assertFalse(got["valid"])
        self.assertEqual(got["task_verdict"]["score"], 0.9)
        for route, cost in [(["A", "B", "A", "E"], 16), (["A", "D", "E"], 3),
                            (["E", "D", "B", "A"], 9), (["A", "B", "D", "E"], 8), ([], 0)]:
            self.assertFalse(self.answer(identifier, {"case": "quarry", "route": route, "cost": cost})["valid"])

    def test_stat_tolerance_and_independent_sample_comparison(self):
        identifier = "stat-pick/sensor-drift"
        base = self.correct(identifier)
        tolerance = 1e-6 * max(1, abs(base["value"]))
        self.assertTrue(self.answer(identifier, base | {"value": base["value"] + tolerance * 0.9})["valid"])
        for value in (base["value"] + tolerance * 1.1, statistics.stdev(PRIVATE[identifier]["numbers"])):
            got = self.answer(identifier, base | {"value": value})
            self.assertFalse(got["valid"])
            self.assertEqual(got["task_verdict"]["score"], 0.5)
        got = self.answer(identifier, base | {"statistic": "mean"})
        self.assertEqual(got["task_verdict"]["score"], 0)

    def test_regex_alternative_pattern_and_finite_scope(self):
        identifier = "regex-infer/widget-code"
        patterns = [r"[A-Z][A-Z]-[0-9][0-9][0-9](?:-R)?", PRIVATE[identifier]["rule"] + "|Z"]
        for pattern in patterns:
            self.assertTrue(self.answer(identifier, {"case": "widget-code", "pattern": pattern})["valid"])
        # Accepting Z demonstrates held-out agreement rather than full language equivalence.
        self.assertIsNotNone(re.fullmatch(patterns[1], "Z"))

    def test_regex_memorizing_visible_examples_fails_heldout(self):
        identifier = "regex-infer/widget-code"
        public = json.loads((ROOT / "fixtures" / identifier / "input.json").read_text())
        pattern = "|".join(re.escape(e["text"]) for e in public["examples"] if e["matches"])
        got = self.answer(identifier, {"case": "widget-code", "pattern": pattern})
        self.assertFalse(got["valid"])
        self.assertEqual(got["task_verdict"]["score"], 0.6)

    def test_regex_constraints(self):
        identifier = "regex-infer/widget-code"
        cases = [("", "empty_pattern"), (" a", "pattern_surrounding_whitespace"),
                 ("x" * 121, "pattern_too_long"), ("[", "invalid_pattern"), ("(A+)+", "nested_quantifier")]
        for pattern, code in cases:
            got = self.answer(identifier, {"case": "widget-code", "pattern": pattern})
            self.assertFalse(got["valid"])
            self.assertEqual(got["task_verdict"]["code"], code)

    def test_regex_worker_timeout_is_unknown_not_wrong_answer(self):
        identifier = "regex-infer/widget-code"
        with patch.object(checker.subprocess, "run", side_effect=subprocess.TimeoutExpired("private regex checker", 2)):
            got = self.answer(identifier, self.correct(identifier))
        self.assertIsNone(got["valid"])
        self.assertIsNone(got["task_verdict"])
        self.assertEqual(got["status"], "verifier_error")

    def test_schema_rejects_case_mismatch_extras_and_wrong_types(self):
        changes = {
            "log-triage/edge-proxy": [{"case": "night-batch"}, {"evidence": []}, {"fault": "BAD-CONFIG"}],
            "cipher-crack/telegram": [{"key": 1}],
            "path-probe/quarry": [{"cost": True}, {"cost": 9.0}, {"route": ["A", 2, "E"]}],
            "regex-infer/widget-code": [{"pattern": None}],
            "stat-pick/sensor-drift": [{"value": True}, {"value": "1.8"}, {"value": 10 ** 1000}],
        }
        for identifier, mutations in changes.items():
            for mutation in mutations + [{"extra": "not allowed"}]:
                got = self.answer(identifier, self.correct(identifier) | mutation)
                self.assertEqual(got["status"], "invalid_answer", got)
                self.assertIsNone(got["task_verdict"])
        got = self.answer("cipher-crack/telegram", {"case": "telegram"})
        self.assertEqual(got["status"], "invalid_answer")

    def test_strict_json_rejects_duplicates_nonfinite_and_overflow(self):
        for raw in ['{"a":1,"a":2}', '{"a":{"b":1,"b":2}}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e9999}']:
            with self.subTest(raw=raw), self.assertRaises(ValueError): checker.strict_json(raw)

    def test_invalid_json_files_fail_without_crashing(self):
        identifier = "stat-pick/sensor-drift"
        self.answer(identifier, self.correct(identifier))
        workspace = self.root / identifier
        for raw in ['{', '{"case":"sensor-drift","case":"sensor-drift"}',
                    '{"case":"sensor-drift","statistic":"spread","value":NaN}',
                    '{"case":"sensor-drift","statistic":"spread","value":1e9999}']:
            (workspace / "answer.json").write_text(raw)
            self.assertEqual(checker.validate_case(identifier, workspace)["status"], "invalid_answer")

    def test_integrity_failure_keeps_semantic_verdict_separate(self):
        identifier = "cipher-crack/telegram"
        self.answer(identifier, self.correct(identifier))
        workspace = self.root / identifier
        for name in ("input.json", "prompt.txt"):
            path = workspace / name
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            got = checker.validate_case(identifier, workspace)
            self.assertFalse(got["valid"])
            self.assertEqual(got["status"], "integrity_failed")
            self.assertTrue(got["task_verdict"]["valid"])
            path.write_bytes(original)
            path.unlink()
            self.assertEqual(checker.validate_case(identifier, workspace)["status"], "integrity_failed")
            path.write_bytes(original)

    def test_missing_and_symlink_answers_or_inputs_fail(self):
        identifier = "cipher-crack/telegram"
        self.answer(identifier, self.correct(identifier))
        workspace = self.root / identifier
        answer = workspace / "answer.json"
        answer.unlink()
        self.assertEqual(checker.validate_case(identifier, workspace)["status"], "invalid_answer")
        elsewhere = self.root / "outside.json"
        elsewhere.write_text(json.dumps(self.correct(identifier)))
        answer.symlink_to(elsewhere)
        self.assertEqual(checker.validate_case(identifier, workspace)["status"], "invalid_answer")
        answer.unlink()
        self.answer(identifier, self.correct(identifier))
        source = workspace / "input.json"
        source.unlink()
        source.symlink_to(ROOT / "fixtures" / identifier / "input.json")
        self.assertEqual(checker.validate_case(identifier, workspace)["status"], "integrity_failed")

    def test_cli_emits_passed_result_and_zero_exit(self):
        identifier = "path-probe/quarry"
        self.answer(identifier, self.correct(identifier))
        got = subprocess.run([sys.executable, str(ROOT / "validators/validate.py"), "--case", identifier,
                              "--workspace", str(self.root / identifier)], capture_output=True, text=True)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertTrue(json.loads(got.stdout)["valid"])


class FixturePreparation(unittest.TestCase):
    def test_exact_public_allowlist_and_no_private_fields(self):
        fields = {"log-triage": {"case", "lines"}, "cipher-crack": {"case", "ciphertext"},
                  "path-probe": {"case", "start", "goal", "links"}, "regex-infer": {"case", "examples"},
                  "stat-pick": {"case", "column", "question", "numbers"}}
        for entry in MANIFEST["cases"]:
            directory = ROOT / "fixtures" / entry["directory"]
            self.assertEqual({p.name for p in directory.iterdir()}, {"input.json", "prompt.txt"})
            public = json.loads((directory / "input.json").read_text())
            self.assertEqual(set(public), fields[entry["plugin_id"]])
            prompt = (directory / "prompt.txt").read_text()
            self.assertEqual(prompt, prompt.strip(), "benchmark publication requires no outer whitespace")
            ref = PRIVATE[entry["id"]]
            combined = (directory / "input.json").read_text() + (directory / "prompt.txt").read_text()
            if entry["plugin_id"] == "cipher-crack": self.assertNotIn(ref["plaintext"], combined)
            if entry["plugin_id"] == "regex-infer":
                self.assertNotIn(ref["rule"], combined)
                self.assertTrue({e["text"] for e in ref["heldout"]}.isdisjoint(e["text"] for e in public["examples"]))

    def test_all_manifest_hashes_and_license(self):
        for entry in MANIFEST["cases"]:
            for name, expected in entry["files"].items():
                raw = (ROOT / "fixtures" / entry["directory"] / name).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected["sha256"])
                self.assertEqual(len(raw), expected["bytes"])
        license_bytes = (ROOT / "fixtures" / MANIFEST["license"]["file"]).read_bytes()
        self.assertEqual(hashlib.sha256(license_bytes).hexdigest(), MANIFEST["license"]["sha256"])

    def test_ast_selection_does_not_evaluate_calls(self):
        tree = ast.parse('VALUES = {Case.X: __import__("does_not_exist")}')
        with self.assertRaises(ValueError): ast.literal_eval(builder.selected(tree, "VALUES", "X"))

    def test_rebuild_is_byte_identical(self):
        reference_root = builder.PROJECT / "references"
        missing = [plugin for plugin, *_ in builder.SPECS
                   if not (reference_root / plugin / ".git").exists()]
        if missing:
            self.skipTest("Optional provenance rebuild needs ignored pinned plugin checkouts: " + ", ".join(missing)
                          + "; ordinary fixture/hash/validator tests remain offline")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            builder.build(reference_root=reference_root, output_root=destination)
            for path in (ROOT / "fixtures").rglob("*"):
                if path.is_file(): self.assertEqual(path.read_bytes(), (destination / path.relative_to(ROOT)).read_bytes())
            self.assertEqual((ROOT / "validators/references.json").read_bytes(), (destination / "validators/references.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
