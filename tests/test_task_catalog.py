import json
import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from robot_benchmark.tasks.predicates import CANDIDATE_TASKS, SEQUENCES, task_predicates

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "configs" / "tasks"
REGISTRY = ROOT / "vendor/reference/robocasa/robocasa/utils/dataset_registry.py"
UNTESTED = {"status": "untested", "trials": 0, "success_rate": None, "conditions": []}


def registry_horizons():
    text = REGISTRY.read_text()
    horizons = {}
    for match in re.finditer(r"^    (\w+)=dict\((.*?)^    \),", text, re.S | re.M):
        horizon = re.search(r"horizon=(\d+)", match.group(2))
        if horizon:
            horizons.setdefault(match.group(1), int(horizon.group(1)))
    return horizons


def fake_robocasa(**helpers):
    """Patch robocasa.utils.object_utils (absent locally) with the given helpers."""
    ou = types.ModuleType("robocasa.utils.object_utils")
    ou.__dict__.update(helpers)
    utils = types.ModuleType("robocasa.utils")
    utils.object_utils = ou
    root = types.ModuleType("robocasa")
    root.utils = utils
    return mock.patch.dict(sys.modules, {"robocasa": root, "robocasa.utils": utils, "robocasa.utils.object_utils": ou})


def raw_env():
    raw = mock.MagicMock()
    raw.obj_body_id = {"obj": 7}
    raw.objects = {"obj": mock.Mock()}
    raw.objects["obj"].name = "obj"
    raw.sim.data.body_xpos = {7: (1.0, 1.0, 0.9)}
    raw.stove.burner_sites = {"front_left": {"name": "fl"}, "rear_left": None}
    raw.stove.get_knobs_state.return_value = {"front_left": 1.0}
    raw.stove.is_burner_on.return_value = True
    raw.sim.data.get_site_xpos.return_value = (1.05, 1.0, 0.9)
    raw.board_contact_timer = 6
    raw.board_contact_positions = [(0.0, 0.0), (0.08, 0.08)]
    raw.washed_loc = [True, True, False]
    raw.washed_time = 25
    raw.sink.get_handle_state.return_value = {"water_on": True, "spout_ori": "left"}
    raw.dishwasher.check_rack_contact.return_value = True
    raw.dishwasher.is_closed.return_value = False
    raw.coffee_machine.check_receptacle_placement_for_pouring.return_value = True
    raw.coffee_machine._turned_on = False
    return raw


class CatalogConfigTests(unittest.TestCase):
    def setUp(self):
        self.configs = {path.stem: json.loads(path.read_text()) for path in sorted(CONFIGS.glob("*.json"))}

    def test_config_files_match_candidates(self):
        self.assertEqual(len(CANDIDATE_TASKS), 16)
        self.assertEqual(set(self.configs), set(CANDIDATE_TASKS))
        self.assertEqual(set(SEQUENCES), {task for task, kind in CANDIDATE_TASKS.items() if kind == "composite_seen"})
        self.assertEqual(sum(kind == "atomic_seen" for kind in CANDIDATE_TASKS.values()), 10)

    def test_configs_use_native_goal_and_registry_horizon(self):
        horizons = registry_horizons()
        for task, config in self.configs.items():
            with self.subTest(task=task):
                self.assertEqual(config["task"], task)
                self.assertEqual(config["schema_version"], 3)
                # publish-cards turns candidate_unscreened into screened with a set-A card.
                self.assertIn(config["status"], ("candidate_unscreened", "screened"))
                self.assertEqual(config["split"], "pretrain")
                self.assertIsNone(config["goal"])
                self.assertEqual(config["goal_source"], "native_instruction")
                self.assertEqual(config["max_steps"], horizons[task])
                self.assertEqual((config["max_decisions"], config["max_interval"]), (100, 400))
                self.assertEqual((config["camera_size"], config["video_record_interval"]), (256, 1))
                self.assertEqual(config["interval_keyframes"], 4)
                self.assertEqual(config["agent_image_history"],
                                 "current_frames_plus_interval_keyframes_plus_decision_history")
                self.assertIs(config["artificial_disturbances"], False)
                self.assertEqual(config["task_set"], CANDIDATE_TASKS[task])
                first = config["reference_prompts"][0]
                self.assertEqual(first["id"], "native_instruction")
                self.assertEqual(first["prompt"], "{goal}")
                self.assertEqual(first["description"], "Card for the task's native RoboCasa instruction (the goal text)")
                if config["status"] == "candidate_unscreened":
                    self.assertEqual(first["performance"]["status"], "untested")
                    self.assertIsNone(first["performance"]["success_rate"])
                else:
                    self.assertEqual(first["performance"]["status"], "screened")
                    self.assertEqual(first["performance"]["policy_seeds"], "screening set A")

    def test_configs_never_expose_privileged_step_prompts(self):
        step_prompts = [prompt for steps in SEQUENCES.values() for _, prompt in steps]
        for task, config in self.configs.items():
            with self.subTest(task=task):
                self.assertEqual(len(config["reference_prompts"]), 1)
                if config["status"] == "candidate_unscreened":
                    self.assertEqual(config["reference_prompts"][0]["performance"], UNTESTED)
                text = json.dumps(config)
                for prompt in step_prompts:
                    self.assertNotIn(prompt, text)


class PredicateTests(unittest.TestCase):
    def test_unknown_and_atomic_tasks_have_no_predicates(self):
        self.assertEqual(task_predicates("UnknownTask", object()), {})
        self.assertEqual(task_predicates("OpenDrawer", object()), {})

    def test_sequences_are_short_prompts_never_success(self):
        for task, steps in SEQUENCES.items():
            names = [name for name, _ in steps]
            self.assertGreaterEqual(len(steps), 2, task)
            self.assertEqual(len(names), len(set(names)), task)
            self.assertNotIn("success", names, task)
            for _, prompt in steps:
                self.assertTrue(prompt.strip() and len(prompt) <= 512, task)

    def test_composite_predicates_are_booleans_keyed_by_sequence(self):
        helpers = {"check_obj_fixture_contact": mock.Mock(return_value=True),
                   "gripper_obj_far": mock.Mock(return_value=False)}
        with fake_robocasa(**helpers):
            for task, steps in SEQUENCES.items():
                with self.subTest(task=task):
                    truth = task_predicates(task, raw_env())
                    self.assertEqual(list(truth), [name for name, _ in steps])
                    self.assertTrue(all(type(value) is bool for value in truth.values()))

    def test_predicates_mirror_upstream_conjuncts(self):
        far = mock.Mock(return_value=True)
        contact = mock.Mock(return_value=True)
        with fake_robocasa(check_obj_fixture_contact=contact, gripper_obj_far=far):
            raw = raw_env()
            self.assertEqual(task_predicates("KettleBoiling", raw), {"kettle_on_burner": True, "kettle_burner_on": True})
            raw.stove.is_burner_on.return_value = False
            self.assertEqual(task_predicates("KettleBoiling", raw), {"kettle_on_burner": True, "kettle_burner_on": False})
            raw.sim.data.get_site_xpos.return_value = (1.2, 1.0, 0.9)  # 0.2 m from the burner > 0.15
            self.assertEqual(task_predicates("KettleBoiling", raw), {"kettle_on_burner": False, "kettle_burner_on": False})
            contact.return_value = False
            raw.sim.data.get_site_xpos.return_value = (1.0, 1.0, 0.9)
            self.assertEqual(task_predicates("KettleBoiling", raw)["kettle_on_burner"], False)

            raw = raw_env()  # sweep = hypot(0.08, 0.08) ~= 0.113 >= 0.1 and timer 6 >= 5
            self.assertEqual(task_predicates("ScrubCuttingBoard", raw), {"board_scrubbed": True, "sponge_released": True})
            far.assert_called_with(raw, "sponge", th=0.15)
            raw.board_contact_positions = [(0.0, 0.0), (0.05, 0.05)]
            self.assertFalse(task_predicates("ScrubCuttingBoard", raw)["board_scrubbed"])
            raw.board_contact_positions, raw.board_contact_timer = [], 0
            self.assertFalse(task_predicates("ScrubCuttingBoard", raw)["board_scrubbed"])

            raw = raw_env()
            self.assertEqual(task_predicates("RinseSinkBasin", raw), {"water_on": True, "basin_rinsed": False})
            raw.washed_loc = [True, True, True]
            raw.sink.get_handle_state.return_value = {"water_on": False, "spout_ori": "left"}
            self.assertEqual(task_predicates("RinseSinkBasin", raw), {"water_on": False, "basin_rinsed": True})

            raw = raw_env()
            self.assertEqual(task_predicates("WashLettuce", raw), {"water_on": True, "lettuce_washed": True})
            raw.washed_time = 24
            self.assertFalse(task_predicates("WashLettuce", raw)["lettuce_washed"])

            raw = raw_env()
            self.assertEqual(task_predicates("LoadDishwasher", raw), {"dishes_on_rack": True, "dishwasher_closed": False})
            raw.dishwasher.is_closed.assert_called_with(raw, th=0.05)
            raw.dishwasher.check_rack_contact.side_effect = lambda env, name: name == "dish0"
            self.assertFalse(task_predicates("LoadDishwasher", raw)["dishes_on_rack"])

            raw = raw_env()
            self.assertEqual(task_predicates("PrepareCoffee", raw), {"mug_under_dispenser": True, "machine_on": False})
            raw.coffee_machine.check_receptacle_placement_for_pouring.assert_called_with(raw, "obj")


if __name__ == "__main__":
    unittest.main()
