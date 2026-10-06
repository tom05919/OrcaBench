import json
import tempfile
import unittest
from pathlib import Path

from scripts.select_stage3 import candidates, collect, confirmed, dose, first_per_task, repeats, replays, rescue


def ep(key, success=True, state="s", layout=1, changes=0, restarts=0, folder="f"):
    return {"key": key, "success": success, "state": state, "layout": layout, "changes": changes,
            "restarts": restarts, "folder": folder, "created_at": "t", "status": "x"}


def table(*episodes):
    return {e["key"]: e for e in episodes}


class SelectionRuleTests(unittest.TestCase):
    def test_first_per_task_varies_scenes_before_repeating_policy_seeds(self):
        keys = [("B", 1001, 0), ("A", 1001, 0), ("A", 1000, 1), ("A", 1000, 0), ("B", 1000, 0), ("A", 1002, 0)]
        self.assertEqual(first_per_task(keys, 2), [("A", 1000, 0), ("A", 1001, 0), ("B", 1000, 0), ("B", 1001, 0)])
        self.assertEqual(first_per_task(keys, 4)[:4], [("A", 1000, 0), ("A", 1001, 0), ("A", 1002, 0), ("A", 1000, 1)])

    def test_candidates_are_plain_successes_only(self):
        plain = table(ep(("A", 1000, 0)), ep(("A", 1000, 1), success=False), ep(("A", 1001, 0)))
        self.assertEqual(candidates(plain, 6), [("A", 1000, 0), ("A", 1001, 0)])

    def test_confirmed_needs_defer_success_and_the_identical_start(self):
        plain = table(*[ep(("A", 1000, p), state="x", layout=7) for p in range(5)])
        defer = table(
            ep(("A", 1000, 0), state="x", layout=7),                    # confirmed
            ep(("A", 1000, 1), success=False, state="x", layout=7),     # defer did not stay successful
            ep(("A", 1000, 2), state="y", layout=8),                    # a different kitchen
            ep(("A", 1000, 3), state="y", layout=7),                    # same kitchen, initial state differs
        )                                                                # ("A", 1000, 4) has no defer episode
        keys, dropped = confirmed(plain, defer, 4)
        self.assertEqual(keys, [("A", 1000, 0)])
        self.assertEqual(dropped, {("A", 1000, 1): "defer_failed", ("A", 1000, 2): "different_layout",
                                   ("A", 1000, 3): "initial_state_differs"})

    def test_confirmed_cap_applies_per_task_after_filtering(self):
        plain = table(*[ep(("A", 1000 + s, 0), state=str(s)) for s in range(4)])
        defer = table(*[ep(("A", 1000 + s, 0), state=str(s)) for s in range(4)])
        self.assertEqual(confirmed(plain, defer, 2)[0], [("A", 1000, 0), ("A", 1001, 0)])

    def test_repeats_cover_failures_and_any_intervention(self):
        llm = table(ep(("A", 1, 0)), ep(("B", 1, 0), success=False), ep(("C", 1, 0), changes=2), ep(("D", 1, 0), restarts=1))
        self.assertEqual(repeats(llm), [("B", 1, 0), ("C", 1, 0), ("D", 1, 0)])

    def test_dose_follows_tasks_where_an_arm_failed_and_is_capped(self):
        keys = [("A", 1, 0), ("A", 2, 0), ("B", 1, 0), ("C", 1, 0)]
        opus = table(ep(("A", 1, 0), success=False), ep(("B", 1, 0)))
        reissue = table(ep(("C", 1, 0), success=False))
        self.assertEqual(dose(keys, opus, reissue), [("A", 1, 0), ("A", 2, 0), ("C", 1, 0)])
        self.assertEqual(dose(keys, opus, reissue, max_pairs=2), [("A", 1, 0), ("A", 2, 0)])

    def test_replays_take_all_failures_and_the_earliest_prompt_changing_successes(self):
        episodes = [ep(("A", 1, 0), success=False, folder="a"), ep(("B", 2, 0), changes=1, folder="b"),
                    ep(("C", 3, 0), changes=1, folder="c"), ep(("D", 4, 0), folder="d")]
        self.assertEqual([e["folder"] for e in replays(episodes, 1)], ["a", "b"])


    def test_rescue_needs_a_scene_the_plain_policy_failed_every_time_at_least_twice(self):
        plain = table(ep(("A", 1000, 0), success=False), ep(("A", 1000, 1), success=False),   # fails repeatedly
                      ep(("A", 1001, 0), success=False), ep(("A", 1001, 1)),                  # mixed: not rescue
                      ep(("A", 1002, 0), success=False),                                      # one trial only
                      ep(("B", 1000, 3), success=False), ep(("B", 1000, 5), success=False))
        self.assertEqual(rescue(plain, 2), [("A", 1000, 0), ("B", 1000, 3)])


class CollectTests(unittest.TestCase):
    def write(self, root, name, scene, policy, success, created, state="h", status=None):
        folder = Path(root) / name
        (folder / "evaluator").mkdir(parents=True)
        (folder / "manifest.json").write_text(json.dumps({
            "artifact_type": "episode", "task": "A", "scene_seed": scene, "policy_seed": policy, "created_at": created}))
        (folder / "result.json").write_text(json.dumps({
            "status": status or ("success" if success else "step_budget_exhausted"), "success": success}))
        (folder / "evaluator" / "states.jsonl").write_text(json.dumps(
            {"step": 0, "state_sha256": state, "episode_metadata": {"layout_id": 41}}) + "\n")

    def test_latest_usable_episode_wins_and_infrastructure_errors_are_skipped(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "old", 1000, 0, False, "2026-10-05T01", state="a")
            self.write(root, "new", 1000, 0, True, "2026-10-05T02", state="b")
            self.write(root, "broken", 1001, 0, False, "2026-10-05T03", status="infrastructure_error")
            rows = collect([root])
            self.assertEqual(list(rows), [("A", 1000, 0)])
            self.assertTrue(rows[("A", 1000, 0)]["success"])
            self.assertEqual((rows[("A", 1000, 0)]["state"], rows[("A", 1000, 0)]["layout"]), ("b", 41))


if __name__ == "__main__":
    unittest.main()
