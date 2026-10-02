import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from robot_benchmark import cli
from robot_benchmark.cli import contract_payload, parse_seeds, resolve_audit_paths, task_parts, validate_splits
from robot_benchmark.contracts import Limits, Skill
from robot_benchmark.records import digest

from tests.fakes import FakeAgent, FakeEnvironment, FakePolicy

ROOT = Path(__file__).resolve().parents[1]
NATIVE = {"schema_version": 3, "status": "candidate_unscreened", "task": "OpenDrawer",
          "task_set": "atomic_seen", "split": "pretrain", "goal": None,
          "goal_source": "native_instruction", "max_steps": 750, "max_decisions": 100,
          "max_interval": 400, "camera_size": 256, "video_record_interval": 1,
          "agent_image_history": "current_frames_plus_interval_keyframes_plus_decision_history",
          "interval_keyframes": 4, "artificial_disturbances": False,
          "reference_prompts": [{"id": "native_instruction",
              "prompt": "{goal}",
              "description": "Card for the task's native RoboCasa instruction (the goal text)",
              "performance": {"status": "untested", "trials": 0, "success_rate": None, "conditions": []}}]}


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

    def test_shipped_task_config_uses_long_intervals_and_keyframes(self):
        config, _, limits = task_parts(Path(__file__).resolve().parents[1] / "configs/cereal_and_bowl.json")
        self.assertEqual(limits.max_interval, 400)
        self.assertEqual(config["interval_keyframes"], 4)

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
            "screening_policy_seeds": [0, 1],
            "reference_policy_seeds": [2, 3],
        }
        self.assertIs(validate_splits(valid), valid)

        overlapping = {**valid, "qualification_seeds": [1]}
        with self.assertRaisesRegex(ValueError, "disjoint"):
            validate_splits(overlapping)
        too_small = {**valid, "evaluation_seeds": list(range(100, 119))}
        with self.assertRaisesRegex(ValueError, "at least 20"):
            validate_splits(too_small)


class GenericTaskConfigTests(unittest.TestCase):
    def parts(self, config):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "task.json"
            path.write_text(json.dumps(config))
            return task_parts(path)

    def test_native_goal_config_passes_with_extra_keys(self):
        config, prompts, limits = self.parts(NATIVE)
        self.assertIsNone(config["goal"])
        self.assertEqual([item.id for item in prompts], ["native_instruction"])
        self.assertEqual((limits.max_steps, limits.max_decisions, limits.max_interval), (750, 100, 400))
        self.assertEqual(self.parts({**NATIVE, "goal": "Open the drawer.", "goal_source": "authored"})[0]["goal"],
                         "Open the drawer.")

    def test_invalid_generic_configs_are_rejected(self):
        for change in ({"max_interval": 100}, {"interval_keyframes": 3}, {"artificial_disturbances": True},
                       {"goal": None, "goal_source": "authored"}, {"goal": "  "}, {"goal": 5},
                       {"reference_prompts": []}, {"max_steps": 0}, {"split": "target"},
                       *({"reference_prompts": [dict(NATIVE["reference_prompts"][0], **{key: value})]}
                         for key in ("id", "prompt") for value in ("", "  ", None, 3))):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.parts({**NATIVE, **change})
        missing = dict(NATIVE)
        del missing["camera_size"]
        with self.assertRaises(ValueError):
            self.parts(missing)

    def test_cereal_and_bowl_keeps_its_audited_checks(self):
        shipped = json.loads((ROOT / "configs/cereal_and_bowl.json").read_text())
        self.assertEqual(self.parts(shipped)[0]["task"], "CerealAndBowl")
        changed = copy.deepcopy(shipped)
        changed["reference_prompts"][0]["prompt"] = "Open the left cabinet."
        with self.assertRaisesRegex(ValueError, "reference prompts changed"):
            self.parts(changed)
        for change in ({"goal": "Do it."}, {"max_steps": 4000}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.parts({**shipped, **change})


class SplitPolicySeedTests(unittest.TestCase):
    def test_shipped_splits_pass_and_policy_seed_sets_are_disjoint(self):
        shipped = json.loads((ROOT / "configs/splits.json").read_text())
        self.assertEqual(validate_splits(shipped)["screening_policy_seeds"], [0, 1, 2, 3, 4])
        self.assertEqual(shipped["reference_policy_seeds"], [5, 6, 7, 8, 9])
        with self.assertRaisesRegex(ValueError, "disjoint"):
            validate_splits({**shipped, "reference_policy_seeds": [4, 5]})
        for name in ("screening_policy_seeds", "reference_policy_seeds"):
            for bad in ([], [1, 1], [-1], None):
                with self.subTest(name=name, bad=bad), self.assertRaises(ValueError):
                    validate_splits({**shipped, name: bad})


class FakeRoboCasa(FakeEnvironment):
    horizon = 750

    def __init__(self, task, split, camera_size):
        super().__init__(native="Open the left drawer.")


class RunEpisodeSeedTests(unittest.TestCase):
    def run_episode(self, output, policy, **kwargs):
        prompts = [Skill(item["id"], item["prompt"], item["description"], item["performance"])
                   for item in NATIVE["reference_prompts"]]
        with mock.patch("robot_benchmark.adapters.robocasa.RoboCasaEnvironment", FakeRoboCasa), \
                mock.patch.object(cli, "encode_episode_videos", return_value={}), \
                mock.patch("builtins.print"):
            return cli.run_episode(output=output, task_config=NATIVE, reference_prompts=prompts,
                                   limits=Limits(750, 100, 400), policy=policy,
                                   agent_factory=lambda env: FakeAgent([{"op": "complete"}]),
                                   kind="llm_development", contract_hash="contract", **kwargs)

    def test_scene_and_policy_seeds_are_recorded_separately(self):
        with tempfile.TemporaryDirectory() as temporary:
            output, policy = Path(temporary), FakePolicy()
            result = self.run_episode(output, policy, seed=7, policy_seed=3)
            (episode,) = output.iterdir()
            manifest = json.loads((episode / "manifest.json").read_text())
            self.assertTrue(episode.name.startswith("seed-7-p3-"))
            self.assertEqual((manifest["seed"], manifest["scene_seed"], manifest["policy_seed"]), (7, 7, 3))
            self.assertEqual(policy.reset_episode_seeds, [3])
            self.assertEqual((result["goal"], result["scene_seed"], result["policy_seed"]),
                             ("Open the left drawer.", 7, 3))

    def test_policy_seed_defaults_to_scene_seed_and_infrastructure_result_carries_seeds(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with mock.patch.object(FakeRoboCasa, "horizon", 1):
                result = self.run_episode(output, FakePolicy(), seed=7)
            (episode,) = output.iterdir()
            self.assertTrue(episode.name.startswith("seed-7-p7-"))
            self.assertEqual(result["status"], "infrastructure_error")
            self.assertEqual((result["goal"], result["scene_seed"], result["policy_seed"]), (None, 7, 7))

    def test_manifest_records_the_video_record_interval_in_use(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with mock.patch.dict(NATIVE, video_record_interval=7):
                self.run_episode(output, FakePolicy(), seed=7, policy_seed=3)
            (episode,) = output.iterdir()
            self.assertEqual(json.loads((episode / "manifest.json").read_text())["video_record_interval"], 7)


class PolicySeedCommandTests(unittest.TestCase):
    def test_feasibility_runs_every_scene_policy_pair_scene_major(self):
        policy = mock.Mock(identity={"adapter": "fake-policy"})
        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch.object(cli, "RemotePolicy", return_value=policy), \
                mock.patch.object(cli, "run_episode") as run_episode:
            base = ["feasibility", "--mode", "ordinary", "--seeds", "1,2", "--output", temporary]
            self.assertEqual(cli.main(base + ["--policy-seeds", "5,6"]), 0)
            pairs = [(call.kwargs["seed"], call.kwargs["policy_seed"]) for call in run_episode.call_args_list]
            self.assertEqual(pairs, [(1, 5), (1, 6), (2, 5), (2, 6)])
            run_episode.reset_mock()
            self.assertEqual(cli.main(base), 0)
            pairs = [(call.kwargs["seed"], call.kwargs["policy_seed"]) for call in run_episode.call_args_list]
            self.assertEqual(pairs, [(1, None), (2, None)])

    def test_run_accepts_policy_seeds(self):
        policy = mock.Mock(identity={"adapter": "fake-policy"})
        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch.object(cli, "RemotePolicy", return_value=policy), \
                mock.patch.object(cli, "HTTPAgent"), mock.patch.object(cli, "run_episode") as run_episode:
            agent_config = Path(temporary) / "agent.json"
            agent_config.write_text("{}")
            self.assertEqual(cli.main(["run", "--development", "--agent-config", str(agent_config), "--seeds", "1",
                                       "--policy-seeds", "5,6", "--output", temporary]), 0)
            pairs = [(call.kwargs["seed"], call.kwargs["policy_seed"]) for call in run_episode.call_args_list]
            self.assertEqual(pairs, [(1, 5), (1, 6)])


POLICY = {"adapter": "fake-policy", "checkpoint": "pinned"}
TASKS = ROOT / "configs" / "tasks"


def write_episode(folder, kind, task, scene, policy, success, contract="h", model="none"):
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({
        "artifact_type": "episode", "kind": kind, "agent": {"kind": kind, "model": model}, "task": task,
        "seed": scene, "scene_seed": scene, "policy_seed": policy, "contract_hash": contract}))
    (folder / "result.json").write_text(json.dumps({
        "status": "success" if success else "step_budget_exhausted", "success": success, "goal": "g",
        "scene_seed": scene, "policy_seed": policy}))


class BenchmarkCommandTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for patcher in (mock.patch.object(cli, "RemotePolicy", return_value=mock.Mock(identity=POLICY)),
                        mock.patch("builtins.print")):
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(cli, "run_episode")
        self.run_episode = patcher.start()
        self.addCleanup(patcher.stop)

    def main(self, *argv):
        return cli.main([str(value) for value in argv])

    def calls(self):
        return [(c.kwargs["task_config"]["task"], c.kwargs["seed"], c.kwargs["policy_seed"], c.kwargs["kind"])
                for c in self.run_episode.call_args_list]

    def hashes(self):
        return {c.kwargs["contract_hash"] for c in self.run_episode.call_args_list}

    def screen(self, *extra, tasks=("OpenDrawer", "KettleBoiling"), mode="reference"):
        return self.main("screen", "--task-configs", *(TASKS / f"{task}.json" for task in tasks),
                         "--scene-seeds", "1000,1001", "--policy-seeds", "0,1", "--mode", mode,
                         "--output", self.root / "screen", *extra)

    def test_shipped_task_pool_passes_task_parts(self):
        paths = sorted(TASKS.glob("*.json"))
        self.assertEqual(len(paths), 16)
        for path in paths:
            with self.subTest(path=path.name):
                config, prompts, _ = task_parts(path)
                self.assertEqual(config["task"], path.stem)
                self.assertNotIn("full_task", [item.id for item in prompts])
        self.assertEqual(sorted(cli.task_pool()), sorted(path.stem for path in paths))

    def test_screen_runs_every_task_scene_policy_combination_with_native_goal(self):
        self.assertEqual(self.screen(), 0)
        self.assertEqual(self.calls(), [(task, scene, policy, "diagnostic_reference")
                                        for task in ("OpenDrawer", "KettleBoiling")
                                        for scene in (1000, 1001) for policy in (0, 1)])
        call = self.run_episode.call_args_list[0].kwargs
        self.assertIsNone(call["task_config"]["goal"])
        self.assertEqual([item.id for item in call["reference_prompts"]], ["native_instruction"])
        self.assertIsInstance(call["agent_factory"](mock.Mock()), cli.OrdinaryPolicySupervisor)
        self.assertEqual(len(self.hashes()), 1)
        (contract_hash,) = self.hashes()
        contract = json.loads((self.root / "screen" / f"contract-{contract_hash}.json").read_text())
        self.assertEqual(digest(contract), contract_hash)
        self.assertFalse((self.root / "screen" / "contract.json").exists())
        self.assertEqual(sorted(contract["task_configs"]), sorted(cli.task_pool()))

    def test_screen_modes_dispatch_privileged_diagnostics(self):
        self.assertEqual(self.screen(mode="retry"), 0)
        self.assertEqual({kind for *_, kind in self.calls()}, {"diagnostic_retry"})
        self.assertIsInstance(self.run_episode.call_args.kwargs["agent_factory"](mock.Mock()),
                              cli.PrivilegedRetrySupervisor)
        self.run_episode.reset_mock()
        self.assertEqual(self.screen(mode="sequencer", tasks=("KettleBoiling",)), 0)
        self.assertEqual({kind for *_, kind in self.calls()}, {"diagnostic_sequencer"})
        self.assertIsInstance(self.run_episode.call_args.kwargs["agent_factory"](mock.Mock()),
                              cli.PrivilegedSequencer)
        self.run_episode.reset_mock()
        self.assertEqual(self.screen(mode="sequencer", tasks=("KettleBoiling", "OpenDrawer")), 2)
        self.run_episode.assert_not_called()

    def test_video_record_interval_override_does_not_change_contract_hash(self):
        self.assertEqual(self.screen(), 0)
        plain = self.hashes()
        self.run_episode.reset_mock()
        self.assertEqual(self.screen("--video-record-interval", "10"), 0)
        self.assertEqual(self.hashes(), plain)
        self.assertEqual({c.kwargs["task_config"]["video_record_interval"] for c in self.run_episode.call_args_list}, {10})
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            self.screen("--video-record-interval", "0")

    def test_skip_existing_skips_only_completed_episodes_of_the_same_kind_and_model(self):
        task_root, current = self.root / "screen" / "OpenDrawer", self.contract_hash()
        write_episode(task_root / "done", "diagnostic_reference", "OpenDrawer", 1000, 0, True,
                      model="ordinary_full_task_policy", contract=current)
        write_episode(task_root / "other-model", "diagnostic_reference", "OpenDrawer", 1000, 1, True, model="other",
                      contract=current)
        write_episode(task_root / "old-hash", "diagnostic_reference", "OpenDrawer", 1000, 1, True,
                      model="ordinary_full_task_policy", contract="old")
        write_episode(task_root / "other-kind", "diagnostic_retry", "OpenDrawer", 1001, 0, True,
                      model="ordinary_full_task_policy", contract=current)
        write_episode(task_root / "infra", "diagnostic_reference", "OpenDrawer", 1001, 1, False,
                      model="ordinary_full_task_policy", contract=current)
        (task_root / "infra" / "result.json").write_text(json.dumps({"status": "infrastructure_error", "success": False}))
        self.assertEqual(self.screen("--skip-existing", tasks=("OpenDrawer",)), 0)
        self.assertEqual([call[1:3] for call in self.calls()], [(1000, 1), (1001, 0), (1001, 1)])
        self.run_episode.reset_mock()
        self.assertEqual(self.screen(tasks=("OpenDrawer",)), 0)
        self.assertEqual(len(self.calls()), 4)

    def test_grid_and_run_stop_after_three_consecutive_infrastructure_errors(self):
        infra, ok = {"status": "infrastructure_error"}, {"status": "success"}
        # A task that keeps failing is abandoned; the grid continues with the next task and reports failure.
        self.run_episode.side_effect = [infra, infra, infra, ok, ok, ok, ok]
        with mock.patch("builtins.print") as printed:
            self.assertEqual(self.screen(), 1)
        self.assertEqual([call[0] for call in self.calls()], ["OpenDrawer"] * 3 + ["KettleBoiling"] * 4)
        self.assertIn("abandoning OpenDrawer after 3 consecutive infrastructure errors", printed.call_args.args[0])
        # Two tasks abandoned back to back (no usable episode between) stop the whole grid.
        self.run_episode.reset_mock()
        self.run_episode.side_effect = [infra] * 6
        with mock.patch("builtins.print") as printed:
            self.assertEqual(self.screen(tasks=("OpenDrawer", "KettleBoiling", "CloseFridge")), 1)
        self.assertEqual([call[0] for call in self.calls()], ["OpenDrawer"] * 3 + ["KettleBoiling"] * 3)
        self.assertIn("two tasks in a row", printed.call_args.args[0])
        # Errors are counted per task: interleaved successes reset the count.
        self.run_episode.reset_mock()
        self.run_episode.side_effect = [infra, ok, infra, infra, infra, ok, ok, ok]
        self.assertEqual(self.screen(), 0)
        self.assertEqual(len(self.calls()), 8)
        self.run_episode.reset_mock()
        self.run_episode.side_effect = [infra] * 4
        self.assertEqual(self.run_command("--development", "--seeds", "1000,1001", "--policy-seeds", "5,6"), 1)
        self.assertEqual(len(self.calls()), 3)

    def test_scenes_from_restricts_rescue_screening_to_low_success_scenes(self):
        groups = {"thresholds": {"trials": 5, "needs_help_max": 1},
                  "tasks": {"OpenDrawer": {"scene_seeds": {"1000": {"reference": [1, 5]}, "1001": {"reference": [4, 5]}}},
                            "KettleBoiling": {"scene_seeds": {"1000": {"reference": [0, 4]},
                                                              "1001": {"reference": [0, 5]}}}}}
        path = self.root / "groups.json"
        path.write_text(json.dumps(groups))
        self.assertEqual(self.screen("--scenes-from", path, mode="retry"), 0)
        self.assertEqual(self.calls(), [("OpenDrawer", 1000, 0, "diagnostic_retry"), ("OpenDrawer", 1000, 1, "diagnostic_retry"),
                                        ("KettleBoiling", 1001, 0, "diagnostic_retry"),
                                        ("KettleBoiling", 1001, 1, "diagnostic_retry")])
        self.run_episode.reset_mock()
        self.assertEqual(self.screen("--scenes-from", path, mode="reference"), 2)
        self.run_episode.assert_not_called()

    def test_run_skip_existing_matches_the_agent_model(self):
        current = self.contract_hash()
        write_episode(self.root / "run" / "a", "llm_development", "OpenDrawer", 1000, 5, False, model="claude-opus-5-5",
                      contract=current)
        write_episode(self.root / "run" / "b", "llm_development", "OpenDrawer", 1000, 6, False, model="other-model",
                      contract=current)
        write_episode(self.root / "run" / "c", "llm_development", "OpenDrawer", 1000, 7, False, model="claude-opus-5-5",
                      contract="old")
        self.assertEqual(self.run_command("--development", "--seeds", "1000", "--policy-seeds", "5,6,7",
                                          "--skip-existing"), 0)
        self.assertEqual(self.calls(), [("OpenDrawer", 1000, 6, "llm_development"),
                                        ("OpenDrawer", 1000, 7, "llm_development")])
        self.assertTrue((self.root / "run" / "c" / "result.json").exists())  # old-hash episode kept on disk

    def test_screen_rejects_configs_outside_the_pool(self):
        changed = json.loads((TASKS / "OpenDrawer.json").read_text())
        changed["max_steps"] += 1
        path = self.root / "OpenDrawer.json"
        path.write_text(json.dumps(changed))
        for config in (path, ROOT / "configs/cereal_and_bowl.json"):
            with self.subTest(config=config.name):
                self.assertEqual(self.main("screen", "--task-configs", config, "--scene-seeds", "1",
                                           "--policy-seeds", "0", "--mode", "reference", "--output", self.root / "s"), 2)
        self.run_episode.assert_not_called()

    def test_baseline_agents_dispatch_by_name(self):
        for name, kind, agent in (("always_defer", "baseline_always_defer", cli.AlwaysDeferAgent),
                                  ("reissue", "baseline_reissue", cli.ReissueAgent)):
            with self.subTest(name=name):
                self.run_episode.reset_mock()
                self.assertEqual(self.main("baseline", "--task-configs", TASKS / "OpenDrawer.json", "--scene-seeds", "1000",
                                           "--policy-seeds", "5,6", "--agent", name, "--output", self.root / name), 0)
                self.assertEqual(self.calls(), [("OpenDrawer", 1000, 5, kind), ("OpenDrawer", 1000, 6, kind)])
                self.assertIsInstance(self.run_episode.call_args.kwargs["agent_factory"](mock.Mock()), agent)
        self.assertEqual(self.run_episode.call_args.kwargs["agent_factory"](mock.Mock()).every, 100)

    def test_feasibility_rejects_tasks_other_than_cereal_and_bowl(self):
        for mode in ("ordinary", "supervisor"):
            with self.subTest(mode=mode):
                self.assertEqual(self.main("feasibility", "--mode", mode, "--task-config", TASKS / "OpenDrawer.json",
                                           "--seeds", "1", "--output", self.root / mode), 2)
        self.run_episode.assert_not_called()

    def test_label_seeds_reads_a_run_directory_and_writes_groups(self):
        for scene, wins in ((1000, 5), (1001, 0)):
            for policy in range(5):
                write_episode(self.root / "runs" / f"{scene}-{policy}", "diagnostic_reference", "OpenDrawer",
                              scene, policy, policy < wins)
        write_episode(self.root / "runs" / "set-b", "diagnostic_reference", "OpenDrawer", 1000, 5, False)
        output = self.root / "groups.json"
        self.assertEqual(self.main("label-seeds", self.root / "runs", "--output", output), 0)
        groups = json.loads(output.read_text())
        self.assertEqual(groups["screening_policy_seeds"], [0, 1, 2, 3, 4])
        scenes = groups["tasks"]["OpenDrawer"]["scene_seeds"]
        self.assertEqual((scenes["1000"]["group"], scenes["1000"]["reference"]), ("leave_alone", [5, 5]))
        self.assertEqual(scenes["1001"]["group"], "medium")

    def test_publish_cards_writes_screened_native_card_performance(self):
        from robot_benchmark import screening
        configs = {}
        for task in ("OpenDrawer", "KettleBoiling", "CloseFridge"):
            configs[task] = self.root / "configs" / f"{task}.json"
            configs[task].parent.mkdir(exist_ok=True)
            configs[task].write_text((TASKS / f"{task}.json").read_text())
        runs = self.root / "screening"
        for scene in (1000, 1001):
            for policy in range(5):
                write_episode(runs / "OpenDrawer" / f"{scene}-{policy}", "diagnostic_reference", "OpenDrawer",
                              scene, policy, scene == 1000 and policy < 4)
        write_episode(runs / "OpenDrawer" / "set-b", "diagnostic_reference", "OpenDrawer", 1000, 5, True)
        write_episode(runs / "OpenDrawer" / "retry", "diagnostic_retry", "OpenDrawer", 1001, 0, True)
        write_episode(runs / "KettleBoiling" / "set-b", "diagnostic_reference", "KettleBoiling", 1000, 5, True)
        write_episode(runs / "CloseFridge" / "infra", "diagnostic_reference", "CloseFridge", 1000, 0, False)
        (runs / "CloseFridge" / "infra" / "result.json").write_text(json.dumps({"status": "infrastructure_error",
                                                                               "success": False}))
        unscreened = {task: configs[task].read_text() for task in ("KettleBoiling", "CloseFridge")}
        for task in unscreened:  # native_card_performance has no usable set-A episode for these tasks
            with self.assertRaises(ValueError):
                screening.native_card_performance(screening.load_episodes(runs), task, [0, 1, 2, 3, 4])
        self.assertEqual(self.main("publish-cards", runs, "--task-configs", *configs.values()), 0)
        drawer = json.loads(configs["OpenDrawer"].read_text())
        expected = screening.native_card_performance(screening.load_episodes(runs), "OpenDrawer", [0, 1, 2, 3, 4])
        self.assertEqual(drawer["status"], "screened")
        self.assertEqual(drawer["reference_prompts"][0]["performance"], expected)
        self.assertEqual((expected["trials"], expected["successes"]), (10, 4))
        self.assertEqual(task_parts(configs["OpenDrawer"])[0], drawer)
        for task, text in unscreened.items():
            self.assertEqual(configs[task].read_text(), text)
            self.assertEqual(json.loads(text)["status"], "candidate_unscreened")

    def groups(self, tasks):
        selected = {"leave_alone": [1000, 1001], "needs_help": [1002, 1003]}
        value = {"schema_version": 1, "screening_policy_seeds": [0, 1, 2, 3, 4],
                 "tasks": {task: {"qualified": True, "scene_seeds": {}, "selected": selected} for task in tasks}}
        path = self.root / "groups.json"
        path.write_text(json.dumps(value))
        return path

    def contract_hash(self):
        splits = json.loads((ROOT / "configs/splits.json").read_text())
        return cli.benchmark_contract([], POLICY, splits)[1]

    def write_reference(self, tasks=("OpenDrawer", "KettleBoiling"), skip=(), contract=None):
        """Set-B diagnostic_reference episodes for every selected scene and reference policy seed."""
        contract = contract or self.contract_hash()
        for task in tasks:
            for scene in (1000, 1001, 1002, 1003):
                for policy in (5, 6, 7, 8, 9):
                    if (task, scene, policy) not in skip:
                        write_episode(self.root / "reference" / task / f"{scene}-{policy}", "diagnostic_reference",
                                      task, scene, policy, scene < 1002, contract=contract)
        return self.root / "reference"

    def freeze(self, *extra, tasks=("OpenDrawer", "KettleBoiling"), reference=None):
        reference = reference or (self.root / "reference" if (self.root / "reference").exists() else self.write_reference(tasks))
        return self.main("freeze-benchmark", "--groups", self.groups(tasks),
                         "--task-configs", *(TASKS / f"{task}.json" for task in tasks),
                         "--models", "claude-opus-5-5", "claude-sonnet-5-5", "--output", self.root / "release.json",
                         "--reference-root", reference, *extra)

    def test_freeze_requires_usable_set_b_reference_episodes_under_the_frozen_hash(self):
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            self.main("freeze-benchmark", "--groups", self.groups(("OpenDrawer",)), "--task-configs",
                      TASKS / "OpenDrawer.json", "--models", "m", "--output", self.root / "release.json", "--allow-fewer")
        tasks = ("OpenDrawer",)
        stale = self.write_reference(tasks, skip={("OpenDrawer", 1003, 9)})
        write_episode(stale / "OpenDrawer" / "old-hash", "diagnostic_reference", "OpenDrawer", 1003, 9, True,
                      contract="old")
        write_episode(stale / "OpenDrawer" / "retry", "diagnostic_retry", "OpenDrawer", 1002, 9, True,
                      contract=self.contract_hash())
        (stale / "OpenDrawer" / "1001-5" / "result.json").write_text(json.dumps({"status": "infrastructure_error",
                                                                                "success": False}))
        with mock.patch("builtins.print") as printed:
            self.assertEqual(self.freeze("--allow-fewer", tasks=tasks, reference=stale), 2)
        self.assertFalse((self.root / "release.json").exists())
        message = printed.call_args.args[0]
        self.assertIn("('OpenDrawer', 1001, 5)", message)
        self.assertIn("('OpenDrawer', 1003, 9)", message)
        self.assertNotIn("1002", message)
        write_episode(stale / "OpenDrawer" / "fixed-1003-9", "diagnostic_reference", "OpenDrawer", 1003, 9, True,
                      contract=self.contract_hash())
        write_episode(stale / "OpenDrawer" / "rerun-1001-5", "diagnostic_reference", "OpenDrawer", 1001, 5, True,
                      contract=self.contract_hash())
        self.assertEqual(self.freeze("--allow-fewer", tasks=tasks, reference=stale), 0)

    def test_baseline_release_applies_the_run_release_checks(self):
        self.assertEqual(self.freeze("--allow-fewer"), 0)

        def baseline(task="OpenDrawer", scenes="1000,1002", policies="5,6"):
            return self.main("baseline", "--task-configs", TASKS / f"{task}.json", "--scene-seeds", scenes,
                             "--policy-seeds", policies, "--agent", "reissue", "--output", self.root / "b",
                             "--release", self.root / "release.json")
        self.assertEqual(baseline(), 0)
        self.assertEqual(len(self.calls()), 4)
        self.run_episode.reset_mock()
        for kwargs in ({"scenes": "1004"}, {"policies": "0"}, {"task": "CloseFridge"}):
            with self.subTest(**kwargs):
                self.assertEqual(baseline(**kwargs), 2)
        release = json.loads((self.root / "release.json").read_text())
        (self.root / "release.json").write_text(json.dumps({**release, "contract_hash": "other"}))
        self.assertEqual(baseline(), 2)
        self.run_episode.assert_not_called()

    def test_freeze_benchmark_writes_a_release_bound_to_the_shared_contract(self):
        self.assertEqual(self.freeze(), 2)
        self.assertFalse((self.root / "release.json").exists())
        self.assertEqual(self.freeze("--allow-fewer"), 0)
        release = json.loads((self.root / "release.json").read_text())
        self.assertEqual((release["status"], release["reference_policy_seeds"]), ("frozen", [5, 6, 7, 8, 9]))
        self.assertEqual(sorted(release["tasks"]), ["KettleBoiling", "OpenDrawer"])
        self.assertEqual(release["models"], ["claude-opus-5-5", "claude-sonnet-5-5"])
        self.assertEqual(self.screen(), 0)
        self.assertEqual(self.hashes(), {release["contract_hash"]})

    def test_analysis_modules_are_recorded_in_the_release_not_the_contract(self):
        import hashlib
        analysis = ("src/robot_benchmark/scorecard.py", "src/robot_benchmark/screening.py")
        self.assertFalse(set(analysis) & set(cli.CONTRACT_FILES))
        self.assertEqual(self.freeze("--allow-fewer"), 0)
        release = json.loads((self.root / "release.json").read_text())
        self.assertEqual(release["analysis_sha256"],
                         {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in analysis})
        self.assertFalse(set(analysis) & set(release["contract"]["implementation_sha256"]))

    def test_screen_and_baseline_agents_use_module_default_parameters(self):
        import inspect
        factories = [factory for _, factory in (*cli.SCREEN_MODES.values(), *cli.BASELINES.values())]
        for factory in factories:
            agent = factory(mock.Mock(), "KettleBoiling")
            with self.subTest(agent=type(agent).__name__):
                defaults = {name: p.default for name, p in inspect.signature(type(agent)).parameters.items()
                            if p.default is not inspect.Parameter.empty}
                self.assertEqual({name: getattr(agent, name) for name in defaults}, defaults)

    def agent_config(self, model="claude-opus-5-5"):
        path = self.root / f"{model}.json"
        path.write_text(json.dumps({"provider": "json_http", "model": model}))
        return path

    def run_command(self, *extra, task=TASKS / "OpenDrawer.json", model="claude-opus-5-5"):
        with mock.patch.object(cli, "HTTPAgent"):
            return self.main("run", "--task-config", task, "--agent-config", self.agent_config(model),
                             "--output", self.root / "run", *extra)

    def test_one_contract_hash_for_screening_baselines_and_llm_runs(self):
        self.assertEqual(self.screen(), 0)
        self.assertEqual(self.main("baseline", "--task-configs", TASKS / "OpenDrawer.json", "--scene-seeds", "1000",
                                   "--policy-seeds", "5", "--agent", "reissue", "--output", self.root / "b"), 0)
        self.assertEqual(self.run_command("--development", "--seeds", "1000", "--policy-seeds", "5"), 0)
        self.assertEqual(self.freeze("--allow-fewer"), 0)
        self.assertEqual(self.run_command("--release", self.root / "release.json", "--seeds", "1000,1002",
                                          "--policy-seeds", "5,6"), 0)
        self.assertEqual(len(self.hashes()), 1)
        self.assertEqual(self.calls()[-5:], [("OpenDrawer", 1000, 5, "llm_development"),
                                             ("OpenDrawer", 1000, 5, "llm"), ("OpenDrawer", 1000, 6, "llm"),
                                             ("OpenDrawer", 1002, 5, "llm"), ("OpenDrawer", 1002, 6, "llm")])

    def test_run_video_record_interval_is_recorded_but_not_hashed(self):
        self.assertEqual(self.run_command("--development", "--seeds", "1000", "--policy-seeds", "5"), 0)
        plain = self.hashes()
        self.run_episode.reset_mock()
        self.assertEqual(self.run_command("--development", "--seeds", "1000", "--policy-seeds", "5",
                                          "--video-record-interval", "10"), 0)
        self.assertEqual(self.hashes(), plain)
        self.assertEqual(self.run_episode.call_args.kwargs["task_config"]["video_record_interval"], 10)

    def test_every_command_writes_a_hash_named_contract_file(self):
        self.assertEqual(self.run_command("--development", "--seeds", "1000", "--policy-seeds", "5"), 0)
        self.assertEqual(self.main("feasibility", "--mode", "ordinary", "--seeds", "1", "--output", self.root / "f"), 0)
        for folder in (self.root / "run", self.root / "f"):
            with self.subTest(folder=folder.name):
                (path,) = folder.glob("contract*.json")
                self.assertEqual(path.name, f"contract-{digest(json.loads(path.read_text()))}.json")

    def test_benchmark_release_restricts_tasks_seeds_and_models(self):
        self.assertEqual(self.freeze("--allow-fewer"), 0)
        release = ("--release", self.root / "release.json")
        for extra, kwargs in ((("--seeds", "1000"), {}),
                              (("--seeds", "1000", "--policy-seeds", "4,5"), {}),
                              (("--seeds", "1000", "--policy-seeds", "0"), {}),
                              (("--seeds", "1004", "--policy-seeds", "5"), {}),
                              (("--seeds", "1000", "--policy-seeds", "5"), {"task": TASKS / "CloseFridge.json"}),
                              (("--seeds", "1000", "--policy-seeds", "5"), {"model": "other-model"})):
            with self.subTest(extra=extra, **kwargs):
                self.assertEqual(self.run_command(*release, *extra, **kwargs), 2)
        self.run_episode.assert_not_called()

    def test_legacy_cereal_and_bowl_release_path_still_works(self):
        config = json.loads((ROOT / "configs/cereal_and_bowl.json").read_text())
        splits = json.loads((ROOT / "configs/splits.json").read_text())
        path = self.root / "legacy-release.json"
        path.write_text(json.dumps({"schema_version": 2, "status": "frozen", "evaluation_seeds": splits["evaluation_seeds"],
                                    "contract_hash": digest(contract_payload(config, POLICY, splits))}))
        cereal = ROOT / "configs/cereal_and_bowl.json"
        self.assertEqual(self.run_command("--release", path, "--seeds", "1000", task=cereal), 0)
        self.assertEqual(self.calls(), [("CerealAndBowl", 1000, None, "llm")])
        self.assertEqual(self.run_command("--release", path, "--seeds", "1000", "--policy-seeds", "5", task=cereal), 2)
        self.assertEqual(self.run_command("--release", path, "--seeds", "1", task=cereal), 2)
        self.assertEqual(len(self.calls()), 1)

    def test_scorecard_reads_a_run_directory_and_writes_json(self):
        self.assertEqual(self.freeze("--allow-fewer"), 0)
        release = json.loads((self.root / "release.json").read_text())
        for index, (kind, model, policy, ok) in enumerate((("diagnostic_reference", "none", 5, True),
                                                           ("llm", "claude-opus-5-5", 5, False),
                                                           ("baseline_always_defer", "always_defer_v1", 5, True))):
            write_episode(self.root / "runs" / str(index), kind, "OpenDrawer", 1000, policy, ok,
                          contract=release["contract_hash"], model=model)
        output = self.root / "scorecard.json"
        self.assertEqual(self.main("scorecard", self.root / "runs", "--release", self.root / "release.json",
                                   "--output", output), 0)
        report = json.loads(output.read_text())
        self.assertEqual(sorted((s["kind"], s["model"]) for s in report["systems"]),
                         [("baseline_always_defer", "always_defer_v1"), ("llm", "claude-opus-5-5")])
        self.assertEqual(report["reference"]["leave_alone"]["successes"], 1)


if __name__ == "__main__":
    unittest.main()
