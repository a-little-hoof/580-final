"""Offline synthetic accounting fixtures; none are experiment runs."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from analyze_graphs import analyze_evidence, analyze_graph, compare_export, digest, task_invocations


def call(prompt=10, completion=2, cached=3, **extra):
    return {"kind": "agent", "error": None, "usage": {
        "prompt_tokens": prompt, "completion_tokens": completion,
        "total_tokens": prompt + completion, "cached_tokens": cached},
        "cost": 0.01, "duration_s": 1, **extra}


def graph():
    return {"nodes": [
        {"id": "outer", "type": "agent_reply", "modelCalls": [call()]},
        {"id": "task", "type": "task"},
        {"id": "inner", "type": "decision", "parent": "task", "modelCalls": [call(20, 4, 7)]},
    ], "edges": []}


class GraphAccountingTests(unittest.TestCase):
    def test_outer_nested_and_cached_subset_are_not_double_counted(self):
        result = analyze_graph(graph())
        totals = result["totals"]
        self.assertEqual(totals["all"]["call_records"], 2)
        self.assertEqual(totals["all"]["usage"]["prompt_tokens"]["known_subtotal"], 30)
        self.assertEqual(totals["all"]["usage"]["total_tokens"]["known_subtotal"], 36)
        self.assertEqual(totals["all"]["usage"]["cached_tokens"]["known_subtotal"], 10)
        matches = compare_export({"usage": call()["usage"], "cost": .01}, totals)
        self.assertTrue(matches["outer"]["usage"]["prompt_tokens"]["equal"])
        self.assertFalse(matches["all"]["usage"]["prompt_tokens"]["equal"])

    def test_identical_calls_are_distinct_records(self):
        raw = graph()
        raw["nodes"][0]["modelCalls"].append(copy.deepcopy(call()))
        self.assertEqual(analyze_graph(raw)["totals"]["outer"]["call_records"], 2)

    def test_failure_missing_usage_and_missing_model_node_stay_explicit(self):
        raw = graph()
        raw["nodes"][2]["modelCalls"] = [{"kind": "agent", "error": "synthetic failure", "duration_s": 3}]
        raw["nodes"].append({"id": "unknown", "type": "agent_reply"})
        result = analyze_graph(raw)
        nested = result["totals"]["nested"]
        self.assertEqual(nested["failed_records"], 1)
        self.assertIsNone(nested["usage"]["prompt_tokens"]["known_subtotal"])
        self.assertEqual(nested["usage"]["prompt_tokens"]["missing_calls"], 1)
        self.assertEqual(nested["model_call_seconds"]["known_subtotal"], 3)
        self.assertEqual(len(result["unmeasured_model_nodes"]), 1)
        self.assertIsNone(compare_export({"usage": {"prompt_tokens": 10}}, result["totals"])["all"]["usage"]["prompt_tokens"]["equal"])

    def test_duplicate_nodes_and_aggregate_copies_are_rejected(self):
        raw = graph()
        raw["nodes"].append(copy.deepcopy(raw["nodes"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            analyze_graph(raw)
        raw = graph()
        raw["nodes"][0]["modelCalls"][0]["kind"] = "tool"
        with self.assertRaisesRegex(ValueError, "possible duplicate"):
            analyze_graph(raw)

    def test_broken_and_cyclic_ancestry_rejected(self):
        for parent in ("missing", "inner"):
            raw = graph()
            raw["nodes"][2]["parent"] = parent
            with self.assertRaisesRegex(ValueError, "Cyclic or missing"):
                analyze_graph(raw)

    def test_unknown_status_and_invalid_numbers_do_not_become_zero(self):
        raw = graph()
        entry = raw["nodes"][0]["modelCalls"][0]
        del entry["error"]
        entry["usage"]["prompt_tokens"] = True
        entry["cost"] = float("nan")
        totals = analyze_graph(raw)["totals"]["outer"]
        self.assertEqual(totals["unknown_status_records"], 1)
        self.assertIsNone(totals["usage"]["prompt_tokens"]["known_subtotal"])
        self.assertIsNone(totals["reported_cost_usd"]["known_subtotal"])

    def test_raw_result_utf8_sizes_exclude_submit_and_preserve_structured_unknown(self):
        raw = graph()
        for name, value in (("read", "é🙂"), ("other", {"lines": ["text"]}), ("submit", "ok")):
            raw["nodes"] += [{"id": name, "type": "tool", "parent": "task", "label": name},
                             {"id": name + ".output", "type": "tool_result", "parent": "task", "value": value}]
            raw["edges"].append({"from": name, "to": name + ".output", "relation": "generated"})
        got = analyze_graph(raw)["nested_data_tool_results"]
        self.assertEqual(got["known_total_utf8_bytes"], 6)
        self.assertEqual(got["known_text_results"], 1)
        self.assertEqual(got["missing_raw_text_results"], 1)
        self.assertEqual(got["records"][0]["raw_text_characters"], 2)

    def test_evidence_roundtrip_ui_comparison_and_changed_export_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "synthetic"
            turns = folder / "turns" / "001"
            turns.mkdir(parents=True)
            local = {"metrics": {"usage": call()["usage"], "cost": .01}, "version": "fixture"}
            chat = {"session": "synthetic", "plugin": "fixture", "turns": [local]}
            export = {"type": "chat", "session_id": "synthetic", "turns": [{**local, "messages": {}}]}
            (folder / "chat.json").write_text(json.dumps(chat))
            (turns / "graph.json").write_text(json.dumps(graph()))
            (turns / "messages.json").write_text("{}")
            (folder / "ui_observation.json").write_text(json.dumps({"input_tokens": 30, "output_tokens": 6}))
            path = root / "export.jsonl"
            path.write_text(json.dumps(export) + "\n")
            provenance = {"export": {"path": "export.jsonl", "sha256": digest(path)},
                          "synced_files": [{"copy": str(p.relative_to(root)), "sha256": digest(p)}
                                           for p in (folder / "chat.json", turns / "graph.json", turns / "messages.json")]}
            (folder / "provenance.json").write_text(json.dumps(provenance))
            got = analyze_evidence(folder, root)["turns"][0]
            self.assertTrue(got["ui_token_comparison"]["input_tokens"]["equal"])
            self.assertTrue(got["messages_equal_export"])
            original = (turns / "graph.json").read_text()
            (turns / "graph.json").write_text(original + "\n")
            with self.assertRaisesRegex(ValueError, "Captured-file hash changed"):
                analyze_evidence(folder, root)
            (turns / "graph.json").write_text(original)
            path.write_text(path.read_text() + "\n")
            with self.assertRaisesRegex(ValueError, "hash changed"):
                analyze_evidence(folder, root)

    def test_full_score_is_not_substituted_for_false_verdict(self):
        got = task_invocations({"tools": [{"name": "task", "isError": False,
                                          "output": '{"verdict":{"valid":false,"score":1}}'}]})
        self.assertFalse(got[0]["valid"])


if __name__ == "__main__":
    unittest.main()
