import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from comp580_agent.common import AgentError, strict_json
from comp580_agent.tools import WorkspaceTools, format_tool_result


class ToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name) / "public"
        self.workspace.mkdir()
        self.logs = Path(self.temporary.name) / "logs"
        (self.workspace / "input.json").write_text('{"value": 17}')
        self.tools = WorkspaceTools(self.workspace, self.logs)

    def test_strict_json_rejects_lossy_duplicates_and_nonfinite_numbers(self):
        for text in ('{"x": 1, "x": 2}', '[NaN]', '[Infinity]', '[1e999]', '{"a":{"x":1,"x":2}}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                strict_json(text)
        self.assertEqual(strict_json('[1e-3, 9223372036854775808]'), [.001, 9223372036854775808])

    def test_python_has_cwd_public_data_and_no_inherited_credentials(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret", "UNRELATED_SECRET": "also-secret"}):
            result = self.tools.execute("run_python", {"code": "import json, os; print(json.load(open('input.json'))['value']); print('OPENAI_API_KEY' in os.environ); print('UNRELATED_SECRET' in os.environ)"})
        self.assertEqual(result, {"stdout": "17\nFalse\nFalse\n", "stderr": "", "exit_code": 0})

    def test_stdout_and_stderr_whitespace_roundtrip(self):
        result = self.tools.execute("run_python", {"code": "import sys; sys.stdout.write('  雪\\n\\n'); sys.stderr.write('\\t warning  ')"})
        self.assertEqual(result["stdout"], "  雪\n\n")
        self.assertEqual(result["stderr"], "\t warning  ")
        self.assertEqual(json.loads(format_tool_result(result, "full")), result)

    def test_python_timeout_and_overflow_fail_explicitly(self):
        started = time.monotonic()
        with self.assertRaises(AgentError) as caught:
            self.tools.execute("run_python", {"code": "import time; time.sleep(60)"}, timeout=.1)
        self.assertEqual(caught.exception.code, "tool_timeout")
        self.assertLess(time.monotonic() - started, 3)
        with self.assertRaises(AgentError) as caught:
            self.tools.execute("run_python", {"code": "print('x'*70000)"})
        self.assertEqual(caught.exception.code, "output_limit")
        self.assertFalse(caught.exception.details["capture_complete"])

    def test_paths_reject_escape_symlinks_and_telemetry(self):
        (self.workspace / "link").symlink_to(self.workspace / "input.json")
        for path in ("../input.json", "/etc/passwd", "link", ".comp580_logs/run/events.jsonl", ".rush/config"):
            with self.subTest(path=path), self.assertRaises(AgentError) as caught:
                self.tools.execute("read_file", {"path": path})
            self.assertEqual(caught.exception.code, "invalid_path")

    def test_read_json_returns_all_values_and_search_is_literal(self):
        self.assertEqual(self.tools.execute("read_json", {"path": "input.json"}), {"path": "input.json", "data": {"value": 17}})
        (self.workspace / "lines.txt").write_text("a.b\naxb\na.b tail\n")
        result = self.tools.execute("search_file", {"path": "lines.txt", "literal": "a.b"})
        self.assertEqual(result["matches"], [{"line": 1, "text": "a.b\n"}, {"line": 3, "text": "a.b tail\n"}])

    def test_answer_requires_object_and_serializable_finite_values(self):
        with self.assertRaises(AgentError):
            self.tools.execute("write_answer", {"answer": [1]})
        with self.assertRaises(ValueError):
            self.tools.execute("write_answer", {"answer": {"x": float("nan")}})
        self.assertFalse((self.workspace / "answer.json").exists())

    def test_deleted_or_symlink_replaced_input_is_changed(self):
        (self.workspace / "input.json").unlink()
        (self.workspace / "input.json").symlink_to("/etc/hosts")
        self.assertEqual(self.tools.check_inputs()["changed_inputs"], ["input.json"])


if __name__ == "__main__":
    unittest.main()
