"""Synthetic offline regression checks; none of these fixtures are experiment runs."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from summarize_traces import summarize_chat, summarize_files


def chat(turn):
    return {"type": "chat", "kind": "nanoagent", "session_id": "synthetic-test", "turns": [turn], "calls": []}


class TraceSummaryTests(unittest.TestCase):
    def test_missing_metrics_do_not_become_atif_zero(self):
        raw = chat({"prompt": 'case: edge-proxy”', "metrics": None, "error": "401 expired",
                    "messages": {"agent": {"model_name": "recorded-model"}, "final_metrics": {"total_prompt_tokens": 0}}})
        turn = summarize_chat(raw, "synthetic", 1)["turns"][0]
        self.assertIsNone(turn["reported_metrics"]["input_tokens"])
        self.assertEqual(turn["model"], "recorded-model")
        self.assertEqual(turn["prompt"], 'case: edge-proxy”')
        self.assertEqual(turn["observation"], "execution_error")

    def test_invalid_verdict_with_full_score_is_not_success(self):
        tool = {"name": "crack-cipher", "isError": False,
                "output": json.dumps({"verdict": {"valid": False, "score": 1.0}})}
        turn = summarize_chat(chat({"tools": [tool]}), "synthetic", 1)["turns"][0]
        self.assertFalse(turn["task_invocations"][0]["verified_success"])
        self.assertEqual(turn["observation"], "failed_verifier_result_present")

    def test_ledger_and_repeated_history_are_not_added(self):
        raw = chat({"metrics": {"usage": {"prompt_tokens": 17}},
                    "messages": {"final_metrics": {"total_prompt_tokens": 1000}}})
        raw["calls"] = [{"input_tokens": 17}]
        result = summarize_chat(raw, "synthetic", 1)
        self.assertEqual(result["reported_turn_metric_sums"]["input_tokens"]["known_subtotal"], 17)
        self.assertIsNone(result["reported_turn_metric_sums"]["cached_input_tokens"]["known_subtotal"])

    def test_tool_error_and_retry_both_survive(self):
        tools = [{"name": "task", "isError": True, "output": "failure”"},
                 {"name": "task", "isError": False, "output": '{"verdict":{"valid":true,"score":1}}'}]
        turn = summarize_chat(chat({"tools": tools}), "synthetic", 1)["turns"][0]
        self.assertEqual(len(turn["task_invocations"]), 2)
        first = turn["task_invocations"][0]
        self.assertIsNone(first["verified_success"])
        self.assertEqual(first["output_characters"], 8)
        self.assertEqual(first["output_utf8_bytes"], 10)
        self.assertTrue(turn["task_invocations"][1]["verified_success"])

    def test_no_invocation_is_not_verified_from_prose(self):
        turn = summarize_chat(chat({"answer": "I succeeded", "tools": []}), "synthetic", 1)["turns"][0]
        self.assertEqual(turn["observation"], "no_task_invocation_recorded")

    def test_missing_turn_metrics_have_known_subtotal_and_missing_count(self):
        raw = chat({"metrics": {"usage": {"prompt_tokens": 8}}})
        raw["turns"].append({"metrics": None})
        got = summarize_chat(raw, "synthetic", 1)["reported_turn_metric_sums"]["input_tokens"]
        self.assertEqual(got, {"known_subtotal": 8, "known_turns": 1, "missing_turns": 1})

    def test_duplicate_sessions_rejected_to_prevent_double_counting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.jsonl"
            raw = chat({"metrics": None})
            path.write_text(json.dumps(raw) + "\n" + json.dumps(copy.deepcopy(raw)) + "\n")
            with self.assertRaisesRegex(ValueError, "Duplicate session"):
                summarize_files([path], "historical_descriptive")


if __name__ == "__main__":
    unittest.main()
