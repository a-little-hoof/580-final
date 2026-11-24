#!/usr/bin/env python3
"""Offline summaries of explicitly selected RUSH NanoAgent chat JSONL exports.

Uses reported turn metrics once. It never fills gaps from ATIF defaults, adds the
duplicate app-call ledger, or infers nested task usage from elapsed time.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path


METRICS = {
    "input_tokens": ("usage", "prompt_tokens"),
    "output_tokens": ("usage", "completion_tokens"),
    "cached_input_tokens": ("usage", "cached_tokens"),
    "total_tokens": ("usage", "total_tokens"),
    "reported_cost_usd": ("cost",),
    "latency_s": ("duration_s",),
    "reported_model_s": ("model_s",),
    "reported_tool_s": ("tools_s",),
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def lookup(value, path):
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def metric_sums(turns):
    result = {}
    for key in METRICS:
        values = [turn["reported_metrics"][key] for turn in turns]
        known = [value for value in values if value is not None]
        result[key] = {
            "known_subtotal": sum(known) if known else None,
            "known_turns": len(known),
            "missing_turns": len(values) - len(known),
        }
    return result


def summarize_tool(tool, index):
    raw = tool.get("output")
    text = raw if isinstance(raw, str) else None
    parsed = raw if isinstance(raw, dict) else None
    if text is not None:
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            pass
    verdict = parsed.get("verdict") if isinstance(parsed, dict) else None
    verdict = verdict if isinstance(verdict, dict) else None
    valid = verdict.get("valid") if verdict else None
    valid = valid if type(valid) is bool else None
    is_error = tool.get("isError")
    return {
        "tool_index": index,
        "name": tool.get("name"),
        "arguments": tool.get("arguments"),
        "is_error": is_error if type(is_error) is bool else None,
        "output_characters": len(text) if text is not None else None,
        "output_utf8_bytes": len(text.encode("utf-8")) if text is not None else None,
        "output_sha256": sha256(text.encode("utf-8")) if text is not None else None,
        "task_output": parsed.get("output") if isinstance(parsed, dict) else None,
        "verdict": verdict,
        "verified_success": valid if is_error is not True else None,
        "error_text": text if is_error is True else None,
    }


def summarize_turn(turn, index):
    prompt = turn.get("prompt")
    metrics = turn.get("metrics")
    messages = turn.get("messages") or {}
    agent = messages.get("agent") or {}
    metric_model = lookup(metrics, ("model",))
    model = metric_model if isinstance(metric_model, str) else agent.get("model_name")
    tools = [summarize_tool(tool, i) for i, tool in enumerate(turn.get("tools", []), 1)]
    nested = [
        {
            "task_name": item.get("name"),
            "recorded_tool_events": [
                {"name": event.get("name"), "is_error": event.get("isError")}
                for event in item.get("steps", [])
            ],
            "usage": None,
            "tool_output_lengths": None,
        }
        for item in turn.get("activity", []) if item.get("kind") == "task"
    ]
    known = [tool["verified_success"] for tool in tools if tool["verified_success"] is not None]
    if turn.get("error"):
        observation = "execution_error"
    elif not tools:
        observation = "no_task_invocation_recorded"
    elif False in known:
        observation = "failed_verifier_result_present"
    elif True in known:
        observation = "verified_result_present"
    elif any(tool["is_error"] is True for tool in tools):
        observation = "tool_error_without_verdict"
    else:
        observation = "task_invocation_without_boolean_verdict"
    return {
        "turn_index": index,
        "prompt": prompt,
        "prompt_sha256": sha256(prompt.encode("utf-8")) if isinstance(prompt, str) else None,
        "answer": turn.get("answer"),
        "plugin_version": turn.get("version"),
        "model": model,
        "model_source": "turn.metrics.model" if isinstance(metric_model, str) else "turn.messages.agent.model_name" if model else None,
        "agent_name": agent.get("name"),
        "agent_version": agent.get("version"),
        "observation": observation,
        "error": turn.get("error"),
        "reported_metrics": {name: number(lookup(metrics, path)) for name, path in METRICS.items()},
        "metric_source": "turn.metrics; token/cost fields exclude nested task calls in the audited chat implementation; timing scope varies by version",
        "task_invocations": tools,
        "nested_task_activity": nested,
        "nested_usage_inclusion": "excluded_from_reported_token_cost_fields_in_audited_implementation" if nested else "no_nested_task_activity_recorded",
        "atif_metrics_used": False,
    }


def summarize_chat(chat, source, line_number):
    if chat.get("type") != "chat" or chat.get("kind") != "nanoagent":
        raise ValueError(f"{source}:{line_number}: only type=chat, kind=nanoagent is supported")
    if not chat.get("session_id") or not isinstance(chat.get("turns"), list):
        raise ValueError(f"{source}:{line_number}: missing session_id or turns")
    turns = [summarize_turn(turn, i) for i, turn in enumerate(chat["turns"], 1)]
    ledger = chat.get("calls", [])
    return {
        "source_file": source,
        "source_line": line_number,
        "session_id": chat["session_id"],
        "plugin_id": lookup(chat, ("plugin", "id")),
        "created_at": chat.get("created_at"),
        "updated_at": chat.get("updated_at"),
        "turn_count": len(turns),
        "multi_turn_history": len(turns) > 1,
        "turns": turns,
        "reported_turn_metric_sums": metric_sums(turns),
        "exported_app_call_ledger": ledger,
        "ledger_added_to_turn_metrics": False,
    }


def summarize_files(paths, dataset_role):
    sources, sessions, seen = [], [], set()
    for path in paths:
        path = Path(path).resolve()
        raw = path.read_bytes()
        sources.append({"file": str(path), "sha256": sha256(raw), "bytes": len(raw)})
        for line_number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            if not line.strip():
                continue
            chat = summarize_chat(json.loads(line), str(path), line_number)
            if chat["session_id"] in seen:
                raise ValueError(f"Duplicate session {chat['session_id']}; select each session export only once")
            seen.add(chat["session_id"])
            sessions.append(chat)
    turns = [turn for session in sessions for turn in session["turns"]]
    tools = [tool for turn in turns for tool in turn["task_invocations"]]
    return {
        "schema_version": 1,
        "dataset_role": dataset_role,
        "sources": sources,
        "limitations": [
            "Historical descriptive sessions are not new matched pilots and must never be pooled with them.",
            "Multi-turn sessions share context and may contain user corrections, retries and different cases.",
            "Reported app-turn usage is counted once; the exported calls ledger and repeated ATIF history are not added.",
            "Reported token/cost totals exclude nested task model calls in the audited chat implementation; these are not full task totals. See docs/TRACE_ACCOUNTING.md.",
            "JSONL fields omit nested per-call usage and raw internal tool outputs; preserve each turn's separate graph.json to recover and verify fuller accounting.",
            "Missing metrics stay null, even if ATIF final_metrics has zeros. No model-call count is inferred from calls ledger length.",
            "Task success uses boolean verdict.valid, never score alone; no invocation or error without verdict is unknown correctness.",
            "Timing scope varies by runtime: current model time includes nested calls, while audited historical turns kept them under tool time. Do not add latency, model time and tool time.",
            "Cost in turn.metrics and cost_usd in the app-call ledger are distinct records; neither is asserted as actual provider spend.",
            "Reported output sizes measure only returned task-wrapper text, not the internal task's read/search output.",
        ],
        "counts": {
            "sessions": len(sessions), "turns": len(turns),
            "recorded_task_invocations": len(tools),
            "verified_true": sum(tool["verified_success"] is True for tool in tools),
            "verified_false": sum(tool["verified_success"] is False for tool in tools),
            "unknown_verdict": sum(tool["verified_success"] is None for tool in tools),
            "tool_errors": sum(tool["is_error"] is True for tool in tools),
            "turns_without_task_invocation": sum(not turn["task_invocations"] for turn in turns),
            "turn_execution_errors": sum(bool(turn["error"]) for turn in turns),
        },
        "reported_turn_metric_sums": metric_sums(turns),
        "sessions": sessions,
    }


def shown(value):
    if value is None:
        return "unknown"
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown(summary):
    c = summary["counts"]
    lines = [
        f"# {summary['dataset_role'].replace('_', ' ').title()} trace summary", "",
        f"{c['sessions']} sessions; {c['turns']} turns; {c['recorded_task_invocations']} recorded task invocations. "
        f"Task-call verdicts: {c['verified_true']} valid, {c['verified_false']} invalid, {c['unknown_verdict']} unknown. "
        f"{c['tool_errors']} tool errors; {c['turns_without_task_invocation']} turns with no task invocation; "
        f"{c['turn_execution_errors']} turn execution errors.", "",
        "These are descriptive counts, not a matched-experiment success rate. Token values cover the outer chat loop in the audited implementation and exclude nested task model calls.", "",
        "| Plugin | Model | Turn | Observation | Input | Cached input | Output | Latency (s) | Wrapper output bytes |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for session in summary["sessions"]:
        for turn in session["turns"]:
            m = turn["reported_metrics"]
            sizes = [tool["output_utf8_bytes"] for tool in turn["task_invocations"]]
            size = ", ".join(shown(value) for value in sizes) if sizes else "none recorded"
            values = [session["plugin_id"], turn["model"] or "unknown", turn["turn_index"], turn["observation"], shown(m["input_tokens"]),
                      shown(m["cached_input_tokens"]), shown(m["output_tokens"]), shown(m["latency_s"]), size]
            lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    lines += ["", "## Sessions and exact prompts", ""]
    for session in summary["sessions"]:
        lines += [f"### {session['plugin_id']}: `{session['session_id']}`", "",
                  f"Created `{session['created_at']}`; source line {session['source_line']} of `{session['source_file']}`.", ""]
        for turn in session["turns"]:
            lines.append(f"{turn['turn_index']}. {turn['prompt']}")
            if turn["error"]:
                lines.append(f"   - Recorded error: {turn['error']}")
        lines.append("")
    lines += ["## Limits", ""] + [f"- {item}" for item in summary["limitations"]]
    lines += ["", "The accompanying JSON preserves exact prompts and hashes, model sources, each verifier result, failure text, metrics, input-file hashes and the uncombined app-call ledger.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-role", required=True, choices=["current_pilot", "historical_descriptive"])
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--markdown-out", type=Path, required=True)
    parser.add_argument("files", nargs="+", type=Path, help="Explicit JSONL export files; no discovery or network access")
    args = parser.parse_args()
    outputs = [args.json_out.resolve(), args.markdown_out.resolve()]
    if len(set(outputs)) != 2 or set(outputs) & {path.resolve() for path in args.files}:
        parser.error("Output paths must be distinct and must not overwrite an input export")
    summary = summarize_files(args.files, args.dataset_role)
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    outputs[0].write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    outputs[1].write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"dataset_role": args.dataset_role, **summary["counts"]}))


if __name__ == "__main__":
    main()
