import copy
import tempfile
import unittest
from pathlib import Path

from robot_benchmark.cli import contract_payload, parse_seeds, resolve_audit_paths, validate_splits
from robot_benchmark.records import digest


class CliValidationTests(unittest.TestCase):
    def test_contract_payload_is_present_and_prompt_sensitive(self):
        task = {
            "schema_version": 2,
            "reference_prompts": [
                {
                    "id": "pick",
                    "prompt": "Pick the bowl.",
                    "description": "Diagnostic reference prompt.",
                    "performance": {"status": "untested"},
                }
            ],
        }
        policy = {"adapter": "fake-policy", "checkpoint": "pinned"}
        splits = {
            "development_seeds": [1],
            "qualification_seeds": [2],
            "evaluation_seeds": list(range(100, 120)),
        }

        payload = contract_payload(task, policy, splits)
        changed = copy.deepcopy(task)
        changed["reference_prompts"][0]["prompt"] = "Pick the cereal box."

        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["task_config"], task)
        self.assertEqual(payload["policy_identity"], policy)
        self.assertEqual(payload["splits"], splits)
        self.assertNotEqual(digest(payload), digest(contract_payload(changed, policy, splits)))

    def test_seed_sets_must_be_unique_and_bounded(self):
        self.assertEqual(parse_seeds("1,2,3"), [1, 2, 3])
        for value in ("1,1", "-1", str(2**32), "one"):
            with self.subTest(value=value), self.assertRaises(Exception):
                parse_seeds(value)

    def test_audit_paths_must_be_relative_and_cannot_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = root.resolve() / "runs" / "trace.jsonl"
            self.assertEqual(resolve_audit_paths(["runs/trace.jsonl"], root), [expected])
            with self.assertRaisesRegex(ValueError, "project-relative"):
                resolve_audit_paths([str(expected)], root)
            with self.assertRaisesRegex(ValueError, "stay under"):
                resolve_audit_paths(["../outside.jsonl"], root)

    def test_split_sets_are_unique_disjoint_and_have_twenty_evaluation_seeds(self):
        valid = {
            "development_seeds": [1],
            "qualification_seeds": [2],
            "evaluation_seeds": list(range(100, 120)),
        }
        self.assertIs(validate_splits(valid), valid)

        overlapping = {**valid, "qualification_seeds": [1]}
        with self.assertRaisesRegex(ValueError, "disjoint"):
            validate_splits(overlapping)
        too_small = {**valid, "evaluation_seeds": list(range(100, 119))}
        with self.assertRaisesRegex(ValueError, "at least 20"):
            validate_splits(too_small)


if __name__ == "__main__":
    unittest.main()
