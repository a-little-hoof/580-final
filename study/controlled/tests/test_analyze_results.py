"""Offline evidence accounting tests; no gateway or app is used."""
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "analyze_results.py"
spec = importlib.util.spec_from_file_location("analyze_results", SCRIPT)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def raw(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode()


def tar_bytes(records, special=None):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, body in records:
            info = tarfile.TarInfo(name)
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
        if special:
            archive.addfile(special)
    return stream.getvalue()


def complete_usage(calls):
    return {"model_calls": len(calls), "usage_complete": True,
            "missing_calls": {k: 0 for k in ("input", "output", "cache_read", "cache_write", "total")},
            "input_tokens": sum(c["usage"]["input"] for c in calls),
            "cache_read_tokens": sum(c["usage"]["cache_read"] for c in calls),
            "output_tokens": sum(c["usage"]["output"] for c in calls)}


def native_call(call_id="call", input_tokens=100, cached=20, output=10):
    return {"call_id": call_id, "model": {"requested": "model", "resolved": "actual-model"},
            "status": "completed", "http_status": 200,
            "usage": {"input": input_tokens, "cache_read": cached, "output": output}}


class CaptureFixture:
    def __init__(self, root, *, verdict="pass", retry=False, identity=True):
        self.root = Path(root)
        self.folder = self.root / "evidence/capture"
        self.folder.mkdir(parents=True)
        self.index_path = self.folder / "capture.json"
        self.wheel = {"code_sha256": "code", "package_modules_sha256": {"agent.py": "module"}}
        self.prompt = b"Read input.json and write answer.json."
        config = {"model": "model", "endpoint_profile": "profile", "providers": ["provider"],
                  "limits": {"max_output_tokens_per_call": 123}}
        self.trial = {"trial_id": "task/case/full/rep01", "case_id": "task/case", "condition": "full",
                      "replicate": "rep01", "benchmark_id": "benchmark", "request": {"harness": "command"}}
        self.case = {"case_id": "task/case", "prompt_sha256": analysis.digest(self.prompt), "benchmark": config}
        run = {"run_id": "run", "benchmark": {"benchmark_id": "benchmark"}, "harness": {"name": "command"},
               **config, "cases": [{"prompt_sha256": self.case["prompt_sha256"], "attempts": []}]}
        exported = {"type": "run", "run_id": "run", "harness": run["harness"], "attempts": []}
        for number in range(1, 3 if retry else 2):
            worker_error = (retry and number == 1) or verdict is None
            aid = "attempt" + str(number)
            directory = self.folder / "attempts" / aid
            directory.mkdir(parents=True)
            calls = [] if worker_error else [native_call()]
            metrics = complete_usage(calls)
            metrics["elapsed_ns"] = number * 1_000_000_000
            if worker_error:
                metrics["usage_complete"] = False
            actual = {"attempt_id": aid, "attempt_no": number, "run_id": "run", "sealed": True,
                      "metrics": metrics, "coverage": {"collector_complete": True, "missing_sources": []},
                      "execution": {"status": "worker_error" if worker_error else "completed"},
                      "verdict": None if worker_error else verdict, "verifier_error": None}
            exported["attempts"].append({"attempt_id": aid, "attempt_no": number, "model_calls": calls})
            run["cases"][0]["attempts"].append({"attempt_id": aid})
            (directory / "attempt.json").write_bytes(raw(actual))
            accounting = {"calls": [{"call_id": c["call_id"], "admission": {"status": "settled", "cost_usd": .01},
                                      "accounting": {"record": {"generation": {"provider_responses": [{"status": 429}, {"status": 200}]}}}}
                                     for c in calls]}
            (directory / "accounting.json").write_bytes(raw(accounting))
            (directory / "events.jsonl").write_bytes(b"")
            if not worker_error:
                import zstandard
                prefix = ".comp580_logs/" + "a" * 32 + "/"
                agent = {**self.wheel, "condition": "full", "configured_model": "model", "max_output_tokens": 123}
                if not identity:
                    agent["code_sha256"] = "different-code"
                result = {"status": "completed", "model_calls": [{"usage": {"prompt_tokens": 100, "completion_tokens": 10}}],
                          "elapsed_seconds": .5, "tool_calls": 2}
                records = [("input.json", b"{}"), ("prompt.txt", self.prompt), ("answer.json", b"{}"),
                           (prefix + "run.json", raw(agent)), (prefix + "result.json", raw(result)),
                           (prefix + "events.jsonl", b""), (prefix + "prompt.txt", self.prompt)]
                (directory / "workspace.tar.zst").write_bytes(zstandard.ZstdCompressor().compress(tar_bytes(records)))
        (self.folder / "run.json").write_bytes(raw(run))
        (self.folder / "selected-run.json").write_bytes(raw(exported))
        (self.folder / "native-export.jsonl").write_bytes(raw(exported) + b"\n")
        self.index = {"run_id": "run", "actual_attempt_count": len(exported["attempts"]), "capture_issues": [], "files": []}
        self.reindex()

    def reindex(self):
        self.index["files"] = [{"path": str(p.relative_to(self.root)), "sha256": analysis.digest(p.read_bytes()), "bytes": p.stat().st_size}
                               for p in sorted(self.folder.rglob("*")) if p.is_file() and p != self.index_path]
        self.index_path.write_bytes(raw(self.index))

    def analyze(self):
        return analysis.analyze_capture(self.index_path, self.trial, self.case, self.wheel,
                                        project_root=self.root, validator=lambda case, workspace: {"valid": True, "status": "passed"})


class AccountingTests(unittest.TestCase):
    def test_partial_call_subtotals_survive_incomplete_trial_totals(self):
        attempt = {key: None for key in analysis.METRICS}
        attempt["native_elapsed_s"], attempt["agent_elapsed_s"] = 107, 104
        attempt["token_measurements"] = {key: {"known_subtotal": value, "known_count": 2, "missing_count": 1}
                                          for key, value in (("input_tokens", 2638), ("cached_tokens", 2304), ("output_tokens", 3827))}
        attempt["cost_measurement"] = {"known_subtotal": .004, "known_count": 2, "missing_count": 1}
        result = analysis.trial_measurements([attempt])
        for key, value in (("input_tokens", 2638), ("cached_tokens", 2304), ("output_tokens", 3827), ("cost_usd", .004)):
            self.assertIsNone(result[key]["value"])
            self.assertEqual(result[key]["known_subtotal"], value)
            self.assertEqual(result[key]["missing_call_count"], 1)
        self.assertEqual(result["native_elapsed_s"]["value"], 107)

    def test_serialized_acknowledgement_is_not_counted_as_delivered(self):
        events = [{"kind": "tool_call", "name": name, "status": "completed", "model_call": index,
                   "raw": {"original_bytes": size, "bytes": size},
                   "visible": {"original_bytes": size // 2, "bytes": size // 2}}
                  for name, index, size in [("read_json", 1, 100), ("run_python", 2, 50), ("write_answer", 3, 20)]]
        result = analysis.tool_diagnostics(events, {"model_calls": [{}, {}, {}]})
        self.assertEqual(result["serialized_tool_bytes"]["visible_original"]["value"], 85)
        self.assertEqual(result["delivered_tool_bytes"]["visible_original"]["value"], 75)
        self.assertEqual(result["cumulative_delivered_tool_bytes"]["visible_original"]["value"], 125)
        self.assertEqual(result["delivered_tool_events"], 2)
        self.assertEqual(result["tool_name_counts"]["read_json"]["total"], 1)
        self.assertIsNone(analysis.tool_diagnostics(events, None)["delivered_tool_bytes"])

    def test_missing_usage_is_unknown_with_known_subtotal(self):
        calls = [native_call("a"), native_call("b")]
        metrics = complete_usage(calls)
        calls[1]["usage"]["input"] = None
        metrics["input_tokens"] = 100
        metrics["missing_calls"]["input"] = 1
        usage, _ = analysis.model_usage(calls, metrics, {})
        self.assertIsNone(usage["input_tokens"]["value"])
        self.assertEqual(usage["input_tokens"]["known_subtotal"], 100)
        self.assertEqual(usage["output_tokens"]["value"], 20)

    def test_missing_collector_invalidates_apparently_complete_usage(self):
        calls = [native_call()]
        usage, _ = analysis.model_usage(calls, complete_usage(calls), {"collector_complete": False})
        self.assertIsNone(usage["input_tokens"]["value"])

    def test_duplicate_call_or_impossible_cached_subset_rejected(self):
        calls = [native_call()]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            analysis.model_usage(calls * 2, {}, {})
        calls[0]["usage"]["cache_read"] = 101
        with self.assertRaisesRegex(ValueError, "Cached token"):
            analysis.model_usage(calls, complete_usage(calls), {})

    def test_settlement_counted_once_and_missing_settlement_unknown(self):
        accounting = {"calls": [{"call_id": "call", "admission": {"status": "settled", "cost_usd": .1},
                                 "accounting": {"record": {"generation": {"cost_usd": 900,
                                      "provider_responses": [{"status": 429}, {"status": 200}]}}}}]}
        count = analysis.settled_cost(accounting, [native_call()])
        self.assertEqual(count["value"], .1)
        self.assertEqual(count["provider_response_statuses"], {"429": 1, "200": 1})
        accounting["calls"][0]["admission"]["status"] = "reserved"
        self.assertIsNone(analysis.settled_cost(accounting, [native_call()])["value"])

    def test_failed_pair_never_claims_savings(self):
        common = {"case_id": "task/case", "replicate": "rep01", "input_tokens": 100}
        full = {**common, "condition": "full", "native_success": True, "performance_eligible": True}
        compact = {**common, "condition": "compact", "input_tokens": 1, "native_success": False, "performance_eligible": False}
        pair = analysis.paired_rows([full, compact])[0]
        self.assertIsNone(pair["input_tokens_ratio"])
        self.assertFalse(pair["both_successful_and_audited"])
        compact.update(native_success=True, performance_eligible=True)
        pair = analysis.paired_rows([full, compact])[0]
        self.assertEqual(pair["input_tokens_delta"], -99)
        _, summary = analysis.summaries([full, compact], [pair])
        self.assertEqual(summary[0]["paired_statistics"]["input_tokens"]["delta"]["mean"], -99)

    def test_duplicate_pair_identity_rejected(self):
        row = {"case_id": "case", "replicate": "r", "condition": "full"}
        with self.assertRaisesRegex(ValueError, "Duplicate paired"):
            analysis.paired_rows([row, row])


class ArchiveTests(unittest.TestCase):
    def test_only_selected_regular_records_read(self):
        records = analysis.read_tar_records(io.BytesIO(tar_bytes([("input.json", b"{}"), ("unrelated", b"ignored")])) )
        self.assertEqual(records, {"input.json": b"{}"})

    def test_traversal_links_and_duplicates_rejected(self):
        link = tarfile.TarInfo("link")
        link.type, link.linkname = tarfile.SYMTYPE, "input.json"
        bad = [tar_bytes([("../input.json", b"{}")]), tar_bytes([], link),
               tar_bytes([("input.json", b"1"), ("input.json", b"2")])]
        for data in bad:
            with self.subTest(data=data[:40]), self.assertRaises(ValueError):
                analysis.read_tar_records(io.BytesIO(data))

    def test_decompression_bound_enforced(self):
        with self.assertRaisesRegex(ValueError, "decompressed byte bound"):
            analysis.read_tar_records(io.BytesIO(tar_bytes([("unselected", b"x" * 20000)])), max_unpacked=10000)

    def test_json_duplicate_keys_and_overflows_rejected(self):
        for value in (b'{"x":1,"x":2}', b'{"x":1e999}', b'{"x":NaN}'):
            with self.assertRaises(ValueError):
                analysis.strict_json(value)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

    def test_complete_capture_identity_audit_and_usage(self):
        fixture = CaptureFixture(self.temporary.name)
        row, attempts = fixture.analyze()
        self.assertTrue(row["native_success"])
        self.assertTrue(row["performance_eligible"])
        self.assertEqual(row["input_tokens"], 100)
        self.assertEqual(row["cached_tokens"], 20)
        self.assertEqual(row["native_elapsed_s"], 1)
        self.assertEqual(row["agent_elapsed_s"], .5)
        self.assertEqual(attempts[0]["agent_tool_calls"], 2)

    def test_worker_retry_retained_missing_usage_not_zero(self):
        fixture = CaptureFixture(self.temporary.name, retry=True)
        row, attempts = fixture.analyze()
        self.assertTrue(row["native_success"])
        self.assertEqual(row["attempt_count"], 2)
        self.assertEqual(row["retry_count"], 1)
        self.assertIsNone(row["input_tokens"])
        self.assertEqual(row["measurements"]["input_tokens"]["known_subtotal"], 100)
        self.assertIsNone(row["cost_usd"])
        self.assertIsNone(row["agent_elapsed_s"])
        self.assertEqual(row["native_elapsed_s"], 3)
        self.assertIsNone(attempts[0]["native_verdict"])

    def test_unscored_worker_error_is_not_task_failure(self):
        fixture = CaptureFixture(self.temporary.name, verdict=None)
        row, _ = fixture.analyze()
        self.assertIsNone(row["native_success"])
        self.assertFalse(row["performance_eligible"])
        summary, _ = analysis.summaries([row], [])
        self.assertEqual(summary[0]["native_failures"], 0)
        self.assertEqual(summary[0]["native_unscored"], 1)

    def test_identity_mismatch_preserves_native_pass_excludes_efficiency(self):
        row, _ = CaptureFixture(self.temporary.name, identity=False).analyze()
        self.assertTrue(row["native_success"])
        self.assertFalse(row["performance_eligible"])
        self.assertFalse(row["identity_valid"])

    def test_tampered_capture_rejected_before_calculation(self):
        fixture = CaptureFixture(self.temporary.name)
        (fixture.folder / "run.json").write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "hash/size mismatch"):
            fixture.analyze()

    def test_unindexed_workspace_rejected(self):
        fixture = CaptureFixture(self.temporary.name)
        fixture.index["files"] = [e for e in fixture.index["files"] if not e["path"].endswith("workspace.tar.zst")]
        fixture.index_path.write_bytes(raw(fixture.index))
        with self.assertRaisesRegex(ValueError, "Workspace archive not covered"):
            fixture.analyze()

    def test_portable_original_root_rebound_without_rewriting_index(self):
        fixture = CaptureFixture(self.temporary.name)
        for entry in fixture.index["files"]:
            entry["path"] = "/old/project/" + entry["path"]
        fixture.index_path.write_bytes(raw(fixture.index))
        before = fixture.index_path.read_bytes()
        analysis.verify_capture(fixture.index_path, recorded_root="/old/project", project_root=fixture.root)
        self.assertEqual(fixture.index_path.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, "escapes"):
            analysis.project_path("/outside/file", recorded_root="/old/project", project_root=fixture.root)


class FreezeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "source.py").write_bytes(b"frozen source")
        wheel = io.BytesIO()
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("comp580_agent/source.py", b"frozen source")
        self.wheel_bytes = wheel.getvalue()
        (self.root / "wheel.whl").write_bytes(self.wheel_bytes)
        files = {"source.py": analysis.digest(b"frozen source")}
        modules = {"source.py": files["source.py"]}
        self.frozen = {"project_root": "/original/project", "logical_trial_count": 50,
                       "cases": [{"case_id": str(i)} for i in range(5)],
                       "source_tree": {"files": files, "sha256": analysis.digest(analysis.canonical(files))},
                       "wheel": {"path": "/original/project/wheel.whl", "sha256": analysis.digest(self.wheel_bytes),
                                 "package_modules_sha256": modules, "code_sha256": analysis.digest(analysis.canonical(modules))},
                       "trials": [{"trial_id": f"{i}/{condition}/{r}", "case_id": str(i), "condition": condition,
                                   "replicate": str(r), "request": {"idempotency_key": f"{i}/{condition}/{r}"}}
                                  for i in range(5) for condition in ("full", "compact") for r in range(5)]}
        self.rehash()

    def rehash(self):
        self.frozen["freeze_sha256"] = analysis.digest(analysis.canonical({k: v for k, v in self.frozen.items() if k != "freeze_sha256"}))
        self.progress = {"freeze_sha256": self.frozen["freeze_sha256"], "trials": {}}

    def test_portable_frozen_source_and_wheel_hashes_still_verified(self):
        analysis.verify_frozen(self.frozen, self.progress, project_root=self.root)
        (self.root / "source.py").write_bytes(b"changed source")
        with self.assertRaisesRegex(ValueError, "Frozen source or validator changed"):
            analysis.verify_frozen(self.frozen, self.progress, project_root=self.root)

    def test_progress_from_other_freeze_rejected(self):
        self.progress["freeze_sha256"] = "different"
        with self.assertRaisesRegex(ValueError, "Freeze/progress digest mismatch"):
            analysis.verify_frozen(self.frozen, self.progress, project_root=self.root)

    def test_archived_exact_wheel_preferred_over_rebuilt_dist(self):
        original = self.root / "wheel.whl"
        archived = self.root / "study/controlled/development/artifacts/wheel.whl"
        archived.parent.mkdir(parents=True)
        archived.write_bytes(original.read_bytes())
        original.unlink()
        result = analysis.verify_frozen(self.frozen, self.progress, project_root=self.root)
        self.assertEqual(result["wheel_source"], "retained_archive")
        self.assertEqual(result["wheel_path"], str(archived.resolve()))
        original.write_bytes(b"rebuilt wheel has different bytes")
        analysis.verify_frozen(self.frozen, self.progress, project_root=self.root)
        archived.write_bytes(b"tampered archive")
        with self.assertRaisesRegex(ValueError, "Frozen wheel changed"):
            analysis.verify_frozen(self.frozen, self.progress, project_root=self.root)

    def test_wheel_module_identity_independently_verified(self):
        self.frozen["wheel"]["package_modules_sha256"] = {"source.py": "incorrect-module-digest"}
        self.frozen["wheel"]["code_sha256"] = analysis.digest(analysis.canonical(self.frozen["wheel"]["package_modules_sha256"]))
        self.rehash()
        with self.assertRaisesRegex(ValueError, "wheel modules differ"):
            analysis.verify_frozen(self.frozen, self.progress, project_root=self.root)

    def test_unpaired_replicates_rejected_even_with_matching_hash(self):
        self.frozen["trials"][0]["replicate"] = "other-replicate"
        self.rehash()
        with self.assertRaisesRegex(ValueError, "same paired replicates"):
            analysis.verify_frozen(self.frozen, self.progress, project_root=self.root)


if __name__ == "__main__":
    unittest.main()
