"""Generic public-workspace tools. Python execution is NOT an OS sandbox."""

import os
import json
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from .common import AgentError, MAX_OUTPUT_BYTES, TOOL_SECONDS, json_text, sha256, strict_json


def format_tool_result(data, condition):
    """Change JSON presentation only; preserve keys, values and string whitespace.

    The agent checks the common full-form byte limit before this function. Tool
    execution, error handling and history are identical for both conditions.
    """
    if condition == "full":
        return json_text(data)
    if condition == "compact":
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    raise AgentError("unsupported_condition", "Condition must be full or compact", fatal=True)


def _schema(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": required, "additionalProperties": False}}}


TOOL_SCHEMAS = [
    _schema("read_json", "Read an entire public JSON file as a structured object, without solving the task.",
            {"path": {"type": "string"}}, ["path"]),
    _schema("read_file", "Read the full UTF-8 text of a public workspace file.",
            {"path": {"type": "string"}}, ["path"]),
    _schema("search_file", "Find a literal string in a public UTF-8 file; return every matching line with its line number.",
            {"path": {"type": "string"}, "literal": {"type": "string"}}, ["path", "literal"]),
    _schema("run_python", "Run Python code in the public workspace using only stdlib. Credentials are removed from its environment. This is not a host filesystem sandbox. Output is bounded; do not alter input files.",
            {"code": {"type": "string"}}, ["code"]),
    _schema("write_answer", "Write the final task answer object to answer.json. This ends the attempt after the current tool calls finish.",
            {"answer": {"type": "object"}}, ["answer"]),
]


class WorkspaceTools:
    def __init__(self, workspace, log_dir, *, max_bytes=MAX_OUTPUT_BYTES):
        self.workspace = Path(workspace).resolve()
        self.log_dir = Path(log_dir).resolve()
        self.max_bytes = max_bytes
        if not self.workspace.is_dir():
            raise AgentError("workspace_missing", "Workspace must be an existing directory", fatal=True)
        self.inputs = self.snapshot()
        self.answer_written = False

    def _reserved(self, path):
        return (path == self.log_dir or self.log_dir in path.parents
                or bool({".rush", ".comp580_logs"} & set(path.relative_to(self.workspace).parts)))

    def resolve(self, name, *, must_exist=True):
        if not isinstance(name, str) or not name or Path(name).is_absolute():
            raise AgentError("invalid_path", "Use a nonempty relative workspace path")
        relative = Path(name)
        if ".." in relative.parts:
            raise AgentError("invalid_path", "Parent traversal is not allowed")
        path = self.workspace / relative
        for part in (path, *path.parents):
            if part == self.workspace:
                break
            if part.is_symlink():
                raise AgentError("invalid_path", "Symlinks are not allowed")
        path = path.resolve()
        if self.workspace not in path.parents or self._reserved(path):
            raise AgentError("invalid_path", "Path must be a public workspace file")
        if must_exist and not path.exists():
            raise AgentError("file_missing", "The requested workspace file does not exist")
        if path.exists() and not stat.S_ISREG(path.stat().st_mode):
            raise AgentError("invalid_path", "Only regular files are supported")
        return path

    def snapshot(self):
        result = {}
        for folder, dirs, files in os.walk(self.workspace, followlinks=False):
            base = Path(folder)
            dirs[:] = [d for d in dirs if not self._reserved(base / d)]
            for name in dirs + files:
                path = base / name
                if path.is_symlink():
                    raise AgentError("input_symlink", "Workspace inputs must not contain symlinks", fatal=True)
            for name in files:
                path = base / name
                if path == self.workspace / "answer.json" or self._reserved(path):
                    continue
                if not stat.S_ISREG(path.stat().st_mode):
                    raise AgentError("input_type", "Workspace inputs must be regular files", fatal=True)
                import hashlib
                digest = hashlib.sha256()
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(65536), b""):
                        digest.update(chunk)
                result[str(path.relative_to(self.workspace))] = {"sha256": digest.hexdigest(), "bytes": path.stat().st_size}
        return result

    def check_inputs(self):
        current, changed = {}, []
        for name, before in self.inputs.items():
            try:
                path = self.resolve(name)
                import hashlib
                digest = hashlib.sha256()
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(65536), b""):
                        digest.update(chunk)
                after = {"sha256": digest.hexdigest(), "bytes": path.stat().st_size}
            except (AgentError, OSError):
                after = None
            current[name] = after
            if after != before:
                changed.append(name)
        return {"initial": self.inputs, "final": current, "changed_inputs": changed,
                "new_files_are_not_frozen_inputs": True}

    def read_text(self, name):
        path = self.resolve(name)
        if path.stat().st_size > self.max_bytes:
            raise AgentError("output_limit", "Input exceeds the full-output byte limit; nothing was truncated",
                             fatal=True, details={"source_bytes": path.stat().st_size})
        data = path.read_bytes()
        if len(data) > self.max_bytes:
            raise AgentError("output_limit", "Input exceeded the full-output byte limit", fatal=True)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise AgentError("invalid_utf8", "Tool input must be UTF-8 text") from error

    def execute(self, name, arguments, *, timeout=TOOL_SECONDS):
        expected = {"read_json": {"path"}, "read_file": {"path"}, "search_file": {"path", "literal"},
                    "run_python": {"code"}, "write_answer": {"answer"}}
        if name not in expected:
            raise AgentError("unknown_tool", "Unknown tool name")
        if not isinstance(arguments, dict) or set(arguments) != expected[name]:
            raise AgentError("invalid_arguments", "Tool arguments must match the declared schema exactly")
        for key in expected[name] - {"answer"}:
            if not isinstance(arguments[key], str):
                raise AgentError("invalid_arguments", f"{key} must be a string")
        if name == "read_json":
            try:
                data = strict_json(self.read_text(arguments["path"]))
            except ValueError as error:
                raise AgentError("invalid_json", "The file is not strict JSON") from error
            return {"path": arguments["path"], "data": data}
        if name == "read_file":
            return {"path": arguments["path"], "text": self.read_text(arguments["path"])}
        if name == "search_file":
            if not arguments["literal"]:
                raise AgentError("invalid_arguments", "The search literal must not be empty")
            text = self.read_text(arguments["path"])
            matches = [{"line": index, "text": line} for index, line in enumerate(text.splitlines(keepends=True), 1)
                       if arguments["literal"] in line]
            return {"path": arguments["path"], "literal": arguments["literal"], "matches": matches}
        if name == "run_python":
            return self.run_python(arguments["code"], timeout)
        answer = arguments["answer"]
        if not isinstance(answer, dict):
            raise AgentError("invalid_arguments", "The final answer must be a JSON object")
        text = json_text(answer)
        if len(text.encode("utf-8")) > self.max_bytes:
            raise AgentError("output_limit", "Answer exceeds the byte limit", fatal=True)
        path = self.resolve("answer.json", must_exist=False)
        temporary = path.with_name(f".answer-{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                handle.write(text)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        self.answer_written = True
        return {"path": "answer.json", "bytes": len(text.encode("utf-8")), "sha256": sha256(text.encode("utf-8"))}

    def run_python(self, code, timeout):
        if len(code.encode("utf-8")) > self.max_bytes:
            raise AgentError("output_limit", "Python source exceeds the byte limit", fatal=True)
        with tempfile.TemporaryDirectory(prefix="comp580-python-") as home:
            # An allowlist prevents gateway/provider credentials and inherited config paths.
            env = {"PATH": os.defpath, "HOME": home, "TMPDIR": home, "LANG": "C.UTF-8"}
            proc = subprocess.Popen([sys.executable, "-I", "-S", "-X", "utf8", "-c", code],
                                    cwd=self.workspace, env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            buffers = {"stdout": bytearray(), "stderr": bytearray()}
            end = time.monotonic() + timeout
            try:
                with selectors.DefaultSelector() as selector:
                    for stream, label in ((proc.stdout, "stdout"), (proc.stderr, "stderr")):
                        os.set_blocking(stream.fileno(), False)
                        selector.register(stream, selectors.EVENT_READ, label)
                    while selector.get_map():
                        remaining = end - time.monotonic()
                        if remaining <= 0:
                            raise AgentError("tool_timeout", "Python tool exceeded its time limit", fatal=True)
                        for key, _event in selector.select(min(remaining, .1)):
                            chunk = os.read(key.fileobj.fileno(), 4096)
                            if not chunk:
                                selector.unregister(key.fileobj)
                                continue
                            buffers[key.data].extend(chunk)
                            total = sum(len(v) for v in buffers.values())
                            if total > self.max_bytes:
                                raise AgentError("output_limit", "Python output exceeded the byte limit; no truncated output was delivered",
                                                 fatal=True, details={"observed_bytes": total, "capture_complete": False})
                    try:
                        returncode = proc.wait(timeout=max(.001, end - time.monotonic()))
                    except subprocess.TimeoutExpired as error:
                        raise AgentError("tool_timeout", "Python tool exceeded its time limit", fatal=True) from error
                try:
                    return {"stdout": bytes(buffers["stdout"]).decode("utf-8"),
                            "stderr": bytes(buffers["stderr"]).decode("utf-8"), "exit_code": returncode}
                except UnicodeDecodeError as error:
                    raise AgentError("invalid_utf8", "Python output was not UTF-8") from error
            finally:
                # Also stop descendants that keep pipes open after their parent exits.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
                proc.stdout.close()
                proc.stderr.close()
