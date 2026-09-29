import unittest

from robot_benchmark.feasibility import public_task_config, qualification_config_view, qualification_report
from robot_benchmark.records import digest


SKILLS = ("open_cabinet", "transfer_cereal", "transfer_bowl", "close_cabinet")
CONDITIONS = ("nominal_entry", "natural_intermediate")


def evidence(successes=8, trials=10, *, relevance=True):
    return {
        "contract_hash": "a" * 64,
        "policy_backend": "groot",
        "checkpoint_manifest_sha256": "b" * 64,
        "skill_conditions": [
            {
                "skill": skill,
                "condition": condition,
                "successes": successes,
                "trials": trials,
                "trace_paths": [f"runs/{skill}-{condition}.jsonl"],
                "duration_steps": {"min": 10, "median": 20, "max": 30},
                "limitations": [f"observed limitation for {skill}"],
            }
            for skill in SKILLS
            for condition in CONDITIONS
        ],
        "full_task": {
            "successes": 16,
            "trials": 20,
            "trace_paths": ["runs/full-task.jsonl"],
        },
        "supervisory_relevance": {
            "verified": relevance,
            "paired_trace_paths": ["runs/paired.jsonl"] if relevance else [],
        },
    }


class QualificationReportTests(unittest.TestCase):
    def test_pass_requires_each_condition_full_task_and_relevance(self):
        report = qualification_report(evidence())

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["contract_hash"], "a" * 64)
        self.assertEqual(report["checkpoint_manifest_sha256"], "b" * 64)
        self.assertEqual(len(report["skill_conditions"]), 8)
        self.assertIsNotNone(report["full_task"]["wilson_95"])

    def test_missing_or_short_condition_is_insufficient_evidence(self):
        missing = evidence()
        missing["skill_conditions"].pop()
        self.assertEqual(qualification_report(missing)["status"], "insufficient_evidence")

        short = evidence(trials=9)
        self.assertEqual(qualification_report(short)["status"], "insufficient_evidence")

        no_identity = evidence()
        no_identity["contract_hash"] = None
        self.assertEqual(qualification_report(no_identity)["status"], "insufficient_evidence")
        self.assertEqual(qualification_report(no_identity)["missing_identity"], ["contract_hash"])

        no_card = evidence()
        no_card["skill_conditions"][0].pop("duration_steps")
        report = qualification_report(no_card)
        self.assertEqual(report["status"], "insufficient_evidence")
        self.assertIn("open_cabinet:nominal_entry:performance_card", report["missing_metadata"])

    def test_complete_below_threshold_fails_before_relevance(self):
        weak = evidence(successes=7, relevance=False)
        self.assertEqual(qualification_report(weak)["status"], "failed")

    def test_passing_counts_without_matched_continuations_are_pending(self):
        self.assertEqual(
            qualification_report(evidence(relevance=False))["status"],
            "pending_relevance",
        )

    def test_duplicate_and_invalid_counts_are_rejected(self):
        duplicate = evidence()
        duplicate["skill_conditions"].append(dict(duplicate["skill_conditions"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            qualification_report(duplicate)

        invalid = evidence()
        invalid["skill_conditions"][0]["successes"] = 11
        with self.assertRaisesRegex(ValueError, "invalid skill counts"):
            qualification_report(invalid)

    def test_public_task_config_contains_performance_but_no_private_trace_paths(self):
        report = qualification_report(evidence())
        base = {
            "status": "development_unqualified",
            "task": "CerealAndBowl",
            "reference_prompts": [
                {"id": skill, "prompt": skill, "description": skill,
                 "performance": {"status": "untested"}}
                for skill in SKILLS
            ],
        }

        published = public_task_config(base, report, digest(report))

        self.assertEqual(published["status"], "qualified_candidate")
        self.assertEqual(published["policy_backend"], "groot")
        self.assertEqual(published["reference_prompts"][0]["performance"]["trials"], 20)
        self.assertNotIn("trace_paths", repr(published))
        self.assertEqual(qualification_config_view(base), qualification_config_view(published))


if __name__ == "__main__":
    unittest.main()
