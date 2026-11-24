"""Offline regression checks. Run with the installed NanoAgent Python, -I -B.

Imports original and patched COPY files only. Never writes to installed runtime,
loads credentials, invokes a plugin tool/verifier, or makes model/network calls.
"""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

from nanoagent.uploaded.contract import ContractError

HERE = Path(__file__).resolve().parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


BEFORE = module("platform_fix_before", "outcome.before.py")
AFTER = module("platform_fix_after", "outcome.patched.py")


def object_schema(value):
    return {"type": "object", "properties": {"field": value}}


class SkeletonFixTests(unittest.TestCase):
    def test_copy_fingerprints_and_pinned_source_identity(self):
        meta = json.loads((HERE / "provenance.json").read_text())
        sha = lambda name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
        self.assertEqual(sha("outcome.before.py"), meta["installed_before_sha256"])
        self.assertEqual(sha("outcome.patched.py"), meta["patched_sha256"])
        self.assertEqual(sha("actual-output-schemas.json"), meta["schemas_sha256"])
        self.assertEqual(meta["installed_before_sha256"], meta["pinned_before_sha256"])

    def test_nonempty_scalar_enum_is_unfilled_null_not_first_value(self):
        for values in (["x", "y"], [1, 2], [1.5, 2.5], [True, False], [None], ["x", 1, None, False]):
            with self.subTest(values=values):
                schema = object_schema({"enum": values})
                with self.assertRaises(ContractError):
                    BEFORE.answer_skeleton(schema)
                self.assertEqual(AFTER.answer_skeleton(schema), {"field": None})

    def test_enum_shape_unknown_or_invalid_values_remain_rejected(self):
        for values in ([], "x", None, {}, [{"x": "y"}], [[1]], ["x", {}], [float("inf")], [float("nan")]):
            with self.subTest(values=values), self.assertRaisesRegex(ContractError, r"\$\.field:"):
                AFTER.answer_skeleton(object_schema({"enum": values}))

    def test_type_and_union_behavior_is_unchanged(self):
        unsupported = [
            {"type": "unknown", "enum": ["x"]}, {"const": "x"}, {},
            {"anyOf": [{"enum": ["x"]}, {"type": "integer"}]},
            {"oneOf": [{"enum": ["x"]}, {"enum": ["y"]}]},
            {"type": ["string", "integer"], "enum": ["x"]},
        ]
        for value in unsupported:
            with self.subTest(value=value):
                for implementation in (BEFORE, AFTER):
                    with self.assertRaises(ContractError):
                        implementation.answer_skeleton(object_schema(value))
        supported = [
            {"type": "string", "enum": ["x"]},
            {"type": "object", "properties": {"x": {"type": "boolean"}}},
            {"type": "array", "items": {"enum": ["x"]}},
            {"type": ["string", "null"]},
            {"anyOf": [{"enum": ["x"]}, {"type": "null"}]},
        ]
        for value in supported:
            with self.subTest(value=value):
                self.assertEqual(BEFORE.answer_skeleton(object_schema(value)), AFTER.answer_skeleton(object_schema(value)))

    def test_reference_resolves_scalar_enum_but_missing_and_recursive_stay_errors(self):
        schema = object_schema({"$ref": "#/$defs/choice"})
        schema["$defs"] = {"choice": {"enum": ["x", "y"]}}
        self.assertEqual(AFTER.answer_skeleton(schema), {"field": None})
        for reference in ("#/$defs/missing", "#"):
            with self.subTest(reference=reference), self.assertRaises(ContractError):
                AFTER.answer_skeleton(object_schema({"$ref": reference}))

    def test_root_still_requires_object(self):
        for schema in ({"enum": ["x"]}, {"type": "array"}, {"type": "string"}):
            with self.subTest(schema=schema), self.assertRaisesRegex(ContractError, "must describe an object"):
                AFTER.answer_skeleton(schema)

    def test_all_five_actual_compiler_schemas_fail_before_and_seed_after(self):
        records = json.loads((HERE / "actual-output-schemas.json").read_text())["schemas"]
        self.assertEqual(len(records), 5)
        expected = {
            "log-triage": {"case": None, "fault": None, "evidence": None},
            "cipher-crack": {"case": None, "key": None, "plaintext": None},
            "path-probe": {"case": None, "route": [], "cost": None},
            "regex-infer": {"case": None, "pattern": None},
            "stat-pick": {"case": None, "statistic": None, "value": None},
        }
        for record in records:
            with self.subTest(plugin=record["plugin"]):
                schema = record["output_schema"]
                original = copy.deepcopy(schema)
                with self.assertRaisesRegex(ContractError, r"\$\.case:") as caught:
                    BEFORE.answer_skeleton(schema)
                self.assertEqual(str(caught.exception), record["before_error"])
                skeleton = AFTER.answer_skeleton(schema)
                self.assertEqual(skeleton, expected[record["plugin"]])
                self.assertEqual(json.loads(AFTER.answer_text(skeleton)), expected[record["plugin"]])
                self.assertEqual(schema, original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
