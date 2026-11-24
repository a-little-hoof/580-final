"""Original serial agent loop; all correctness judgments remain external."""

import time
from pathlib import Path

from . import __version__
from .common import (AgentError, ATTEMPT_SECONDS, MAX_MODEL_CALLS, MAX_OUTPUT_BYTES, MAX_RESPONSE_BYTES,
                     REQUEST_SECONDS, TOOL_SECONDS, json_text, sha256, strict_json, time_limit)
from .gateway import Gateway
from .common import package_fingerprint
from .telemetry import Telemetry
from .tools import TOOL_SCHEMAS, WorkspaceTools, format_tool_result

SYSTEM_PROMPT = """You are solving a task in a public workspace. Follow the user's exact request using the available generic tools as needed. Public task data is in input.json; other public files may also be read. If answer.json contains an output schema, use that shape. Do not change input files. Use write_answer to write the final answer object, then stop. Do not claim success based on a hidden verifier: correctness is checked separately. Python is available for computation with the standard library, and is not a host filesystem sandbox. Work efficiently within 12 model calls, 10 seconds per tool, and 180 seconds for the attempt. Full tool results are bounded at 64 KiB; exceeding that limit fails the attempt without truncation."""


class Agent:
    def __init__(self, config, workspace, log_dir, *, gateway=None, clock=time.monotonic):
        self.config = config
        self.workspace = Path(workspace).resolve()
        self.log_dir = Path(log_dir).resolve()
        if self.log_dir == self.workspace or self.log_dir in self.workspace.parents:
            raise AgentError("log_directory", "Log directory must not contain the public workspace", fatal=True)
        self.gateway = gateway or Gateway(config)
        self.clock = clock

    def run(self, prompt, *, condition="full"):
        if condition not in {"full", "compact"}:
            raise AgentError("unsupported_condition", "Condition must be full or compact", fatal=True)
        if not isinstance(prompt, str) or not prompt:
            raise AgentError("prompt", "A nonempty exact prompt is required", fatal=True)
        started = self.clock()
        deadline = started + ATTEMPT_SECONDS
        evidence = Telemetry(self.log_dir, secrets=(self.config.api_key,))
        tools = None
        calls, tool_count = [], 0
        status, failure, answer_info = "failed", None, None
        input_check = None
        evidence.save_text("prompt.txt", prompt)
        evidence.save_json("run.json", {
            "schema_version": 1, "agent_version": __version__, "condition": condition,
            **package_fingerprint(),
            "configured_model": self.config.model, "temperature": 0,
            "max_output_tokens": self.config.max_output_tokens,
            "limits": {"model_calls": MAX_MODEL_CALLS, "tool_seconds": TOOL_SECONDS,
                       "attempt_seconds": ATTEMPT_SECONDS, "output_bytes": MAX_OUTPUT_BYTES,
                       "gateway_response_bytes": MAX_RESPONSE_BYTES},
            "tool_output_serialization": (
                "json.dumps(ensure_ascii=False, indent=2, allow_nan=False)" if condition == "full" else
                "json.dumps(ensure_ascii=False, separators=(',', ':'), allow_nan=False)"),
            "python_is_host_filesystem_sandbox": False, "network_retries": 0,
            "success_scope": "completed answer artifact; task correctness is external"})

        def remaining():
            value = deadline - self.clock()
            if value <= 0:
                raise AgentError("attempt_timeout", "Attempt exceeded its time limit", fatal=True)
            return value

        def integrity():
            nonlocal input_check
            with time_limit(remaining(), "attempt_timeout"):
                input_check = tools.check_inputs()
            if input_check["changed_inputs"]:
                raise AgentError("input_modified", "Public input files changed during the attempt", fatal=True,
                                 details={"changed_inputs": input_check["changed_inputs"]})

        try:
            with time_limit(remaining(), "attempt_timeout"):
                tools = WorkspaceTools(self.workspace, self.log_dir)
                evidence.save_json("inputs.initial.json", tools.inputs)
            messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
            for call_index in range(1, MAX_MODEL_CALLS + 1):
                request = {"model": self.config.model, "messages": messages, "tools": TOOL_SCHEMAS,
                           "temperature": 0, "max_tokens": self.config.max_output_tokens, "stream": False}
                request_ref = evidence.save_json(f"model/{call_index:03d}.request.json", request)
                call_start = self.clock()
                timeout = min(REQUEST_SECONDS, remaining())
                call = {"index": call_index, "request": request_ref, "resolved_model": None,
                        "usage": None, "status": "failed"}
                calls.append(call)
                try:
                    with time_limit(timeout, "attempt_timeout" if timeout < REQUEST_SECONDS else "request_timeout"):
                        body = self.gateway.complete(request, timeout=timeout)
                    if not isinstance(body, bytes):
                        raise AgentError("invalid_response", "Transport must return raw response bytes", fatal=True)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise AgentError("output_limit", "Gateway response exceeded 2 MiB; no truncated response was used",
                                         fatal=True, details={"source": "gateway", "capture_complete": False})
                    try:
                        text = body.decode("utf-8")
                    except UnicodeDecodeError:
                        raise AgentError("invalid_response", "Gateway response is not UTF-8", fatal=True) from None
                    call["response"] = evidence.save_text(f"model/{call_index:03d}.response.json", text)
                    try:
                        response = strict_json(text)
                    except ValueError:
                        raise AgentError("invalid_response", "Gateway response is not strict JSON", fatal=True) from None
                    if isinstance(response, dict):
                        call["resolved_model"] = response.get("model") if isinstance(response.get("model"), str) else None
                        call["usage"] = response.get("usage") if isinstance(response.get("usage"), dict) else None
                    assistant, tool_calls = self.parse_response(response)
                    call["status"] = "completed"
                except AgentError as error:
                    call["error"] = {"code": error.code, **error.details}
                    raise
                finally:
                    call["elapsed_seconds"] = self.clock() - call_start
                    evidence.event({"kind": "model_call", **call})
                remaining()
                messages.append(assistant)
                if not tool_calls:
                    if not tools.answer_written:
                        raise AgentError("answer_missing", "Model stopped before calling write_answer", fatal=True)
                    break
                for tool_call in tool_calls:
                    tool_count += 1
                    tool_start = self.clock()
                    event = {"kind": "tool_call", "index": tool_count, "model_call": call_index,
                             "tool_call_id": tool_call["id"], "name": tool_call["function"]["name"]}
                    tool_error = None
                    try:
                        try:
                            arguments = strict_json(tool_call["function"]["arguments"])
                        except ValueError:
                            raise AgentError("invalid_arguments", "Tool arguments must be strict JSON") from None
                        timeout = min(TOOL_SECONDS, remaining())
                        with time_limit(timeout, "attempt_timeout" if timeout < TOOL_SECONDS else "tool_timeout"):
                            raw = tools.execute(event["name"], arguments, timeout=timeout)
                    except AgentError as error:
                        tool_error = error
                        raw = {"error": {"code": error.code, "message": str(error), **error.details}}
                    except (OSError, ValueError, TypeError):
                        tool_error = AgentError("tool_error", "Tool operation failed")
                        raw = {"error": {"code": tool_error.code, "message": str(tool_error)}}
                    event["elapsed_seconds"] = self.clock() - tool_start
                    event["status"] = "failed" if tool_error else "completed"
                    event["raw_payload_kind"] = "error_metadata" if tool_error else "tool_result"
                    event["raw_result_complete"] = tool_error is None
                    # The same full-form limit must apply to every future condition.
                    raw_text = json_text(raw)
                    event["raw"] = evidence.save_text(f"tools/{tool_count:03d}.raw.json", raw_text)
                    try:
                        if len(raw_text.encode("utf-8")) > MAX_OUTPUT_BYTES:
                            raise AgentError("output_limit", "Full tool result exceeded 64 KiB; no truncated output was delivered", fatal=True)
                        if tool_error and tool_error.fatal:
                            raise tool_error
                        visible = format_tool_result(raw, condition)
                        event["visible"] = evidence.save_text(f"tools/{tool_count:03d}.visible.txt", visible)
                        messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": visible})
                        integrity()
                    except AgentError as error:
                        event["status"] = "failed"
                        event["error"] = {"code": error.code, **error.details}
                        raise
                    finally:
                        evidence.event(event)
                if tools.answer_written:
                    break
            if not tools.answer_written:
                raise AgentError("model_call_limit", "Model call limit reached without an answer", fatal=True)
            with time_limit(remaining(), "attempt_timeout"):
                answer_path = tools.resolve("answer.json")
                answer_text = tools.read_text("answer.json")
                if not isinstance(strict_json(answer_text), dict):
                    raise AgentError("answer_invalid", "answer.json must contain a strict JSON object", fatal=True)
                answer_bytes = answer_path.read_bytes()
                answer_info = {"path": "answer.json", "bytes": len(answer_bytes), "sha256": sha256(answer_bytes)}
                integrity()
                remaining()
            status = "completed"
        except AgentError as error:
            failure = {"code": error.code, "message": str(error), **error.details}
        except (OSError, ValueError, TypeError):
            failure = {"code": "local_error", "message": "Local operation failed; no retry was attempted"}
        finally:
            if tools is not None:
                # Preserve an after-hash even for failures; bounded separately so audit cannot hang.
                try:
                    with time_limit(TOOL_SECONDS, "integrity_timeout"):
                        input_check = tools.check_inputs()
                except (AgentError, OSError):
                    input_check = {"initial": tools.inputs, "final": None, "changed_inputs": None,
                                   "verification_error": "Final input integrity could not be measured"}
                if input_check.get("changed_inputs"):
                    status = "failed"
                    failure = {"code": "input_modified", "message": "Public input files changed during the attempt",
                               "changed_inputs": input_check["changed_inputs"], "prior_failure": failure}
                elif input_check.get("verification_error") and status == "completed":
                    status = "failed"
                    failure = {"code": "integrity_unknown", "message": input_check["verification_error"]}
                evidence.save_json("inputs.final.json", input_check)
            if self.clock() >= deadline and status == "completed":
                status = "failed"
                failure = {"code": "attempt_timeout", "message": "Attempt exceeded its time limit before final evidence verification"}
            result = {"schema_version": 1, "status": status, "failure": failure, "condition": condition,
                      "model_calls": calls, "tool_calls": tool_count, "answer": answer_info,
                      "elapsed_seconds": self.clock() - started, "input_integrity": input_check,
                      "usage_scope": "raw per-call provider usage; missing values remain null; no cost estimate",
                      "task_correctness": "not evaluated by this agent"}
            evidence.save_json("result.json", result)
        return result

    @staticmethod
    def parse_response(response):
        if not isinstance(response, dict) or not isinstance(response.get("choices"), list) or len(response["choices"]) != 1:
            raise AgentError("invalid_response", "Expected exactly one completion choice", fatal=True)
        choice = response["choices"][0]
        if not isinstance(choice, dict) or choice.get("finish_reason") not in {"stop", "tool_calls"}:
            raise AgentError("completion_incomplete", "Completion did not finish normally", fatal=True)
        message = choice.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise AgentError("invalid_response", "Expected an assistant message", fatal=True)
        if message.get("content") is not None and not isinstance(message.get("content"), str):
            raise AgentError("invalid_response", "Assistant content must be text or null", fatal=True)
        assistant = {"role": "assistant", "content": message.get("content")}
        if isinstance(message.get("reasoning_content"), str):
            assistant["reasoning_content"] = message["reasoning_content"]
        tool_calls = message.get("tool_calls") or []
        if not isinstance(tool_calls, list):
            raise AgentError("invalid_response", "Tool calls must be a list", fatal=True)
        ids = set()
        for call in tool_calls:
            if (not isinstance(call, dict) or not isinstance(call.get("id"), str) or not call["id"]
                    or call["id"] in ids or call.get("type") != "function" or not isinstance(call.get("function"), dict)
                    or not isinstance(call["function"].get("name"), str)
                    or not isinstance(call["function"].get("arguments"), str)):
                raise AgentError("invalid_response", "Invalid or duplicate function call", fatal=True)
            ids.add(call["id"])
        if tool_calls:
            assistant["tool_calls"] = tool_calls
        return assistant, tool_calls
