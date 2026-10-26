import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

from test_time_score import COMPLETE, SCRIPTED, episode, run

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONFIG = {"call_seconds": {"claude-opus-5-5": 4.7, "claude-sonnet-5-5": 2.2}, "tasks": {
    "Iced": {"deadline_seconds": 150.0, "story": {"text": "Ice melts.", "clock_starts": "ice_out", "limit_seconds": None}},
    "Warm": {"deadline_seconds": 100.0, "story": {"text": "It cools.", "clock_starts": "step0", "limit_seconds": None}},
    "Plain": {"deadline_seconds": 50.0},
}}


class StoryLimitTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.limits = load("set_story_limits")

    def run_ep(self, name, task, backend, first_success, trigger=None, logged=True, steps=600):
        truth = [False] * steps + [False] if first_success is None else [False] * first_success + [True]
        n = len(truth)
        extra = {"ice_out": [i >= trigger for i in range(n)] if trigger is not None else [False] * n} if logged else None
        return episode(self.root, name, task=task, kind="diagnostic_reference", agent=SCRIPTED, backend=backend,
                       steps=n - 1, truth=truth, extra=extra, success=first_success is not None)

    def test_limit_is_slowest_qualifying_median_plus_three_slowest_calls(self):
        runs = [self.run_ep(f"a{i}", "Iced", "a", first, trigger=100) for i, first in enumerate((300, 400, 500))]
        runs.append(self.run_ep("b0", "Iced", "b", 900, trigger=100))  # one success only: does not qualify
        runs.append(self.run_ep("a_fail", "Iced", "a", None, trigger=100))
        out = self.limits.story_limits(runs, CONFIG, ["a", "b"])["Iced"]
        self.assertEqual(out["medians"], {"a": 15.0})  # (400 - 100) / 20
        self.assertEqual(out["limit_seconds"], 30)  # 15 + 3 x 4.7 = 29.1, rounded up to 5 s
        self.assertEqual(out["successes_and_runs"]["a"], (3, 4))
        self.assertTrue(out["binds"])

    def test_step0_clock_and_missing_trigger(self):
        warm = [self.run_ep(f"w{i}", "Warm", "a", first, logged=False) for i, first in enumerate((200, 400))]
        self.assertEqual(self.limits.story_limits(warm, CONFIG, ["a"])["Warm"]["limit_seconds"], 30)  # 15 + 14.1
        unlogged = [self.run_ep(f"u{i}", "Iced", "a", 300, logged=False) for i in range(3)]
        self.assertIsNone(self.limits.story_limits(unlogged, CONFIG, ["a"])["Iced"]["limit_seconds"])

    def test_writing_drops_a_story_with_no_limit(self):
        raw = copy.deepcopy(CONFIG)
        dropped = self.limits.apply_limits(raw, {"Iced": {"limit_seconds": None}, "Warm": {"limit_seconds": 30}})
        self.assertEqual(dropped, ["Iced"])
        self.assertNotIn("story", raw["tasks"]["Iced"])  # the supervisor is not told of a clock that never counts
        self.assertEqual(raw["tasks"]["Iced"]["deadline_seconds"], 150.0)
        self.assertEqual(raw["tasks"]["Warm"]["story"]["limit_seconds"], 30)


class SessionPlanTests(unittest.TestCase):
    def test_plans_cover_every_cell_once_in_policy_blocks_with_hidden_labels(self):
        plans = load("make_session_plans").make_plans(["p1", "p2", "p3"], ["A", "B"], [1000, 1001], 0, seed=7)
        self.assertEqual(sorted(plans), ["scene1000", "scene1001"])
        for name, order in plans.items():
            self.assertEqual(len(order), 6)
            self.assertEqual({(e["backend"], e["task"]) for e in order},
                             {(p, t) for p in ("p1", "p2", "p3") for t in ("A", "B")})
            for block in (order[:3], order[3:]):
                self.assertEqual({e["backend"] for e in block}, {"p1", "p2", "p3"})
                self.assertEqual(len({e["task"] for e in block}), 1)
            labels = {e["backend"]: e["policy_label"] for e in order}
            self.assertEqual(sorted(labels.values()), ["K", "R", "T"])
            self.assertTrue(all(e["policy_label"] == labels[e["backend"]] for e in order))
        again = load("make_session_plans").make_plans(["p1", "p2", "p3"], ["A", "B"], [1000, 1001], 0, seed=7)
        self.assertEqual(plans, again)


class SelectionTests(unittest.TestCase):
    @staticmethod
    def ladder(rates):
        return {b: {"tasks": {t: {"successes": s, "usable": 8} for t, s in tasks.items()}} for b, tasks in rates.items()}

    def setUp(self):
        self.select = load("select_final").select
        unseen = {"MakeIceLemonade": 2, "PortionHotDogs": 1, "GarnishPancake": 3, "ArrangeTea": 2, "PanTransfer": 0}
        seen = {"OpenCabinet": 8, "OpenDrawer": 6, "CloseFridge": 5, "PickPlaceCounterToCabinet": 7,
                "PickPlaceCounterToStove": 3}
        scale = {"groot": 1.0, "groot_u10": 0.5, "groot_u30": 2.0, "pi05": 1.0, "groot_pretrain": 0.0}
        self.data = self.ladder({b: {t: min(8, round(s * k)) for t, s in (unseen | seen).items()}
                                 for b, k in scale.items()})

    def test_helpable_story_tasks_first_and_widest_policy_spread(self):
        ceiling = {"groot": {"PortionHotDogs": {"plain": [1, 8], "sequencer": [5, 8]},
                             "ArrangeTea": {"plain": [2, 8], "sequencer": [6, 8]},
                             "GarnishPancake": {"plain": [3, 8], "sequencer": [5, 8]},
                             "MakeIceLemonade": {"plain": [2, 8], "sequencer": [3, 8]}},
                   "groot_pretrain": {"PanTransfer": {"plain": [0, 8], "sequencer": [8, 8]}}}  # excluded policy
        choice = self.select(self.data, ceiling)
        self.assertFalse(choice["fallback_monitoring"])
        self.assertEqual(choice["unseen_tasks"], ["PortionHotDogs", "GarnishPancake", "ArrangeTea"])
        self.assertEqual(choice["story_tasks"], ["PortionHotDogs", "GarnishPancake"])
        self.assertEqual(set(choice["policies"]), {"groot_u10", "groot", "groot_u30"})  # pi05 ties groot: less spread
        self.assertNotIn("groot_pretrain", choice["policies"])
        self.assertEqual(choice["seen_tasks"], ["OpenCabinet", "PickPlaceCounterToCabinet", "OpenDrawer"])

    def test_explicit_policies_replace_rule_two_and_untested_ones_stay_null(self):
        ceiling = {"groot": {"PortionHotDogs": {"pairs": 8, "plain_successes": 1, "sequencer_successes": 2}}}
        choice = self.select(self.data, ceiling, ["groot", "groot_u30", "newpolicy"])
        self.assertEqual(choice["policies"], ["groot", "groot_u30", "newpolicy"])
        self.assertIsNone(choice["policy_unseen_success"]["newpolicy"])
        self.assertEqual(choice["untested_policies"], ["newpolicy"])
        self.assertTrue(choice["fallback_monitoring"])  # W2's real ceiling format, margin 1 < 2

    def test_fallback_to_monitoring_when_fewer_than_two_tasks_are_helpable(self):
        ceiling = {"groot": {"PortionHotDogs": {"plain": [1, 8], "sequencer": [3, 8]}}}
        choice = self.select(self.data, ceiling)
        self.assertTrue(choice["fallback_monitoring"])
        self.assertEqual(choice["unseen_tasks"][0], "PortionHotDogs")
        self.assertEqual(len(choice["unseen_tasks"]), 4)
        self.assertNotIn("PanTransfer", choice["unseen_tasks"])  # no plain success anywhere


class PrimaryResultTests(unittest.TestCase):
    def test_clustered_bootstrap_and_model_difference(self):
        score_time = load("score_time")
        rows = lambda shift: [{"task": t, "scene": s, "paired_regret_heldout": shift + 0.1 * s}
                              for t in ("A", "B") for s in (0, 1, 2) for _ in range(3)]
        result = score_time.clustered_bootstrap(rows(0.2), "paired_regret_heldout")
        self.assertEqual((result["episodes"], result["clusters"]), (18, 6))
        self.assertAlmostEqual(result["mean"], 0.3)
        self.assertLessEqual(result["ci95"][0], 0.3)
        self.assertGreaterEqual(result["ci95"][1], 0.3)
        diff = score_time.difference(rows(0.5), rows(0.2), "paired_regret_heldout")
        self.assertAlmostEqual(diff["mean"], 0.3)
        self.assertAlmostEqual(diff["ci95"][0], 0.3)  # a constant shift: no spread across clusters
        cells = {("m1", "b", "A"): rows(0.5), ("m2", "b", "A"): rows(0.2)}
        self.assertIn("m1 - m2", score_time.primary(cells)["differences"])

    def test_paired_heldout_regret_uses_the_same_root_twin_and_a_step_chosen_without_its_scene(self):
        score_time = load("score_time")
        pod, other_pod = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        for scene, first in ((1000, 200), (1001, 300), (1002, 400)):  # always-defer twins: checker true from `first`
            episode(pod, f"twin{scene}", kind="baseline_always_defer", agent=SCRIPTED, steps=999,
                    truth=[False] * first + [True] * (1000 - first), scene_seed=scene)
        # Held-out steps: 400 for scenes 1000 and 1001 (chosen on the other two), 300 for 1002, where its twin is
        # not yet successful. Twin values 0.6, 0.6 and 0; model values 1 - (15 + 2 x 4.7) / 50, 0 and 1 - 39.1 / 50.
        episode(pod, "llm1000", steps=300, model_calls=2, decisions=[COMPLETE(300)], scene_seed=1000)
        episode(pod, "llm1001", steps=100, success=False, false_completion=True, model_calls=2,
                decisions=[COMPLETE(100)], scene_seed=1001)
        episode(pod, "llm1002", steps=500, model_calls=3, decisions=[COMPLETE(500)], scene_seed=1002)
        episode(pod, "llm_infra", steps=50, success=False, model_calls=1, scene_seed=1000,
                infrastructure_error={"type": "frame_noise"})
        episode(other_pod, "llm_other_pod", steps=300, model_calls=2, scene_seed=1000)  # no twin on its own pod
        _, cells = score_time.score(score_time.load([pod, other_pod]), CONFIG, {"Plain": 1000})
        rows = sorted(cells[("claude-opus-5-5", "groot", "Plain")], key=lambda r: r["scene"])
        self.assertEqual(len(rows), 4)  # the infrastructure error is not scored
        paired = [r for r in rows if "paired_regret_heldout" in r]
        self.assertEqual([r["scene"] for r in paired], [1000, 1001, 1002])
        for row, expected in zip(paired, (0.6 - 0.512, 0.6, 0.0 - 0.218)):
            self.assertAlmostEqual(row["paired_regret_heldout"], expected)
        self.assertAlmostEqual(paired[2]["paired_regret"], 0.6 - 0.218)  # hindsight step 400 on every twin
        result = score_time.primary(cells)["per_model"]["claude-opus-5-5"]
        self.assertEqual((result["mean"], result["episodes"], result["clusters"]), (0.157, 3, 3))
        kept = score_time.load([pod, other_pod], scenes=[1000, 1001])
        self.assertEqual(sorted({e["scene_seed"] for e in kept}), [1000, 1001])
        self.assertEqual(len(kept), 6)  # two twins and four model episodes (one an infrastructure error)

    def test_task_type_breakdown_counts_successes_twins_and_rewrites(self):
        breakdown = load("task_type_breakdown").breakdown
        pod = Path(tempfile.mkdtemp())
        for scene, first in ((1000, 200), (1001, 300), (1002, 400)):
            episode(pod, f"twin{scene}", kind="baseline_always_defer", agent=SCRIPTED, steps=999,
                    truth=[False] * first + [True] * (1000 - first), scene_seed=scene)
        episode(pod, "llm1000", steps=300, model_calls=2, decisions=[run(0, 300, "go"), COMPLETE(300)],
                scene_seed=1000)
        episode(pod, "llm1001", steps=100, success=False, false_completion=True, model_calls=2, prompt_changes=1,
                decisions=[run(0, 100, "go"), COMPLETE(100)], scene_seed=1001)
        episode(pod, "llm1002", steps=500, model_calls=3,
                decisions=[run(0, 300, "go"), run(300, 200), COMPLETE(500)], scene_seed=1002)
        selection = {"seen_tasks": ["Plain"], "unseen_tasks": ["Warm"]}
        cell = breakdown(load("score_time").load([pod]), CONFIG, selection, {"Plain": 1000})[
            ("claude-opus-5-5", "leave-alone")]
        self.assertEqual((cell["episodes"], cell["successes"], cell["successes_with_value"]), (3, 2, 2))
        self.assertEqual((cell["twins"], cell["twin_successes"]), (3, 3))
        self.assertEqual((cell["no_rewrite"], cell["rewrote"]), ([2, 2], [0, 1]))
        self.assertAlmostEqual(cell["timer_value"], 0.4)  # held-out twin values 0.6, 0.6 and 0
        self.assertEqual(cell["declarations"], {"correct": 2, "false: not reached yet": 1})
        # The false "done" at step 100 of scene 1001 came 200 steps before its twin's first success at 300.
        self.assertEqual((cell["early_declarations"], cell["early_median_seconds"]), (1, 10.0))
        self.assertEqual(cell["twin_done_before_false_declaration"], 0)
        self.assertEqual(cell["first_interval"], {300: 2, 100: 1})


if __name__ == "__main__":
    unittest.main()
