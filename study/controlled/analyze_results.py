#!/usr/bin/env python3
"""Offline independent analysis of frozen paired trials and native captures.

No app, gateway, or runner API is imported. Archives are streamed and never
extracted; only named regular public files are copied into a temporary directory
for the host-side deterministic validator. Native verdicts remain primary.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import statistics
import tarfile
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
MAX_ARCHIVE_BYTES = 256 << 20
MAX_UNPACKED_BYTES = 256 << 20
MAX_SELECTED_BYTES = 64 << 20
MAX_RECORD_BYTES = 4 << 20
MAX_MEMBERS = 10000
METRICS = ("input_tokens", "cached_tokens", "output_tokens", "native_elapsed_s", "agent_elapsed_s", "cost_usd")
FIELDS = {"input_tokens": ("input", "input_tokens"), "cached_tokens": ("cache_read", "cache_read_tokens"),
          "output_tokens": ("output", "output_tokens")}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, child in items:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = child
        return value
    def number(text):
        value = float(text)
        if not math.isfinite(value):
            raise ValueError("Nonfinite JSON number")
        return value
    return json.loads(raw, object_pairs_hook=pairs, parse_float=number,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON number")))


def read_bytes(path, cap=MAX_ARCHIVE_BYTES):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > cap:
        raise ValueError("Missing, linked, or oversized evidence file: " + path.name)
    with path.open("rb") as handle:
        raw = handle.read(cap + 1)
    if len(raw) > cap:
        raise ValueError("Evidence exceeded byte bound")
    return raw


def load(path):
    return strict_json(read_bytes(path))


def project_path(path, *, recorded_root=None, project_root=PROJECT_ROOT):
    """Rebind archived project paths without changing any evidence bytes."""
    path, root = Path(path), Path(project_root).resolve()
    if path.is_absolute():
        old = Path(recorded_root) if recorded_root else root
        if path.is_relative_to(old):
            path = root / path.relative_to(old)
    else:
        path = root / path
    if not path.resolve().is_relative_to(root):
        raise ValueError("Evidence path escapes project root")
    return path.resolve()


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def measured(values):
    known = [v for v in values if numeric(v)]
    return {"value": sum(known) if len(known) == len(values) else None,
            "known_subtotal": sum(known), "known_count": len(known), "missing_count": len(values) - len(known)}


class BoundedReader:
    def __init__(self, stream, maximum):
        self.stream, self.maximum, self.total = stream, maximum, 0

    def read(self, size=-1):
        if size < 0:
            size = self.maximum - self.total + 1
        raw = self.stream.read(min(size, self.maximum - self.total + 1))
        self.total += len(raw)
        if self.total > self.maximum:
            raise ValueError("Archive exceeds decompressed byte bound")
        return raw


def read_tar_records(stream, *, max_unpacked=MAX_UNPACKED_BYTES):
    """Read bounded regular records; reject traversal/links without writing paths."""
    records, names, total, count = {}, set(), 0, 0
    with tarfile.open(fileobj=BoundedReader(stream, max_unpacked), mode="r|") as archive:
        for member in archive:
            count += 1
            if count > MAX_MEMBERS:
                raise ValueError("Too many archive members")
            name = member.name[2:] if member.name.startswith("./") else member.name
            parts = PurePosixPath(name).parts
            if not parts or name.startswith("/") or ".." in parts or "\\" in name:
                raise ValueError("Unsafe archive member path")
            if name in names:
                raise ValueError("Duplicate archive member")
            names.add(name)
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("Archive contains nonregular file")
            selected = name in {"input.json", "prompt.txt", "answer.json"} or (
                len(parts) >= 3 and parts[0] == ".comp580_logs" and re.fullmatch("[0-9a-f]{32}", parts[1]))
            if not selected:
                continue
            if member.size > MAX_RECORD_BYTES or member.size < 0:
                raise ValueError("Selected archive record exceeds bound")
            total += member.size
            if total > MAX_SELECTED_BYTES:
                raise ValueError("Selected archive records exceed bound")
            raw = archive.extractfile(member).read(MAX_RECORD_BYTES + 1)
            if len(raw) != member.size:
                raise ValueError("Archive member size mismatch")
            records[name] = raw
    return records


def read_workspace(path):
    import zstandard
    raw = read_bytes(path)
    with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw)) as stream:
        return read_tar_records(stream)


def verify_capture(index_path, *, recorded_root=None, project_root=PROJECT_ROOT):
    index_path = Path(index_path).resolve()
    index = load(index_path)
    folder = index_path.parent
    declared = {}
    for entry in index["files"]:
        path = project_path(entry["path"], recorded_root=recorded_root, project_root=project_root)
        if not path.resolve().is_relative_to(folder) or path in declared:
            raise ValueError("Capture file escaped folder or was duplicated")
        raw = read_bytes(path)
        if digest(raw) != entry["sha256"] or len(raw) != entry["bytes"]:
            raise ValueError("Capture hash/size mismatch: " + path.name)
        declared[path] = entry
    for name in ("run.json", "selected-run.json", "native-export.jsonl"):
        if folder / name not in declared:
            raise ValueError("Required capture file not covered by index")
    run, exported = load(folder / "run.json"), load(folder / "selected-run.json")
    selected = [strict_json(line) for line in read_bytes(folder / "native-export.jsonl").splitlines() if line.strip()]
    selected = [row for row in selected if row.get("type") == "run" and row.get("run_id") == run["run_id"]]
    if selected != [exported] or exported["run_id"] != index["run_id"]:
        raise ValueError("Selected run differs from original native export")
    native_ids = [a["attempt_id"] for a in exported["attempts"]]
    detailed_ids = [a["attempt_id"] for c in run["cases"] for a in c["attempts"]]
    if len(set(native_ids)) != len(native_ids) or sorted(native_ids) != sorted(detailed_ids):
        raise ValueError("Attempt identities differ or contain duplicates")
    if index["actual_attempt_count"] != len(native_ids):
        raise ValueError("Capture attempt count mismatch")
    for aid in native_ids:
        for name in ("attempt.json", "accounting.json", "events.jsonl"):
            if folder / "attempts" / aid / name not in declared:
                raise ValueError("Attempt evidence not covered by capture index")
        workspace = folder / "attempts" / aid / "workspace.tar.zst"
        if workspace.exists() and workspace not in declared:
            raise ValueError("Workspace archive not covered by capture index")
    return index, run, exported


def verify_frozen(frozen, progress, *, project_root=PROJECT_ROOT):
    expected = digest(canonical({k: v for k, v in frozen.items() if k != "freeze_sha256"}))
    if expected != frozen["freeze_sha256"] or progress["freeze_sha256"] != expected:
        raise ValueError("Freeze/progress digest mismatch")
    if frozen["logical_trial_count"] != 50 or len(frozen["trials"]) != 50 or len(frozen["cases"]) != 5:
        raise ValueError("Expected frozen five-task, fifty-trial study")
    ids = [t["trial_id"] for t in frozen["trials"]]
    keys = [t["request"]["idempotency_key"] for t in frozen["trials"]]
    if len(set(ids)) != 50 or len(set(keys)) != 50 or set(progress["trials"]) - set(ids):
        raise ValueError("Unexpected or duplicate trial identity")
    for case in frozen["cases"]:
        replicates = []
        for condition in ("full", "compact"):
            selected = [t for t in frozen["trials"] if t["case_id"] == case["case_id"] and t["condition"] == condition]
            if len(selected) != 5 or len({t["replicate"] for t in selected}) != 5:
                raise ValueError("Each task/condition requires five distinct paired replicates")
            replicates.append({t["replicate"] for t in selected})
        if replicates[0] != replicates[1]:
            raise ValueError("Conditions do not share the same paired replicates")
    root = Path(project_root).resolve()
    if digest(canonical(frozen["source_tree"]["files"])) != frozen["source_tree"]["sha256"]:
        raise ValueError("Frozen source tree digest is inconsistent")
    for name, expected in frozen["source_tree"]["files"].items():
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()) or digest(read_bytes(path)) != expected:
            raise ValueError("Frozen source or validator changed: " + name)
    original_wheel = project_path(frozen["wheel"]["path"], recorded_root=frozen["project_root"], project_root=root)
    archived_wheel = root / "study/controlled/development/artifacts" / original_wheel.name
    wheel_path = archived_wheel if archived_wheel.exists() else original_wheel
    if digest(read_bytes(wheel_path)) != frozen["wheel"]["sha256"]:
        raise ValueError("Frozen wheel changed")
    if digest(canonical(frozen["wheel"]["package_modules_sha256"])) != frozen["wheel"]["code_sha256"]:
        raise ValueError("Frozen package identity is inconsistent")
    with zipfile.ZipFile(io.BytesIO(read_bytes(wheel_path))) as wheel:
        modules = {}
        names = wheel.namelist()
        if len(set(names)) != len(names):
            raise ValueError("Wheel contains duplicate members")
        for info in wheel.infolist():
            path = PurePosixPath(info.filename)
            if path.parts and path.parts[0] == "comp580_agent" and path.suffix == ".py":
                if len(path.parts) != 2 or info.file_size > MAX_RECORD_BYTES:
                    raise ValueError("Unexpected or oversized wheel module")
                modules[path.name] = digest(wheel.read(info))
        if modules != frozen["wheel"]["package_modules_sha256"]:
            raise ValueError("Evidence wheel modules differ from frozen source identity")
    return {"source_tree_sha256": frozen["source_tree"]["sha256"], "wheel_path": str(wheel_path),
            "wheel_source": "retained_archive" if wheel_path == archived_wheel else "original_path",
            "wheel_sha256": frozen["wheel"]["sha256"]}


def model_usage(calls, metrics, coverage):
    ids = [c["call_id"] for c in calls]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate native model call")
    result, issues = {}, []
    for label, (field, metric_field) in FIELDS.items():
        count = measured([(c.get("usage") or {}).get(field) for c in calls])
        count["complete"] = (metrics.get("model_calls") == len(calls)
                             and metrics.get("usage_complete") is True
                             and (metrics.get("missing_calls") or {}).get(field) == 0
                             and count["missing_count"] == 0)
        if coverage.get("collector_complete") is False or coverage.get("missing_sources"):
            count["complete"] = False
        if numeric(metrics.get(metric_field)) and metrics[metric_field] != count["known_subtotal"]:
            issues.append("native_metric_call_sum_mismatch:" + label)
            count["complete"] = False
        if not count["complete"]:
            count["value"] = None
        result[label] = count
    if (result["cached_tokens"]["value"] is not None and result["input_tokens"]["value"] is not None
            and result["cached_tokens"]["value"] > result["input_tokens"]["value"]):
        raise ValueError("Cached token subset exceeds input tokens")
    return result, issues


def settled_cost(accounting, calls, zero_known=False):
    rows = accounting.get("calls", [])
    ids = [r["call_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate accounting call")
    values = [r["admission"].get("cost_usd") if r["admission"].get("status") == "settled" else None for r in rows]
    count = measured(values)
    complete = (set(ids) == {c["call_id"] for c in calls} and count["missing_count"] == 0
                and (bool(calls) or zero_known))
    count["complete"] = complete
    if not complete:
        count["value"] = None
    statuses = {}
    for row in rows:
        record = (row.get("accounting") or {}).get("record") or {}
        generation = record.get("generation") or {}
        for response in generation.get("provider_responses") or []:
            key = str(response.get("status", "unknown"))
            statuses[key] = statuses.get(key, 0) + 1
    count["provider_response_statuses"] = statuses
    return count


def validator_function():
    path = HERE / "validators/validate.py"
    spec = importlib.util.spec_from_file_location("comp580_offline_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_case


def audit_workspace(records, case_id, validator):
    with tempfile.TemporaryDirectory(prefix="comp580-answer-audit-") as directory:
        for name in ("input.json", "prompt.txt", "answer.json"):
            if name in records:
                (Path(directory) / name).write_bytes(records[name])
        return validator(case_id, directory)


def agent_records(records):
    names = [name for name in records if re.fullmatch(r"\.comp580_logs/[0-9a-f]{32}/run\.json", name)]
    if len(names) != 1:
        return None, None, [], ["agent_metadata_missing_or_ambiguous"]
    prefix = names[0].removesuffix("run.json")
    run = strict_json(records[names[0]])
    result = strict_json(records[prefix + "result.json"]) if prefix + "result.json" in records else None
    events = [strict_json(line) for line in records.get(prefix + "events.jsonl", b"").splitlines() if line.strip()]
    issues = [] if result is not None else ["agent_result_missing"]
    for event in events:
        for key in ("request", "response", "raw", "visible"):
            reference = event.get(key)
            if isinstance(reference, dict) and "path" in reference:
                raw = records.get(prefix + reference["path"])
                if raw is None or digest(raw) != reference.get("sha256") or len(raw) != reference.get("bytes"):
                    issues.append("agent_artifact_hash_mismatch:" + key)
    return run, result, events, issues


def tool_diagnostics(events, result):
    """Frozen v0.2.0 retains history; only a later dispatched call sees a result."""
    tools = [e for e in events if e.get("kind") == "tool_call"]
    names = {}
    for event in tools:
        counts = names.setdefault(event.get("name", "unknown"), {"total": 0, "completed": 0, "failed": 0})
        counts["total"] += 1
        if event.get("status") in ("completed", "failed"):
            counts[event["status"]] += 1
    dispatched = len(result["model_calls"]) if result is not None and isinstance(result.get("model_calls"), list) else None
    def aggregate(selected, weighted=False):
        totals = {}
        for kind in ("raw", "visible"):
            for form, field in (("original", "original_bytes"), ("saved", "bytes")):
                values = []
                for event in selected:
                    reference = event.get(kind)
                    if not isinstance(reference, dict):
                        continue  # No serialized artifact was produced for this field.
                    value = reference.get(field)
                    weight = dispatched - event["model_call"] if weighted else 1
                    values.append(value * weight if numeric(value) else None)
                totals[kind + "_" + form] = measured(values)
        return totals
    delivered = [e for e in tools if dispatched is not None and type(e.get("model_call")) is int
                 and 0 < e["model_call"] < dispatched and isinstance(e.get("visible"), dict)]
    return {"tool_name_counts": names, "serialized_tool_bytes": aggregate(tools),
            "delivered_tool_bytes": aggregate(delivered) if dispatched is not None else None,
            "cumulative_delivered_tool_bytes": aggregate(delivered, True) if dispatched is not None else None,
            "delivered_tool_events": len(delivered) if dispatched is not None else None,
            "tool_byte_scope": "UTF-8 bytes of original and credential-redacted saved artifacts; serialized includes final acknowledgements. "
            "Delivery is inferred for frozen v0.2.0 full retained history when event.model_call < dispatched agent call count; "
            "cumulative totals weight each result by subsequent dispatched calls. Raw is the full JSON counterpart, not a second delivered message."}


def trial_measurements(attempts):
    totals = {key: measured([a[key] for a in attempts]) for key in METRICS}
    for key in (*FIELDS, "cost_usd"):
        details = [a["cost_measurement"] if key == "cost_usd" else a["token_measurements"][key] for a in attempts]
        totals[key].update(known_subtotal=sum(d["known_subtotal"] for d in details),
                           known_call_count=sum(d["known_count"] for d in details),
                           missing_call_count=sum(d["missing_count"] for d in details),
                           count_scope="known_count/missing_count count complete/incomplete attempt totals; "
                           "known_subtotal includes every known call within incomplete attempts; "
                           "call counts describe captured call records, not unobserved calls")
    return totals


def analyze_capture(index_path, trial, case, wheel, *, validator=None, recorded_root=None, project_root=PROJECT_ROOT):
    index, run, exported = verify_capture(index_path, recorded_root=recorded_root, project_root=project_root)
    if (run["benchmark"]["benchmark_id"] != trial["benchmark_id"]
            or run["harness"]["name"] != trial["request"]["harness"]
            or exported["harness"]["name"] != trial["request"]["harness"]):
        raise ValueError("Run benchmark or harness differs from frozen trial")
    for field in ("model", "endpoint_profile", "providers", "limits"):
        if run[field] != case["benchmark"][field]:
            raise ValueError("Native configuration differs from frozen benchmark")
    if len(run["cases"]) != 1 or run["cases"][0]["prompt_sha256"] != case["prompt_sha256"]:
        raise ValueError("Native case/prompt differs from frozen case")
    folder = Path(index_path).resolve().parent
    validator = validator or validator_function()
    attempts = []
    for native in sorted(exported["attempts"], key=lambda a: a["attempt_no"]):
        aid = native["attempt_id"]
        attempt_dir = folder / "attempts" / aid
        actual = load(attempt_dir / "attempt.json")
        if actual["attempt_id"] != aid or actual.get("run_id") != run["run_id"] or not actual["sealed"]:
            raise ValueError("Unsealed or mismatched attempt identity")
        metrics, coverage = actual.get("metrics") or {}, actual.get("coverage") or {}
        calls = native["model_calls"]
        usage, issues = model_usage(calls, metrics, coverage)
        costs = settled_cost(load(attempt_dir / "accounting.json"), calls,
                             zero_known=metrics.get("model_calls") == 0 and metrics.get("usage_complete") is True)
        workspace_path = attempt_dir / "workspace.tar.zst"
        records = read_workspace(workspace_path) if workspace_path.exists() else {}
        agent, result, events, record_issues = agent_records(records)
        worker_error = (actual.get("execution") or {}).get("status") == "worker_error"
        if not worker_error or records:
            issues += record_issues
        identity = bool(agent and agent.get("code_sha256") == wheel["code_sha256"]
                        and agent.get("package_modules_sha256") == wheel["package_modules_sha256"]
                        and agent.get("condition") == trial["condition"]
                        and agent.get("configured_model") == run["model"]
                        and agent.get("max_output_tokens") == run["limits"]["max_output_tokens_per_call"])
        if agent and not identity:
            issues.append("agent_identity_or_configuration_mismatch")
        if "prompt.txt" in records and digest(records["prompt.txt"]) != case["prompt_sha256"]:
            issues.append("workspace_prompt_mismatch")
        for path, raw in records.items():
            if re.fullmatch(r"\.comp580_logs/[0-9a-f]{32}/prompt\.txt", path) and digest(raw) != case["prompt_sha256"]:
                issues.append("agent_exact_prompt_mismatch")
        audit = audit_workspace(records, case["case_id"], validator) if records else {"valid": None, "status": "workspace_missing"}
        agent_calls = result.get("model_calls", []) if result else []
        if result and len(agent_calls) != len(calls):
            issues.append("agent_native_model_call_count_mismatch")
        if result:
            for label, field in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens")):
                local = measured([(c.get("usage") or {}).get(field) for c in agent_calls])
                if usage[label]["value"] is not None and local["value"] != usage[label]["value"]:
                    issues.append("agent_native_usage_mismatch:" + label)
        elapsed_ns = metrics.get("elapsed_ns")
        native_elapsed = elapsed_ns / 1e9 if numeric(elapsed_ns) else metrics.get("elapsed_ms") / 1000 if numeric(metrics.get("elapsed_ms")) else None
        agent_elapsed = result.get("elapsed_seconds") if result and numeric(result.get("elapsed_seconds")) else None
        attempts.append({"attempt_id": aid, "attempt_no": native["attempt_no"], "run_id": run["run_id"],
                         "case_id": case["case_id"], "condition": trial["condition"], "trial_id": trial["trial_id"],
                         "execution": actual.get("execution"), "native_verdict": actual.get("verdict"),
                         "native_verifier_error": actual.get("verifier_error"), "local_audit": audit,
                         "agent_status": result.get("status") if result else None,
                         "agent_failure": result.get("failure") if result else None,
                         "agent_identity_valid": identity, "issues": issues, "coverage": coverage,
                         "native_metrics": metrics, "token_measurements": usage, "cost_measurement": costs,
                         "input_tokens": usage["input_tokens"]["value"], "cached_tokens": usage["cached_tokens"]["value"],
                         "output_tokens": usage["output_tokens"]["value"], "agent_elapsed_s": agent_elapsed,
                         "native_elapsed_s": native_elapsed, "cost_usd": costs["value"],
                         "model_call_count": len(calls), "agent_model_call_count": len(agent_calls) if result else None,
                         "agent_tool_calls": result.get("tool_calls") if result else None,
                         "native_tool_calls": metrics.get("tool_calls"),
                         "resolved_models": sorted({c["model"]["resolved"] for c in calls
                                                    if isinstance(c.get("model"), dict) and isinstance(c["model"].get("resolved"), str)}),
                         **tool_diagnostics(events, result),
                         "model_calls": [{k: c.get(k) for k in ("call_id", "model", "status", "http_status", "finish_reason", "usage", "timing_ns", "error")} for c in calls]})
    if not attempts or len({a["attempt_no"] for a in attempts}) != len(attempts):
        raise ValueError("Missing or duplicate attempt numbers")
    latest = attempts[-1]
    success = True if latest["native_verdict"] == "pass" else False if latest["native_verdict"] == "fail" else None
    issues = [{"attempt_id": a["attempt_id"], "issue": issue} for a in attempts for issue in a["issues"]]
    row = {"trial_id": trial["trial_id"], "case_id": case["case_id"], "condition": trial["condition"],
           "replicate": trial["replicate"], "run_id": run["run_id"], "phase": "captured",
           "native_success": success, "native_verdict": latest["native_verdict"],
           "agent_status": latest["agent_status"], "agent_failure": latest["agent_failure"],
           "local_audit_valid": latest["local_audit"]["valid"], "attempt_count": len(attempts),
           "retry_count": len(attempts) - 1, "latest_attempt_id": latest["attempt_id"],
           "identity_valid": latest["agent_identity_valid"], "issues": issues,
           "capture_issues": index.get("capture_issues", []), "capture_path": str(Path(index_path).resolve()),
           "capture_sha256": digest(read_bytes(index_path)),
           "measurement_scope": "sum across every attempt; any missing attempt value makes total unknown",
           "performance_eligible": success is True and latest["local_audit"].get("valid") is True
           and latest["agent_identity_valid"] and not issues and not index.get("capture_issues")}
    row["measurements"] = trial_measurements(attempts)
    row.update({key: row["measurements"][key]["value"] for key in METRICS})
    return row, attempts


def describe(values):
    known = [v for v in values if numeric(v)]
    return {"n": len(known), "missing": len(values) - len(known),
            "mean": statistics.mean(known) if known else None,
            "sample_sd": statistics.stdev(known) if len(known) > 1 else None,
            "min": min(known) if known else None, "max": max(known) if known else None}


def paired_rows(trials):
    blocks = {}
    for trial in trials:
        block = blocks.setdefault((trial["case_id"], trial["replicate"]), {})
        if trial["condition"] in block:
            raise ValueError("Duplicate paired condition")
        block[trial["condition"]] = trial
    result = []
    for (case, replicate), conditions in sorted(blocks.items()):
        full, compact = conditions.get("full"), conditions.get("compact")
        eligible = bool(full and compact and full.get("performance_eligible") and compact.get("performance_eligible"))
        row = {"case_id": case, "replicate": replicate, "both_successful_and_audited": eligible,
               "full_success": full.get("native_success") if full else None,
               "compact_success": compact.get("native_success") if compact else None,
               "full_run_id": full.get("run_id") if full else None, "compact_run_id": compact.get("run_id") if compact else None}
        for metric in METRICS:
            a, b = full.get(metric) if full else None, compact.get(metric) if compact else None
            available = eligible and numeric(a) and numeric(b)
            row[metric + "_delta"] = b - a if available else None
            row[metric + "_ratio"] = b / a if available and a > 0 else None
        result.append(row)
    return result


def summaries(trials, pairs):
    result = []
    for case in sorted({t["case_id"] for t in trials}):
        for condition in ("full", "compact"):
            rows = [t for t in trials if t["case_id"] == case and t["condition"] == condition]
            eligible = [t for t in rows if t.get("performance_eligible")]
            result.append({"case_id": case, "condition": condition, "planned": len(rows),
                           "captured": sum(t.get("phase") == "captured" for t in rows),
                           "native_passes": sum(t.get("native_success") is True for t in rows),
                           "native_failures": sum(t.get("native_success") is False for t in rows),
                           "native_unscored": sum(t.get("native_success") is None for t in rows),
                           "local_audit_passes": sum(t.get("local_audit_valid") is True for t in rows),
                           "performance_eligible_trials": len(eligible),
                           "actual_attempts": sum(t.get("attempt_count", 0) for t in rows),
                           "latency_all_captured_trials": {m: describe([t.get(m) for t in rows if t.get("phase") == "captured"])
                                                           for m in ("native_elapsed_s", "agent_elapsed_s")},
                           "metrics_successful_audited_trials": {m: describe([t.get(m) for t in eligible]) for m in METRICS}})
    pair_summary = []
    for case in sorted({p["case_id"] for p in pairs}):
        rows = [p for p in pairs if p["case_id"] == case]
        # Deltas may be negative; use a signed descriptive statistic here.
        def signed(values):
            known = [v for v in values if type(v) in (int, float) and math.isfinite(v)]
            return {"n": len(known), "missing": len(values) - len(known), "mean": statistics.mean(known) if known else None,
                    "sample_sd": statistics.stdev(known) if len(known) > 1 else None,
                    "min": min(known) if known else None, "max": max(known) if known else None}
        pair_summary.append({"case_id": case, "planned_pairs": len(rows),
                             "both_successful_and_audited": sum(p["both_successful_and_audited"] for p in rows),
                             "paired_statistics": {m: {"ratio": describe([p[m + "_ratio"] for p in rows]),
                                                       "delta": signed([p[m + "_delta"] for p in rows])} for m in METRICS}})
    return result, pair_summary


def analyze(freeze_path, progress_path, *, project_root=PROJECT_ROOT):
    frozen, progress = load(freeze_path), load(progress_path)
    verification = verify_frozen(frozen, progress, project_root=project_root)
    trials, attempts, seen_runs = [], [], set()
    for trial in frozen["trials"]:
        current = progress["trials"].get(trial["trial_id"], {})
        if current.get("request") is not None and current["request"] != trial["request"]:
            raise ValueError("Progress request differs from frozen trial")
        capture_paths = current.get("captures") or []
        if not capture_paths:
            trials.append({**{k: trial[k] for k in ("trial_id", "case_id", "condition", "replicate")},
                           "phase": current.get("phase", "not_started"), "run_id": current.get("run_id"),
                           "native_success": None, "performance_eligible": False})
            continue
        case = next(c for c in frozen["cases"] if c["case_id"] == trial["case_id"])
        path = project_path(capture_paths[-1], recorded_root=frozen["project_root"], project_root=project_root)
        row, captured_attempts = analyze_capture(path, trial, case, frozen["wheel"],
                                               recorded_root=frozen["project_root"], project_root=project_root)
        if row["run_id"] != current.get("run_id") or row["run_id"] in seen_runs or row["run_id"] in frozen["excluded_run_ids"]:
            raise ValueError("Duplicate, excluded, or wrong logical run")
        seen_runs.add(row["run_id"])
        row["progress_phase"] = current.get("phase")
        trials.append(row)
        attempts.extend(captured_attempts)
    pairs = paired_rows(trials)
    summary, paired_summary = summaries(trials, pairs)
    return {"schema_version": 1, "freeze_sha256": frozen["freeze_sha256"],
            "analyzer_sha256": digest(read_bytes(__file__)),
            "frozen_artifact_verification": verification,
            "progress_file_sha256": digest(read_bytes(progress_path)), "configuration": frozen["configuration"],
            "frozen_code_sha256": frozen["wheel"]["code_sha256"],
            "planned_trials": 50, "captured_trials": len(seen_runs), "actual_attempts": len(attempts),
            "excluded_run_ids": frozen["excluded_run_ids"], "trials": trials, "attempts": attempts,
            "unsuccessful_trials": [t for t in trials if t.get("phase") == "captured" and t.get("native_success") is not True],
            "pairs": pairs, "summary": summary, "paired_summary": paired_summary,
            "interpretation": ["Native latest-attempt verdict is primary; independent local validation is an audit.",
                               "Token, cost and duration totals include all attempts, not only the latest attempt.",
                               "Cached tokens are a subset of input tokens, not an additional token total.",
                               "Costs are admission settlement totals only; provider generation/accounting copies are not added.",
                               "Provider routing statuses may show retries despite zero agent-level retries.",
                               "Paired savings exclude failed or unaudited pairs and incomplete metrics; failures remain in trial tables.",
                               "Five paired repetitions per task support descriptive SD/range only; no broad generalization or significance claim."]}


def csv_file(path, rows, columns):
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(row.get(key), ensure_ascii=False) if isinstance(row.get(key), (dict, list)) else row.get(key) for key in columns})


def display(value, digits=2):
    return "unknown" if value is None else f"{value:.{digits}f}"


def write_outputs(result, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    common = ["trial_id", "case_id", "condition", "run_id"]
    csv_file(output / "trials.csv", result["trials"], common + ["replicate", "phase", "native_success", "native_verdict", "agent_status", "agent_failure", "local_audit_valid", "attempt_count", "retry_count", "identity_valid", "performance_eligible", *METRICS, "measurements", "issues"])
    csv_file(output / "failures.csv", result["unsuccessful_trials"], common + ["replicate", "native_verdict", "agent_status", "agent_failure", "local_audit_valid", "attempt_count", *METRICS, "measurements", "issues"])
    csv_file(output / "attempts.csv", result["attempts"], common + ["attempt_id", "attempt_no", "execution", "native_verdict", "native_verifier_error", "agent_status", "agent_failure", "agent_identity_valid", "model_call_count", "agent_model_call_count", "agent_tool_calls", "native_tool_calls", "resolved_models", *METRICS, "local_audit", "tool_name_counts", "serialized_tool_bytes", "delivered_tool_bytes", "cumulative_delivered_tool_bytes", "issues"])
    csv_file(output / "pairs.csv", result["pairs"], ["case_id", "replicate", "both_successful_and_audited", "full_success", "compact_success", "full_run_id", "compact_run_id"] + [m + suffix for m in METRICS for suffix in ("_delta", "_ratio")])
    lines = ["# Controlled experiment results", "", f"Captured {result['captured_trials']}/50 logical trials; {result['actual_attempts']} actual attempts. Freeze `{result['freeze_sha256']}`.", "",
             "Native pass counts include every planned logical trial. Metric entries are mean ± sample SD (n) for successful, independently audited trials; unknown measurements are excluded explicitly by n. Every attempt and failed or unscored trial remains in the CSV/JSON evidence.", "",
             "| Task / condition | Native pass / planned | Captured | Actual attempts | Input tokens (n) | Cached subset (n) | Output tokens (n) | Native seconds (n) | Agent seconds (n) | Settled USD (n) |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["summary"]:
        cells = [f"{row['case_id']} / {row['condition']}", f"{row['native_passes']}/{row['planned']}", str(row["captured"]), str(row["actual_attempts"])]
        for metric in METRICS:
            stats = row["metrics_successful_audited_trials"][metric]
            digits = 6 if metric == 'cost_usd' else 2
            cells.append(f"{display(stats['mean'], digits)} ± {display(stats['sample_sd'], digits)} ({stats['n']})")
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "Paired ratios are Compact/Full; deltas are Compact minus Full. Only pairs in which both conditions pass and satisfy the audit contribute. SD is sample SD; with n ≤ 5 these are descriptive results, not a significance test.", "",
              "| Task | Eligible pairs | Input ratio mean ± SD [range] | Native-time ratio mean ± SD [range] | Agent-time ratio mean ± SD [range] |", "|---|---:|---|---|---|"]
    for row in result["paired_summary"]:
        cells = [row["case_id"], f"{row['both_successful_and_audited']}/{row['planned_pairs']}"]
        for metric in ("input_tokens", "native_elapsed_s", "agent_elapsed_s"):
            stats = row["paired_statistics"][metric]["ratio"]
            cells.append(f"{display(stats['mean'])} ± {display(stats['sample_sd'])} [{display(stats['min'])}, {display(stats['max'])}], n={stats['n']}")
        lines.append("| " + " | ".join(cells) + " |")
    if result["unsuccessful_trials"]:
        lines += ["", "Unsuccessful captured trials remain part of the experiment. Known usage subtotals below are partial evidence, not complete totals or savings. The full trial time includes the failure; all-trial latency statistics are also retained in analysis.json.", "",
                  "| Trial | Native / agent outcome | Native seconds | Agent seconds | Known input / cached / output | Settled cost known subtotal (USD) |",
                  "|---|---|---:|---:|---|---:|"]
        for row in result["unsuccessful_trials"]:
            counts = [row["measurements"][key] for key in ("input_tokens", "cached_tokens", "output_tokens")]
            usage = " / ".join(f"{c['known_subtotal']:g}" + (" (total unknown)" if c["value"] is None else "") for c in counts)
            cost = row["measurements"]["cost_usd"]
            failure = (row.get("agent_failure") or {}).get("code", row.get("agent_status"))
            cells = [row["trial_id"], f"{row['native_verdict']} / {failure}", display(row["native_elapsed_s"], 3),
                     display(row["agent_elapsed_s"], 3), usage,
                     display(cost["known_subtotal"], 6) + (" (total unknown)" if cost["value"] is None else "")]
            lines.append("| " + " | ".join(cells) + " |")
    lines += ["", *["- " + note for note in result["interpretation"]], ""]
    (output / "results_summary.md").write_text("\n".join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, default=HERE / "final/freeze.json")
    parser.add_argument("--progress", type=Path, default=HERE / "final/progress.json")
    parser.add_argument("--out", type=Path, default=HERE / "final/analysis")
    args = parser.parse_args(argv)
    result = analyze(args.freeze, args.progress)
    write_outputs(result, args.out)
    print(json.dumps({"captured_trials": result["captured_trials"], "actual_attempts": result["actual_attempts"], "output": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
