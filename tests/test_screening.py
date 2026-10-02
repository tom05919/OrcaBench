import json
import tempfile
import unittest
from pathlib import Path

from robot_benchmark.evaluation import wilson_interval
from robot_benchmark.screening import freeze_release, label_seeds, load_episodes, native_card_performance

KINDS = {"reference": "diagnostic_reference", "retry": "diagnostic_retry", "sequencer": "diagnostic_sequencer"}


def eps(task, scene, kind, outcomes, first_policy_seed=0):
    """Synthetic (manifest, result) tuples; outcomes are True/False/None (None = infrastructure error)."""
    rows = []
    for i, ok in enumerate(outcomes):
        manifest = {"artifact_type": "episode", "kind": KINDS[kind], "task": task, "seed": scene,
                    "scene_seed": scene, "policy_seed": first_policy_seed + i}
        result = {"status": "infrastructure_error" if ok is None else "success" if ok else "step_budget_exhausted",
                  "success": bool(ok), "prompt_submissions": 2 if kind == "retry" else 1}
        rows.append((manifest, result))
    return rows


def seed_eps(task, scene, reference, retry=(), sequencer=()):
    return eps(task, scene, "reference", reference) + eps(task, scene, "retry", retry) + eps(task, scene, "sequencer", sequencer)


SEEDS = [0, 1, 2, 3, 4]
LEAVE = [True] * 5
HELP = [False] * 5
RESCUE = [True, True, False, False, False]


def group_of(groups, task, scene):
    return groups["tasks"][task]["scene_seeds"][str(scene)]


class LabelTests(unittest.TestCase):
    def test_each_group_and_pairs(self):
        episodes = (seed_eps("T", 1, LEAVE) + seed_eps("T", 2, [True] * 4 + [False])
                    + seed_eps("T", 3, HELP, retry=RESCUE) + seed_eps("T", 4, [True, False, False, False, False], sequencer=RESCUE)
                    + seed_eps("T", 5, [True, False, False, False, False], retry=[True, False, False, False, False])
                    + seed_eps("T", 6, [True, True, True, False, False]) + seed_eps("T", 7, HELP))
        groups = label_seeds(episodes, SEEDS)
        got = {s: group_of(groups, "T", s)["group"] for s in range(1, 8)}
        self.assertEqual(got, {1: "leave_alone", 2: "leave_alone", 3: "needs_help", 4: "needs_help",
                               5: "medium", 6: "medium", 7: "medium"})
        self.assertEqual(group_of(groups, "T", 3), {"group": "needs_help", "reference": [0, 5], "retry": [2, 5], "sequencer": [0, 0]})
        self.assertEqual(groups["schema_version"], 1)
        self.assertEqual(groups["screening_policy_seeds"], SEEDS)
        self.assertEqual(groups["thresholds"], {"trials": 5, "leave_alone_min": 4, "needs_help_max": 1, "rescue_min": 2,
                                                "min_per_group": 2, "max_per_group": 4})

    def test_retry_success_without_reprompt_is_a_trial_not_a_rescue(self):
        retry = eps("T", 1, "retry", RESCUE)
        retry[1][1]["prompt_submissions"] = 1  # succeeded on the first prompt: same evidence as the reference
        groups = label_seeds(seed_eps("T", 1, HELP) + retry, SEEDS)
        self.assertEqual((group_of(groups, "T", 1)["group"], group_of(groups, "T", 1)["retry"]), ("medium", [1, 5]))
        retry[1][1]["prompt_submissions"] = 3
        self.assertEqual(group_of(label_seeds(seed_eps("T", 1, HELP) + retry, SEEDS), "T", 1)["retry"], [2, 5])

    def test_pending_below_five_usable_reference_trials(self):
        groups = label_seeds(seed_eps("T", 1, [True] * 4) + seed_eps("T", 2, [True] * 4 + [None]), SEEDS)
        self.assertEqual(group_of(groups, "T", 1)["group"], "pending")
        self.assertEqual(group_of(groups, "T", 2)["group"], "pending")
        self.assertEqual(group_of(groups, "T", 2)["reference"], [4, 4])

    def test_infrastructure_errors_not_counted(self):
        # 3 usable successes + errors would be leave_alone if errors counted as trials; rescue needs >=5 usable retry trials
        episodes = seed_eps("T", 1, HELP, retry=[True, True, None, None, None])
        self.assertEqual(group_of(label_seeds(episodes, SEEDS), "T", 1)["group"], "medium")
        self.assertEqual(group_of(label_seeds(episodes, SEEDS), "T", 1)["retry"], [2, 2])

    def test_other_kinds_and_policy_seeds_ignored(self):
        llm = eps("T", 1, "reference", [True] * 5)
        for manifest, _ in llm:
            manifest["kind"] = "llm"
        episodes = seed_eps("T", 1, HELP) + eps("T", 1, "reference", [True] * 5, first_policy_seed=5) + llm
        groups = label_seeds(episodes, SEEDS)
        self.assertEqual(group_of(groups, "T", 1)["group"], "medium")
        self.assertEqual(group_of(groups, "T", 1)["reference"], [0, 5])

    def test_duplicate_rejected(self):
        episodes = seed_eps("T", 1, LEAVE)
        with self.assertRaises(ValueError):
            label_seeds(episodes + [episodes[0]], SEEDS)
        # same policy seed under a different kind is fine
        label_seeds(episodes + eps("T", 1, "retry", [True]), SEEDS)

    def test_infrastructure_error_retry_allowed(self):
        retried = eps("T", 1, "reference", [None, True])
        retried[1][0]["policy_seed"] = 0
        episodes = retried + eps("T", 1, "reference", [True] * 4, first_policy_seed=1)
        groups = label_seeds(episodes, SEEDS)
        self.assertEqual((group_of(groups, "T", 1)["group"], group_of(groups, "T", 1)["reference"]), ("leave_alone", [5, 5]))
        single = eps("T", 1, "reference", [None, True])
        single[1][0]["policy_seed"] = 0
        self.assertEqual(group_of(label_seeds(single, SEEDS), "T", 1)["reference"], [1, 1])

    def test_repeated_infrastructure_errors_leave_seed_pending(self):
        twice = eps("T", 1, "reference", [None, None])
        for manifest, _ in twice:
            manifest["policy_seed"] = 0
        groups = label_seeds(twice + eps("T", 1, "reference", [True] * 3, first_policy_seed=1), SEEDS)
        self.assertEqual((group_of(groups, "T", 1)["group"], group_of(groups, "T", 1)["reference"]), ("pending", [3, 3]))
        groups = label_seeds(twice, SEEDS)
        self.assertEqual((group_of(groups, "T", 1)["group"], group_of(groups, "T", 1)["reference"]), ("pending", [0, 0]))

    def test_two_non_infrastructure_attempts_rejected(self):
        episodes = eps("T", 1, "reference", [None, True, False])
        for manifest, _ in episodes:
            manifest["policy_seed"] = 0
        with self.assertRaises(ValueError):
            label_seeds(episodes, SEEDS)

    def test_exactly_one_of_scene_and_policy_seed_rejected(self):
        for drop in ("scene_seed", "policy_seed"):
            manifest, result = seed_eps("T", 1, LEAVE)[0]
            del manifest[drop]
            with self.assertRaises(ValueError):
                label_seeds([(manifest, result)], SEEDS)

    def test_qualification_and_selection_cap_and_order(self):
        episodes = []
        for s in (1009, 1001, 1005, 1003, 1007, 1002):
            episodes += seed_eps("A", s, LEAVE)
        for s in (2004, 2000, 2008, 2002, 2006):
            episodes += seed_eps("A", s, HELP, retry=RESCUE)
        episodes += seed_eps("B", 1, LEAVE) + seed_eps("B", 2, LEAVE) + seed_eps("B", 3, HELP, retry=RESCUE)
        episodes += seed_eps("C", 1, LEAVE) + seed_eps("C", 2, LEAVE) + seed_eps("C", 3, HELP, retry=RESCUE) + seed_eps("C", 4, HELP, retry=RESCUE)
        groups = label_seeds(episodes, SEEDS)
        self.assertTrue(groups["tasks"]["A"]["qualified"])
        self.assertEqual(groups["tasks"]["A"]["selected"], {"leave_alone": [1001, 1002, 1003, 1005], "needs_help": [2000, 2002, 2004, 2006]})
        self.assertFalse(groups["tasks"]["B"]["qualified"])
        self.assertEqual(groups["tasks"]["B"]["selected"], {"leave_alone": [], "needs_help": []})
        self.assertTrue(groups["tasks"]["C"]["qualified"])
        self.assertEqual(groups["tasks"]["C"]["selected"], {"leave_alone": [1, 2], "needs_help": [3, 4]})

    def test_custom_thresholds_merge(self):
        groups = label_seeds(seed_eps("T", 1, [True] * 3), [0, 1, 2], {"trials": 3, "leave_alone_min": 3})
        self.assertEqual(group_of(groups, "T", 1)["group"], "leave_alone")
        self.assertEqual(groups["thresholds"]["max_per_group"], 4)
        self.assertEqual(groups["screening_policy_seeds"], [0, 1, 2])

    def test_legacy_seed_fallback(self):
        manifest, result = seed_eps("T", 1, LEAVE)[0]
        legacy = {k: v for k, v in manifest.items() if k not in ("scene_seed", "policy_seed")}
        legacy["seed"] = 1
        groups = label_seeds([(legacy, result)], [1])
        self.assertEqual(group_of(groups, "T", 1)["reference"], [1, 1])


class NativeCardTests(unittest.TestCase):
    def test_pools_usable_set_a_reference_episodes_of_the_task(self):
        episodes = (seed_eps("T", 1, [True, True, False, None, True], retry=LEAVE) + seed_eps("T", 2, HELP)
                    + eps("T", 3, "reference", [True] * 5, first_policy_seed=5) + seed_eps("U", 1, LEAVE))
        self.assertEqual(native_card_performance(episodes, "T", SEEDS), {
            "status": "screened", "trials": 9, "successes": 3, "success_rate": 3 / 9, "wilson_95": wilson_interval(3, 9),
            "policy_seeds": "screening set A",
            "note": "Plain-policy success on the native instruction over all screened scene seeds; not a per-seed estimate."})

    def test_no_usable_reference_episode_is_not_screened(self):
        with self.assertRaises(ValueError):
            native_card_performance(eps("T", 1, "reference", [None, None]) + seed_eps("U", 1, LEAVE), "T", SEEDS)

    def test_duplicate_usable_episode_rejected(self):
        episodes = seed_eps("T", 1, LEAVE)
        with self.assertRaises(ValueError):
            native_card_performance(episodes + [episodes[0]], "T", SEEDS)


def qualified_groups(count, screening=(0, 1, 2, 3, 4)):
    tasks = {f"T{i}": {"qualified": True, "scene_seeds": {}, "selected": {"leave_alone": [1, 2], "needs_help": [3, 4]}} for i in range(count)}
    tasks["Unq"] = {"qualified": False, "scene_seeds": {}, "selected": {"leave_alone": [], "needs_help": []}}
    return {"schema_version": 1, "thresholds": {}, "screening_policy_seeds": list(screening), "tasks": tasks}


class FreezeTests(unittest.TestCase):
    def configs(self, count):
        return {f"T{i}": {"task": f"T{i}"} for i in range(count)} | {"Unq": {"task": "Unq"}}

    def test_freeze_ten_qualified_tasks(self):
        release = freeze_release(qualified_groups(10), self.configs(10), [5, 6, 7, 8, 9], ["m1", "m2"], "abc")
        self.assertEqual({k: release[k] for k in ("schema_version", "status", "contract_hash", "models", "reference_policy_seeds")},
                         {"schema_version": 1, "status": "frozen", "contract_hash": "abc", "models": ["m1", "m2"], "reference_policy_seeds": [5, 6, 7, 8, 9]})
        self.assertTrue(release["created_at"].endswith("+00:00") or release["created_at"].endswith("Z"))
        self.assertEqual(len(release["tasks"]), 10)
        self.assertNotIn("Unq", release["tasks"])
        self.assertEqual(release["tasks"]["T0"], {"config": {"task": "T0"}, "leave_alone": [1, 2], "needs_help": [3, 4]})

    def test_more_than_ten_qualified_keeps_top_ten_by_predeclared_rank(self):
        groups = qualified_groups(12)
        sizes = {"T0": (2, 2), "T1": (4, 2), "T2": (2, 3), "T3": (3, 3), "T4": (2, 2), "T5": (4, 4),
                 "T6": (2, 2), "T7": (2, 2), "T8": (2, 2), "T9": (2, 2), "T10": (3, 4), "T11": (2, 2)}
        for task, (leave, helped) in sizes.items():
            groups["tasks"][task]["selected"] = {"leave_alone": list(range(leave)), "needs_help": list(range(10, 10 + helped))}
        configs = self.configs(12)
        del configs["T9"]  # a task outside the kept ten needs no config
        release = freeze_release(groups, configs, [5], ["m"], "h")
        # min desc, then total desc, then name asc: T5, T10, T3, T1, T2, then the (2, 2) ties T0, T11, T4, T6, T7.
        self.assertEqual(list(release["tasks"]), ["T5", "T10", "T3", "T1", "T2", "T0", "T11", "T4", "T6", "T7"])
        self.assertEqual(len(freeze_release(groups, self.configs(12), [5], ["m"], "h", max_tasks=11)["tasks"]), 11)

    def test_fewer_than_ten_rejected_unless_allowed(self):
        with self.assertRaises(ValueError):
            freeze_release(qualified_groups(9), self.configs(9), [5], ["m"], "h")
        release = freeze_release(qualified_groups(9), self.configs(9), [5], ["m"], "h", allow_fewer=True)
        self.assertEqual(len(release["tasks"]), 9)

    def test_reference_seed_overlap_rejected(self):
        with self.assertRaises(ValueError):
            freeze_release(qualified_groups(10), self.configs(10), [4, 5], ["m"], "h")
        with self.assertRaises(ValueError):
            freeze_release(qualified_groups(10), self.configs(10), [4, 5], ["m"], "h", allow_fewer=True)

    def test_reference_seeds_must_be_nonempty_unique_int_list(self):
        for bad in ([], [5, 5], [5, "6"], [True], (5, 6), None, [5.0]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                freeze_release(qualified_groups(10), self.configs(10), bad, ["m"], "h")

    def test_missing_config_rejected(self):
        configs = self.configs(10)
        del configs["T3"]
        with self.assertRaises(ValueError):
            freeze_release(qualified_groups(10), configs, [5], ["m"], "h")


class LoadEpisodesTests(unittest.TestCase):
    def test_load_with_missing_result_and_non_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, manifest, result in (
                ("a", {"artifact_type": "episode", "task": "T", "seed": 1}, {"status": "success", "success": True}),
                ("b", {"artifact_type": "episode", "task": "T", "seed": 2}, None),
                ("c", {"artifact_type": "feasibility", "task": "T"}, {"status": "success"}),
            ):
                (root / name).mkdir()
                (root / name / "manifest.json").write_text(json.dumps(manifest))
                if result is not None:
                    (root / name / "result.json").write_text(json.dumps(result))
            rows = load_episodes(root)
        self.assertEqual([m["seed"] for m, _ in rows], [1, 2])
        self.assertEqual(rows[0][1]["status"], "success")
        self.assertEqual(rows[1][1]["status"], "infrastructure_error")
        self.assertFalse(rows[1][1]["success"])

    def test_invalid_result_is_infrastructure_error_but_invalid_manifest_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, text in (("a", '{"status": "succ'), ("b", "[1]"), ("c", '{"success": true}')):
                (root / name).mkdir()
                (root / name / "manifest.json").write_text(json.dumps({"artifact_type": "episode", "task": "T", "seed": 1}))
                (root / name / "result.json").write_text(text)
            rows = load_episodes(root)
            self.assertEqual([(r["status"], r["success"]) for _, r in rows], [("infrastructure_error", False)] * 3)
            self.assertIn("unreadable result", rows[0][1]["infrastructure_error"])
            (root / "a" / "manifest.json").write_text('{"artifact_type": "epi')
            with self.assertRaises(ValueError):
                load_episodes(root)


if __name__ == "__main__":
    unittest.main()
