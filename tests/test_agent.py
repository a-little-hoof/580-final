"""Provider-free integration tests: injected byte responses, no network sockets."""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from comp580_agent.agent import Agent
from comp580_agent.cli import parser
from comp580_agent.common import AgentError, MAX_OUTPUT_BYTES, MAX_RESPONSE_BYTES
from comp580_agent.gateway import Config


def completion(calls=None, *, model="resolved/model", usage=None, content=None, finish=None):
    message = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = [{"id": f"call-{index}", "type": "function",
                                  "function": {"name": name, "arguments": json.dumps(arguments)}}
                                 for index, (name, arguments) in enumerate(calls)]
    result = {"choices": [{"finish_reason": finish or ("tool_calls" if calls else "stop"), "message": message}]}
    if model is not None:
        result["model"] = model
    if usage is not None:
        result["usage"] = usage
    return json.dumps(result, ensure_ascii=False).encode()


class FakeGateway:
    def __init__(self, responses, *, advance=None):
        self.responses = iter(responses)
        self.requests = []
        self.timeouts = []
        self.advance = advance

    def complete(self, payload, *, timeout):
        self.requests.append(copy.deepcopy(payload))
        self.timeouts.append(timeout)
        if self.advance:
            self.advance()
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name) / "public"
        self.workspace.mkdir()
        (self.workspace / "input.json").write_text('{"data": [1, 2], "label": "雪"}', encoding="utf-8")
        (self.workspace / "answer.json").write_text('{"answer": "string"}')
        self.logs = Path(self.temporary.name) / "logs"
        self.config = Config("https://gateway.invalid/v1", "test-private-key", "pinned/model", 4096)

    def run_agent(self, responses, prompt="Exact request\n  with whitespace  ", **kwargs):
        gateway = FakeGateway(responses)
        agent = Agent(self.config, self.workspace, self.logs, gateway=gateway, **kwargs)
        return agent.run(prompt), gateway

    def test_full_loop_preserves_prompt_data_usage_and_actual_model(self):
        usage = {"prompt_tokens": 12, "completion_tokens": 3,
                 "prompt_tokens_details": {"cached_tokens": 4}}
        result, fake = self.run_agent([
            completion([("read_json", {"path": "input.json"})], usage=usage),
            completion([("write_answer", {"answer": {"answer": "ok"}})], model=None),
        ])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["input_integrity"]["changed_inputs"], [])
        self.assertEqual((self.logs / "prompt.txt").read_text(), "Exact request\n  with whitespace  ")
        self.assertEqual(fake.requests[0]["messages"][1], {"role": "user", "content": "Exact request\n  with whitespace  "})
        self.assertEqual(fake.requests[0]["model"], "pinned/model")
        self.assertEqual(fake.requests[0]["temperature"], 0)
        self.assertEqual(fake.requests[0]["max_tokens"], 4096)
        self.assertEqual(fake.timeouts, [60, 60])
        visible = fake.requests[1]["messages"][-1]["content"]
        self.assertEqual(visible, json.dumps({"path": "input.json", "data": {"data": [1, 2], "label": "雪"}}, ensure_ascii=False, indent=2, allow_nan=False))
        self.assertEqual(result["model_calls"][0]["usage"], usage)
        self.assertEqual(result["model_calls"][0]["resolved_model"], "resolved/model")
        self.assertIsNone(result["model_calls"][1]["usage"])
        self.assertIsNone(result["model_calls"][1]["resolved_model"])
        self.assertEqual(json.loads((self.workspace / "answer.json").read_text()), {"answer": "ok"})

    def test_seeded_schema_is_not_completed_answer(self):
        result, _ = self.run_agent([completion(content="Done")])
        self.assertEqual(result["failure"]["code"], "answer_missing")

    def test_no_retry_after_gateway_failure_and_no_secret(self):
        result, gateway = self.run_agent([AgentError("http_error", "Gateway rejected the request", fatal=True, details={"http_status": 401})])
        self.assertEqual(len(gateway.requests), 1)
        self.assertEqual(result["failure"]["http_status"], 401)
        self.assertIsNone(result["model_calls"][0]["usage"])
        for path in self.logs.rglob("*"):
            if path.is_file():
                self.assertNotIn(self.config.api_key, path.read_text())
                self.assertNotIn("Authorization", path.read_text())

    def test_twelve_call_limit_is_exact(self):
        result, fake = self.run_agent([completion([("read_json", {"path": "input.json"})])] * 12)
        self.assertEqual(result["failure"]["code"], "model_call_limit")
        self.assertEqual(len(fake.requests), 12)

    def test_invalid_tool_arguments_return_error_and_can_recover(self):
        result, fake = self.run_agent([
            completion([("read_json", {"path": "input.json", "extra": True})]),
            completion([("write_answer", {"answer": {"answer": "ok"}})]),
        ])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(json.loads(fake.requests[1]["messages"][-1]["content"])["error"]["code"], "invalid_arguments")

    def test_python_mutation_fails_and_records_hash_change(self):
        result, fake = self.run_agent([completion([("run_python", {"code": "open('input.json', 'w').write('{}')"})])])
        self.assertEqual(result["failure"]["code"], "input_modified")
        self.assertEqual(result["input_integrity"]["changed_inputs"], ["input.json"])
        self.assertNotEqual(result["input_integrity"]["initial"]["input.json"], result["input_integrity"]["final"]["input.json"])
        self.assertEqual(len(fake.requests), 1)

    def test_formatted_result_limit_is_not_silently_truncated(self):
        (self.workspace / "large.txt").write_text("\t" * (MAX_OUTPUT_BYTES // 2))
        result, fake = self.run_agent([completion([("read_file", {"path": "large.txt"})])])
        self.assertEqual(result["failure"]["code"], "output_limit")
        self.assertTrue((self.logs / "tools/001.raw.json").is_file())
        self.assertFalse((self.logs / "tools/001.visible.txt").exists())
        self.assertEqual(len(fake.requests), 1)

    def test_gateway_response_redacts_echoed_credential_only_in_evidence(self):
        result, _ = self.run_agent([completion(content=self.config.api_key)])
        self.assertTrue(result["model_calls"][0]["response"]["credential_redacted"])
        self.assertNotIn(self.config.api_key, (self.logs / "model/001.response.json").read_text())

    def test_whole_attempt_deadline_before_final_answer(self):
        now = [0.0]
        fake = FakeGateway([completion([("write_answer", {"answer": {"answer": "late"}})])], advance=lambda: now.__setitem__(0, 181.0))
        result = Agent(self.config, self.workspace, self.logs, gateway=fake, clock=lambda: now[0]).run("request")
        self.assertEqual(result["failure"]["code"], "attempt_timeout")
        self.assertEqual(result["tool_calls"], 0)
        self.assertEqual(json.loads((self.workspace / "answer.json").read_text()), {"answer": "string"})

    def test_expired_pre_dispatch_deadline_does_not_count_a_model_call(self):
        ticks = iter([0.0, 0.0, 181.0])
        result, fake = self.run_agent([], clock=lambda: next(ticks, 181.0))
        self.assertEqual(result["failure"]["code"], "attempt_timeout")
        self.assertEqual(fake.requests, [])
        self.assertEqual(result["model_calls"], [])

    def test_gateway_response_can_exceed_tool_limit_without_truncation(self):
        body = completion([("write_answer", {"answer": {"answer": "ok"}})],
                          content="r" * (MAX_OUTPUT_BYTES + 1))
        result, _ = self.run_agent([body])
        self.assertEqual(result["status"], "completed")
        self.assertEqual((self.logs / "model/001.response.json").read_bytes(), body)
        limits = json.loads((self.logs / "run.json").read_text())["limits"]
        self.assertEqual(limits["output_bytes"], 64 * 1024)
        self.assertEqual(limits["gateway_response_bytes"], 2 * 1024 * 1024)

    def test_oversize_injected_gateway_response_fails_without_tool_execution(self):
        result, fake = self.run_agent([b"x" * (MAX_RESPONSE_BYTES + 1)])
        self.assertEqual(result["failure"]["code"], "output_limit")
        self.assertEqual(result["failure"]["source"], "gateway")
        self.assertFalse(result["failure"]["capture_complete"])
        self.assertEqual(len(fake.requests), 1)
        self.assertEqual(result["tool_calls"], 0)
        self.assertIsNone(result["model_calls"][0]["usage"])
        self.assertFalse((self.logs / "model/001.response.json").exists())

    def test_remaining_request_budget_is_bounded(self):
        now = [0.0]
        fake = FakeGateway([
            completion([("read_json", {"path": "input.json"})]),
            completion([("write_answer", {"answer": {"answer": "ok"}})]),
        ], advance=lambda: now.__setitem__(0, 150.0))
        result = Agent(self.config, self.workspace, self.logs, gateway=fake, clock=lambda: now[0]).run("request")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(fake.timeouts, [60, 30])

    def test_incomplete_response_usage_remains_observed(self):
        result, _ = self.run_agent([completion(usage={"completion_tokens": 4096}, finish="length")])
        self.assertEqual(result["failure"]["code"], "completion_incomplete")
        self.assertEqual(result["model_calls"][0]["usage"], {"completion_tokens": 4096})

    def test_duplicate_provider_keys_fail_with_raw_evidence(self):
        result, _ = self.run_agent([b'{"choices": [], "choices": []}'])
        self.assertEqual(result["failure"]["code"], "invalid_response")
        self.assertEqual((self.logs / "model/001.response.json").read_bytes(), b'{"choices": [], "choices": []}')

    def test_cli_supports_final_prompt_and_explicit_exact_prompt(self):
        exact = "  exact\nrequest  "
        self.assertEqual(parser().parse_args(["--condition", "full", exact]).prompt, exact)
        self.assertEqual(parser().parse_args(["--condition", "full", "--prompt", exact]).explicit_prompt, exact)
        self.assertEqual(parser().parse_args(["--condition", "compact", exact]).condition, "compact")
        with self.assertRaises(SystemExit), patch("sys.stderr"):
            parser().parse_args(["--condition", "preview", exact])

    def test_reserved_harness_runtime_is_not_public_or_frozen(self):
        runtime = self.workspace / ".rush"
        runtime.mkdir()
        (runtime / "python").symlink_to("/does/not/exist")
        result, fake = self.run_agent([
            completion([("read_file", {"path": ".rush/python"})]),
            completion([("write_answer", {"answer": {"answer": "ok"}})]),
        ])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(set(result["input_integrity"]["initial"]), {"input.json"})
        self.assertEqual(json.loads(fake.requests[1]["messages"][-1]["content"])["error"]["code"], "invalid_path")


if __name__ == "__main__":
    unittest.main()
