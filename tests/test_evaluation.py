import json
import tempfile
import unittest
from pathlib import Path

from robot_benchmark.evaluation import summarize


def write_episode(root, name, *, model, seed, status, success, kind="llm", agent=True):
    episode = root / name
    episode.mkdir()
    manifest = {
        "artifact_type": "episode",
        "contract_hash": "contract",
        "agent": {"model": model} if agent else None,
        "kind": kind,
        "seed": seed,
    }
    result = {
        "status": status,
        "success": success,
        "physical_success_any": success,
        "physical_success_final": success,
        "false_completion": False,
        "steps": 12,
        "model_calls": 3,
        "policy_calls": 2,
        "switches": 1,
        "retries": 2,
        "interrupts": 0,
        "intervals": [4, 8],
        "model_seconds": 1.5,
        "policy_seconds": 2.5,
        "wall_seconds": 4.5,
        "usage": [{"input_tokens": 10, "output_tokens": 2}],
    }
    (episode / "manifest.json").write_text(json.dumps(manifest))
    (episode / "result.json").write_text(json.dumps(result))


class EvaluationTests(unittest.TestCase):
    def test_summary_reports_protocol_metrics_and_paired_outcomes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_episode(root, "a-1", model="model-a", seed=1, status="success", success=True)
            write_episode(root, "a-2", model="model-a", seed=2, status="false_completion", success=False)
            write_episode(root, "b-1", model="model-b", seed=1, status="false_completion", success=False)
            write_episode(root, "b-2", model="model-b", seed=2, status="success", success=True)

            report = summarize(root)

            group = next(row for row in report["groups"] if row["model"] == "model-a")
            self.assertEqual(group["success_rate"], 0.5)
            self.assertEqual(group["total_steps"], 24)
            self.assertEqual(group["total_model_calls"], 6)
            self.assertEqual(group["interval_histogram"], {"4": 2, "8": 2})
            self.assertEqual(group["token_usage_totals"], {"input_tokens": 20, "output_tokens": 4})
            paired = report["paired_comparisons"][0]
            self.assertEqual(paired["paired_seeds"], [1, 2])
            self.assertEqual((paired["left_only_success"], paired["right_only_success"]), (1, 1))

    def test_infrastructure_attempt_stays_visible_and_null_agent_is_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_episode(
                root,
                "setup-error",
                model="unused",
                seed=4,
                status="infrastructure_error",
                success=False,
                kind="llm_development",
                agent=False,
            )

            group = summarize(root)["groups"][0]

            self.assertEqual(group["model"], "setup_pending")
            self.assertEqual((group["attempted"], group["usable"]), (1, 0))
            self.assertEqual(group["infrastructure_errors"], 1)

    def test_duplicate_seed_for_same_model_and_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_episode(root, "first", model="model-a", seed=1, status="success", success=True)
            write_episode(root, "second", model="model-a", seed=1, status="success", success=True)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                summarize(root)


if __name__ == "__main__":
    unittest.main()
