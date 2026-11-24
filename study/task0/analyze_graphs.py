#!/usr/bin/env python3
"""Offline accounting of captured RUSH plugin-chat provenance graphs.

Counts each observed node.modelCalls entry once. This supports the audited chat
graph topology, not arbitrary DAGs or provider billing reconstruction.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path


TOKEN_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens",
                "cache_write_tokens", "cache_write_1h_tokens", "reasoning_tokens")
MODEL_NODES = {"agent_reply", "decision"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value, integer=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        return None
    if integer and type(value) is not int:
        return None
    return value


def measured_sum(values):
    known = [value for value in values if value is not None]
    return {"known_subtotal": sum(known) if known or not values else None,
            "known_calls": len(known), "missing_calls": len(values) - len(known)}


def call_status(call):
    if call.get("error") or call.get("failed") is True:
        return "failed"
    if "error" in call or call.get("failed") is False:
        return "completed"
    return "unknown"


def aggregate(calls):
    return {
        "call_records": len(calls),
        "completed_records": sum(call_status(c) == "completed" for c in calls),
        "failed_records": sum(call_status(c) == "failed" for c in calls),
        "unknown_status_records": sum(call_status(c) == "unknown" for c in calls),
        "usage": {key: measured_sum([number((c.get("usage") or {}).get(key), True) for c in calls])
                  for key in TOKEN_FIELDS},
        "reported_cost_usd": measured_sum([number(c.get("cost")) for c in calls]),
        "model_call_seconds": measured_sum([number(c.get("duration_s")) for c in calls]),
    }


def nested_tool_sizes(graph, by_id):
    """Measure stored raw text only; parsed JSON does not preserve wire bytes."""
    results = []
    for node in graph["nodes"]:
        if node.get("type") != "tool" or not node.get("parent") or node.get("label") == "submit":
            continue
        outputs = [by_id[e["to"]] for e in graph.get("edges", [])
                   if e.get("from") == node["id"] and e.get("relation") == "generated"
                   and e.get("to") in by_id and by_id[e["to"]].get("type") == "tool_result"]
        if not outputs:
            results.append({"tool_node": node["id"], "tool_name": node.get("label"),
                            "is_error": node.get("isError"), "result_node": None,
                            "raw_utf8_bytes": None, "representation": "missing_result"})
        for output in outputs:
            value = output.get("value")
            text = isinstance(value, str)
            results.append({"tool_node": node["id"], "tool_name": node.get("label"),
                            "is_error": node.get("isError"), "result_node": output["id"],
                            "raw_utf8_bytes": len(value.encode("utf-8")) if text else None,
                            "raw_text_characters": len(value) if text else None,
                            "representation": "raw_text" if text else "structured_value_wire_bytes_unknown"})
    known = [r["raw_utf8_bytes"] for r in results if r["raw_utf8_bytes"] is not None]
    return {"records": results, "known_text_results": len(known),
            "missing_raw_text_results": len(results) - len(known),
            "known_total_utf8_bytes": sum(known) if known or not results else None,
            "known_max_utf8_bytes": max(known) if known else None,
            "scope": "nested tool nodes excluding submit, reference and outer task output; exact stored text bytes only"}


def analyze_graph(graph):
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("Graph must contain a nodes list")
    by_id = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            raise ValueError("Each graph node needs a string id")
        if node["id"] in by_id:
            raise ValueError(f"Duplicate graph node: {node['id']}")
        by_id[node["id"]] = node
    groups = {"outer": [], "nested": []}
    unmeasured = []
    record_locations = []
    for node in nodes:
        parents, seen = [], {node["id"]}
        parent = node.get("parent")
        while parent is not None:
            if parent in seen or parent not in by_id:
                raise ValueError(f"Cyclic or missing parent at {node['id']}")
            seen.add(parent)
            parents.append(by_id[parent])
            parent = by_id[parent].get("parent")
        if node.get("type") not in MODEL_NODES:
            if "modelCalls" in node:
                raise ValueError(f"Unsupported modelCalls owner: {node['id']}")
            continue
        if parents and not any(p.get("type") == "task" for p in parents):
            raise ValueError(f"Model node has no task ancestor: {node['id']}")
        if not parents and node.get("type") != "agent_reply":
            raise ValueError("Only chat agent_reply nodes may be outer model nodes")
        scope = "nested" if parents else "outer"
        calls = node.get("modelCalls")
        if calls is None or calls == []:
            unmeasured.append({"node_id": node["id"], "scope": scope,
                               "reason": "absent_or_empty_modelCalls"})
            continue
        if not isinstance(calls, list):
            raise ValueError("modelCalls must be a list")
        for index, call in enumerate(calls):
            if not isinstance(call, dict):
                raise ValueError("Model call record must be an object")
            # Audited graph construction removes these inclusive profile copies.
            # Without stable call IDs we cannot safely deduplicate another topology.
            if call.get("kind") == "tool":
                raise ValueError("Unsupported aggregate kind=tool record; possible duplicate nested call")
            if call.get("usage") is not None and not isinstance(call["usage"], dict):
                raise ValueError("Call usage must be an object or null")
            groups[scope].append(call)
            record_locations.append({"node_id": node["id"], "record_index": index,
                                     "scope": scope, "status": call_status(call)})
    combined = groups["outer"] + groups["nested"]
    totals = {name: aggregate(calls) for name, calls in {**groups, "all": combined}.items()}
    return {"topology": "audited_chat_graph_with_task_ancestors",
            "totals": totals, "record_locations": record_locations,
            "unmeasured_model_nodes": unmeasured,
            "nested_data_tool_results": nested_tool_sizes(graph, by_id),
            "coverage": "recorded_calls_only; omitted failed attempts or provider calls cannot be ruled out"}


def compare_value(value, metric):
    value = number(value)
    measured = metric["known_subtotal"]
    equal = None
    if value is not None and measured is not None and metric["missing_calls"] == 0:
        equal = math.isclose(value, measured, rel_tol=1e-9, abs_tol=1e-12)
    return {"observed": value, "graph_known_subtotal": measured,
            "missing_graph_calls": metric["missing_calls"], "equal": equal}


def compare_export(metrics, totals):
    metrics = metrics or {}
    usage = metrics.get("usage") or {}
    return {scope: {
        "usage": {key: compare_value(usage.get(key), values["usage"][key]) for key in TOKEN_FIELDS},
        "cost": compare_value(metrics.get("cost"), values["reported_cost_usd"]),
    } for scope, values in totals.items()}


def load_export(path, session):
    found = [row for row in (json.loads(line) for line in path.read_text().splitlines() if line.strip())
             if row.get("type") == "chat" and row.get("session_id") == session]
    if len(found) != 1:
        raise ValueError(f"Expected one export session {session}; found {len(found)}")
    return found[0]


def verify_capture(path, provenance, project_root):
    entries = [entry for entry in provenance.get("synced_files", [])
               if (project_root / entry["copy"]).resolve() == path.resolve()]
    if len(entries) != 1 or not entries[0].get("sha256"):
        raise ValueError(f"Missing or ambiguous captured-file hash: {path}")
    if digest(path) != entries[0]["sha256"]:
        raise ValueError(f"Captured-file hash changed: {path}")


def task_invocations(turn):
    results = []
    for tool in turn.get("tools", []):
        value = tool.get("output")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = None
        verdict = value.get("verdict") if isinstance(value, dict) else None
        valid = verdict.get("valid") if isinstance(verdict, dict) else None
        results.append({"task": tool.get("name"), "arguments": tool.get("arguments"),
                        "is_error": tool.get("isError"),
                        "valid": valid if type(valid) is bool and not tool.get("isError") else None,
                        "score": verdict.get("score") if isinstance(verdict, dict) else None})
    return results


def analyze_evidence(folder, project_root):
    chat_path = folder / "chat.json"
    provenance = json.loads((folder / "provenance.json").read_text())
    verify_capture(chat_path, provenance, project_root)
    chat = json.loads(chat_path.read_text())
    if chat.get("session") != folder.name:
        raise ValueError("Evidence directory does not match chat.session")
    export_path = project_root / provenance["export"]["path"]
    if digest(export_path) != provenance["export"]["sha256"]:
        raise ValueError(f"Export hash changed: {export_path}")
    exported = load_export(export_path, chat["session"])
    if len(chat["turns"]) != len(exported["turns"]):
        raise ValueError("Local/export turn counts differ")
    ui_path = folder / "ui_observation.json"
    ui = json.loads(ui_path.read_text()) if ui_path.exists() else None
    for entry in provenance.get("ui_evidence", {}).values():
        path = project_root / entry["path"]
        if digest(path) != entry["sha256"]:
            raise ValueError(f"UI evidence hash changed: {path}")
    results = []
    for index, (local, remote) in enumerate(zip(chat["turns"], exported["turns"]), 1):
        if local != {k: v for k, v in remote.items() if k != "messages"}:
            raise ValueError(f"Local/export turn differs: {chat['session']} turn {index}")
        graph_path = folder / "turns" / f"{index:03d}" / "graph.json"
        messages_path = graph_path.with_name("messages.json")
        row = {"turn": index, "plugin_version": local.get("version"),
               "agent": (remote.get("messages") or {}).get("agent"),
               "task_invocations": task_invocations(remote),
               "exported_metrics": remote.get("metrics"),
               "export_error_present": bool(remote.get("error"))}
        if not graph_path.exists():
            row["status"] = "missing_graph"
            results.append(row)
            continue
        verify_capture(graph_path, provenance, project_root)
        if messages_path.exists():
            verify_capture(messages_path, provenance, project_root)
        row.update(analyze_graph(json.loads(graph_path.read_text())))
        row["status"] = "analyzed"
        row["graph_source"] = {"path": str(graph_path.relative_to(project_root)), "sha256": digest(graph_path)}
        row["export_comparison"] = compare_export(remote.get("metrics"), row["totals"])
        row["messages_equal_export"] = (json.loads(messages_path.read_text()) == remote.get("messages")
                                         if messages_path.exists() else None)
        row["ui_observation"] = ui
        row["ui_token_comparison"] = None
        if ui and (len(chat["turns"]) == 1 or ui.get("turn") == index):
            row["ui_token_comparison"] = {
                name: compare_value(ui.get(name), row["totals"]["all"]["usage"][key])
                for name, key in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"),
                                  ("cached_input_tokens", "cached_tokens"))}
        results.append(row)
    return {"session_id": chat["session"], "plugin": chat["plugin"],
            "sources": {"chat": {"path": str(chat_path.relative_to(project_root)), "sha256": digest(chat_path)},
                        "export": provenance["export"],
                        "ui": {"path": str(ui_path.relative_to(project_root)), "sha256": digest(ui_path)} if ui else None},
            "turns": results}


def show(value):
    return "—" if value is None else f"{value:,}" if isinstance(value, int) else f"{value:.6g}"


def render(summary):
    lines = ["# Pilot graph accounting", "",
             "Observed model-call records, counted once per graph node and record index. These are pilot descriptions, not success-rate estimates or provider billing totals.", "",
             "| Plugin / turn | Calls outer / nested | Outer input / output | Nested input / output | All input / output | Cached input, all | UI input/output match |",
             "|---|---:|---:|---:|---:|---:|---|"]
    timings, sizes = [], []
    for session in summary["sessions"]:
        for row in session["turns"]:
            name = f"{session['plugin']} / {row['turn']}"
            if row["status"] != "analyzed":
                lines.append(f"| {name} | — | — | — | — | — | Missing graph |")
                continue
            t = row["totals"]
            def pair(scope):
                return " / ".join(show(t[scope]["usage"][k]["known_subtotal"]) for k in ("prompt_tokens", "completion_tokens"))
            checks = row["ui_token_comparison"]
            ui_match = "not recorded" if checks is None else " / ".join(str(checks[k]["equal"]) if checks[k]["equal"] is not None else "unknown" for k in ("input_tokens", "output_tokens"))
            lines.append(f"| {name} | {t['outer']['call_records']} / {t['nested']['call_records']} | {pair('outer')} | {pair('nested')} | {pair('all')} | {show(t['all']['usage']['cached_tokens']['known_subtotal'])} | {ui_match} |")
            m = row["exported_metrics"] or {}
            timings.append(f"| {name} | {show(t['all']['reported_cost_usd']['known_subtotal'])} | {show(t['all']['model_call_seconds']['known_subtotal'])} | {show(m.get('duration_s'))} | {show(m.get('model_s'))} | {show(m.get('tools_s'))} |")
            data = row["nested_data_tool_results"]
            sizes.append(f"| {name} | {data['known_text_results']} | {data['missing_raw_text_results']} | {show(data['known_total_utf8_bytes'])} | {show(data['known_max_utf8_bytes'])} |")
    lines += ["", "| Plugin / turn | Graph cost, USD | Graph model seconds | Export latency, s | Export model, s | Export tool, s |",
              "|---|---:|---:|---:|---:|---:|", *timings, "",
              "| Plugin / turn | Raw-text data results | Missing raw-byte sizes | Known total UTF-8 bytes | Largest known result, bytes |",
              "|---|---:|---:|---:|---:|", *sizes, "",
              "Data-result sizes exclude submit acknowledgments, hidden reference outputs, and the outer task wrapper. Structured graph values have unknown original wire size; they are not reserialized to manufacture a raw byte count.", "",
              "Cached input is included in input tokens; reasoning is included in output tokens. Missing fields remain unknown in JSON. Tables show known subtotals; inspect per-field missing counts and unmeasured model nodes before treating them as complete.", "",
              "Graph cost is the runtime's token-price calculation. Display-rounded UI timing/cost strings are preserved without treating them as exact numbers. Exported calls[] and repeated ATIF history are never added.", "",
              "Failed records, unknown statuses, unmeasured model nodes, source hashes, and export/UI comparisons are retained in the accompanying JSON. Runtime context is supplied by the operator; it is not inferred from graph contents.", ""]
    return "\n".join(lines)


def render_pilots(summary):
    lines = ["# Initial pilot results", "",
             "One observed pilot per captured task. Token columns include outer and nested graph model-call records; latency comes from the native export. Cached input is already part of input tokens.", "",
             "| Task | Case | Model | Input tokens | Cached input | Output tokens | Verifier | Latency, s |",
             "|---|---|---|---:|---:|---:|---|---:|"]
    for session in sorted(summary["sessions"], key=lambda s: s["plugin"]):
        for row in session["turns"]:
            if row["status"] != "analyzed":
                continue
            tools = row["task_invocations"]
            tasks = ", ".join(str(t["task"]) for t in tools) or "not invoked"
            cases = ", ".join(str((t["arguments"] or {}).get("case", "—"))
                              if isinstance(t["arguments"], dict) else "—" for t in tools)
            verdict = ("pass" if all(t["valid"] is True for t in tools) else
                       "fail" if any(t["valid"] is False for t in tools) else "unknown") if tools else "unknown"
            metrics = row["exported_metrics"] or {}
            model = (row.get("agent") or {}).get("model_name") or metrics.get("model") or "unknown"
            usage = row["totals"]["all"]["usage"]
            values = [show(usage[k]["known_subtotal"]) for k in ("prompt_tokens", "cached_tokens", "completion_tokens")]
            lines.append(f"| {tasks} | {cases} | {model} | {' | '.join(values)} | {verdict} | {show(metrics.get('duration_s'))} |")
    lines += ["", "Verifier success uses the recorded valid boolean, not score or assistant prose. These preliminary single-run observations do not estimate a success rate or establish a cross-model comparison.", "",
              "See graph-accounting.json for source hashes, per-call coverage, failed/unknown records, and comparisons with native outer-only counters and captured UI totals. Missing measurements must remain unknown.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--evidence-root", type=Path, default=Path("study/task0/evidence"))
    parser.add_argument("--output-prefix", type=Path, default=Path("study/task0/summaries/graph-accounting"))
    parser.add_argument("--pilot-results", type=Path, default=Path("study/task0/summaries/pilot-results.md"))
    parser.add_argument("--runtime-context", default=None)
    args = parser.parse_args()
    root = args.project_root.resolve()
    evidence = root / args.evidence_root
    sessions = [analyze_evidence(p.parent, root) for p in sorted(evidence.glob("*/chat.json"))]
    summary = {"schema_version": 1, "runtime_context_supplied": args.runtime_context,
               "method": "observed node.modelCalls records; supported chat/task ancestor topology; no provider completeness claim",
               "pending_evidence_directories": [p.name for p in sorted(evidence.iterdir()) if p.is_dir() and not (p / "chat.json").exists()],
               "sessions": sessions}
    output = root / args.output_prefix
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n")
    output.with_suffix(".md").write_text(render(summary))
    (root / args.pilot_results).write_text(render_pilots(summary))
    print(f"Analyzed {len(sessions)} captured sessions -> {output}.json / .md")


if __name__ == "__main__":
    main()
