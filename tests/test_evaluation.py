import json
import tempfile
import unittest
from pathlib import Path

from robot_benchmark.evaluation import summarize


def write_episode(root, name, *, model, seed, status, success, kind="llm", agent=True, policy_seed=None):
    episode = root / name
    episode.mkdir()
    manifest = {
        "artifact_type": "episode",
        "contract_hash": "contract",
        "agent": {"model": model} if agent else None,
        "kind": kind,
        "seed": seed,
    }
    if policy_seed is not None:
        manifest["policy_seed"] = policy_seed
    result = {
        "status": status,
        "success": success,
        "physical_success_any": success,
        "physical_success_final": success,
        "false_completion": False,
        "steps": 12,
        "model_calls": 3,
        "policy_calls": 2,
        "prompt_submissions": 3,
        "prompt_changes": 1,
        "prompt_restarts": 1,
        "discarded_actions": 4,
        "intervals": [4, 8],
        "model_seconds": 1.5,
        "policy_seconds": 2.5,
        "simulated_seconds": 0.6,
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
            self.assertEqual(group["prompt_submissions"], 6)
            self.assertEqual(group["prompt_changes"], 2)
            self.assertEqual(group["prompt_restarts"], 2)
            self.assertEqual(group["discarded_actions"], 8)
            self.assertEqual(group["interval_histogram"], {"4": 2, "8": 2})
            self.assertEqual(group["token_usage_totals"], {"input_tokens": 20, "output_tokens": 4})
            self.assertAlmostEqual(group["simulated_seconds"], 1.2)
            self.assertAlmostEqual(group["mean_simulated_seconds"], 0.6)
            self.assertAlmostEqual(group["mean_wall_seconds"], 4.5)
            self.assertAlmostEqual(group["mean_model_seconds"], 1.5)
            paired = report["paired_comparisons"][0]
            self.assertEqual(paired["paired_seeds"], [[1, 1], [2, 2]])
            self.assertEqual((group["seeds"], group["usable_seeds"]), ([[1, 1], [2, 2]], [[1, 1], [2, 2]]))
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


    def test_duplicates_are_keyed_by_scene_and_policy_seed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_episode(root, "p0", model="model-a", seed=1, policy_seed=0, status="success", success=True)
            write_episode(root, "p1", model="model-a", seed=1, policy_seed=1, status="success", success=True)
            self.assertEqual(summarize(root)["groups"][0]["attempted"], 2)
            write_episode(root, "p1-again", model="model-a", seed=1, policy_seed=1, status="success", success=True)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                summarize(root)

    def test_paired_comparison_keeps_policy_seeds_apart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for model, winner in (("model-a", 0), ("model-b", 1)):
                for policy_seed in (0, 1):
                    write_episode(root, f"{model}-p{policy_seed}", model=model, seed=1, policy_seed=policy_seed,
                                  status="success" if policy_seed == winner else "false_completion",
                                  success=policy_seed == winner)
            paired = summarize(root)["paired_comparisons"][0]
            self.assertEqual(paired["paired_seeds"], [[1, 0], [1, 1]])
            self.assertEqual((paired["paired_n"], paired["left_only_success"], paired["right_only_success"]), (2, 1, 1))


if __name__ == "__main__":
    unittest.main()
