import copy
from http.client import IncompleteRead
import json
import argparse
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from robot_benchmark import cli
from robot_benchmark.contracts import ModelReply
from tests.fakes import FakeEnvironment, FakePolicy, SENTINEL

ROOT = Path(__file__).resolve().parents[1]


class PublicAgent:
    def __init__(self, config, *, session_mode=False, spend_guard=None):
        self.identity = {"model": config["model"], "prompt_version": 6 if session_mode else 5}
        self.observations = []

    def decide(self, observation):
        self.observations.append(copy.deepcopy(observation))
        if observation["step"] == 0:
            return ModelReply({"op": "run_policy", "prompt": observation["goal"], "steps": 5})
        return ModelReply({"op": "complete"})


class CliSessionTests(unittest.TestCase):
    def inputs(self, folder):
        model = {"provider": "anthropic", "model": "claude-sonnet-5-5",
                 "endpoint": "https://api.anthropic.com/v1/messages"}
        plan = [{"task": "OpenDrawer", "scene_seed": seed, "policy_seed": 0,
                 "policy_label": label, "backend": backend, "expect_state": "a" * 64}
                for seed, label, backend in ((1, "K", "groot"), (2, "R", "pi05"))]
        workers = {"K": "http://127.0.0.1:8765", "R": "http://127.0.0.1:8766"}
        timing = {"version": 1, "call_seconds": {"claude-sonnet-5-5": 2.2},
                  "tasks": {"OpenDrawer": {"deadline_seconds": 37.5,
                            "story": {"text": "The food is cooling.", "clock_starts": SENTINEL,
                                      "limit_seconds": 10}}}}
        for name, data in (("plan", plan), ("workers", workers), ("model", model), ("time", timing)):
            (folder / f"{name}.json").write_text(json.dumps(data))
        return ["session", "--plan", str(folder / "plan.json"), "--workers", str(folder / "workers.json"),
                "--agent-config", str(folder / "model.json"), "--time-pressure", str(folder / "time.json"),
                "--session-id", "test-session", "--development", "--api-dollar-cap", "10",
                "--output", str(folder / "run")]

    def test_dry_run_validates_without_worker_contact_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            command = self.inputs(folder)
            model = json.loads((folder / "model.json").read_text())
            model["api_key_env"] = "MISSING_W3_TEST_KEY"
            (folder / "model.json").write_text(json.dumps(model))
            with mock.patch.object(cli, "RemotePolicy") as policy, mock.patch("builtins.print"):
                self.assertEqual(cli.main(command + ["--dry-run"]), 0)
            policy.assert_not_called()
            self.assertFalse((folder / "run").exists())

    def test_runs_ordered_episodes_and_projects_real_public_context(self):
        policies, agents, expected_states = [], [], []

        def policy_factory(url):
            policy = FakePolicy()
            policy.identity = {"backend": "groot" if url.endswith("8765") else "pi05",
                               "checkpoint_manifest_sha256": "verified", "gpu": "test-gpu"}
            policies.append(policy)
            return policy

        def agent_factory(config, **kwargs):
            agent = PublicAgent(config, **kwargs)
            agents.append(agent)
            return agent

        def environment(task, split, camera_size, **kwargs):
            env = FakeEnvironment(success=lambda step: step >= 5, native="Open the drawer.")
            env.horizon = 750
            expected_states.append(kwargs.get("expected_start_state"))
            return env

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            command = self.inputs(folder)
            with mock.patch.object(cli, "RemotePolicy", side_effect=policy_factory), \
                    mock.patch.object(cli, "HTTPAgent", side_effect=agent_factory), \
                    mock.patch("robot_benchmark.adapters.robocasa.RoboCasaEnvironment", side_effect=environment), \
                    mock.patch.object(cli, "encode_episode_videos", return_value={}), mock.patch("builtins.print"):
                self.assertEqual(cli.main(command), 0)
            session = folder / "run/sessions/test-session"
            rows = [json.loads(line) for line in (session / "session.jsonl").read_text().splitlines()]
            self.assertEqual([row["policy_label"] for row in rows], ["K", "R"])
            self.assertEqual([row["index"] for row in rows], [0, 1])
            self.assertEqual(set(rows[0]), {"session_id", "index", "policy_label", "backend", "task",
                                           "scene_seed", "policy_seed", "episode_dir"})
            self.assertEqual(expected_states, ["a" * 64, "a" * 64])
            for row in rows:
                manifest = json.loads((session / row["episode_dir"] / "manifest.json").read_text())
                self.assertEqual(manifest["kind"], "llm_development")
                self.assertEqual(manifest["agent"]["prompt_version"], 6)
            self.assertEqual(len(agents), 1, "one supervisor instance must serve the session")
            self.assertEqual(agents[0].observations[0]["experience"], [])
            later = agents[0].observations[2]
            self.assertEqual(later["policy"], "R")
            self.assertTrue(later["experience"][0]["outcome"]["success"])
            self.assertNotIn(SENTINEL, json.dumps(later))
            self.assertNotIn("backend", json.dumps(later["experience"]))
            self.assertNotIn("scene_seed", json.dumps(later["experience"]))

    def test_worker_backend_mismatch_stops_before_model_construction(self):
        wrong = mock.Mock(identity={"backend": "pi05", "checkpoint_manifest_sha256": "verified"})
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            command = self.inputs(folder)
            with mock.patch.object(cli, "RemotePolicy", return_value=wrong), \
                    mock.patch.object(cli, "HTTPAgent") as agent, mock.patch("builtins.print"):
                self.assertEqual(cli.main(command), 2)
            agent.assert_not_called()
            self.assertFalse((folder / "run/sessions/test-session").exists())

    def test_failed_worker_health_stops_before_the_next_backend_runs(self):
        first = FakePolicy()
        first.identity = {"backend": "groot", "checkpoint_manifest_sha256": "verified"}
        second = FakePolicy()
        second.identity = {"backend": "pi05", "checkpoint_manifest_sha256": "verified"}
        errors = (ConnectionError("health refused"), IncompleteRead(b"partial health response", 17))
        for error in errors:
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                command = self.inputs(folder)
                def environment(*args, **kwargs):
                    env = FakeEnvironment(step_error=ConnectionError("worker died during rollout"))
                    env.horizon = 750
                    return env
                with mock.patch.object(cli, "RemotePolicy", side_effect=[first, second, error]), \
                        mock.patch.object(cli, "HTTPAgent", side_effect=PublicAgent), \
                        mock.patch("robot_benchmark.adapters.robocasa.RoboCasaEnvironment", side_effect=environment), \
                        mock.patch.object(cli, "encode_episode_videos", return_value={}), mock.patch("builtins.print"):
                    self.assertEqual(cli.main(command), 1)
                session = folder / "run/sessions/test-session"
                rows = [json.loads(line) for line in (session / "session.jsonl").read_text().splitlines()]
                self.assertEqual(len(rows), 1, "Do not attempt an interleaved backend after the failed worker dies")
                result = json.loads((session / "episodes/0000/result.json").read_text())
                self.assertEqual(result["status"], "infrastructure_error")
                self.assertEqual(result["session_stop"], "policy_worker_unavailable")
                self.assertIn(type(error).__name__, result["session_stop_error"])
                state = json.loads((session / "session_result.json").read_text())
                self.assertEqual(state["status"], "policy_worker_unavailable")

    def test_healthy_worker_after_simulator_failure_allows_next_episode(self):
        first = FakePolicy()
        first.identity = {"backend": "groot", "checkpoint_manifest_sha256": "verified"}
        second = FakePolicy()
        second.identity = {"backend": "pi05", "checkpoint_manifest_sha256": "verified"}
        failed = FakeEnvironment(step_error=RuntimeError("simulator render failure"))
        healthy = FakeEnvironment(success=lambda step: step >= 5)
        failed.horizon = healthy.horizon = 750
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            command = self.inputs(folder)
            with mock.patch.object(cli, "RemotePolicy", side_effect=[first, second, first]), \
                    mock.patch.object(cli, "HTTPAgent", side_effect=PublicAgent), \
                    mock.patch("robot_benchmark.adapters.robocasa.RoboCasaEnvironment", side_effect=[failed, healthy]), \
                    mock.patch.object(cli, "encode_episode_videos", return_value={}), mock.patch("builtins.print"):
                self.assertEqual(cli.main(command), 0)
            session = folder / "run/sessions/test-session"
            state = json.loads((session / "session_result.json").read_text())
            self.assertEqual(state["status"], "completed")
            self.assertEqual(state["attempted_episodes"], 2)
            first_result = json.loads((session / "episodes/0000/result.json").read_text())
            self.assertNotIn("session_stop", first_result)
            self.assertEqual(first_result["status"], "infrastructure_error")

    def test_replaced_worker_identity_stops_after_an_infrastructure_failure(self):
        first = FakePolicy()
        first.identity = {"backend": "groot", "checkpoint_manifest_sha256": "verified"}
        second = FakePolicy()
        second.identity = {"backend": "pi05", "checkpoint_manifest_sha256": "verified"}
        replacement = FakePolicy()
        replacement.identity = {**first.identity, "checkpoint_manifest_sha256": "different"}
        failed = FakeEnvironment(step_error=RuntimeError("worker failed"))
        failed.horizon = 750
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            command = self.inputs(folder)
            with mock.patch.object(cli, "RemotePolicy", side_effect=[first, second, replacement]), \
                    mock.patch.object(cli, "HTTPAgent", side_effect=PublicAgent), \
                    mock.patch("robot_benchmark.adapters.robocasa.RoboCasaEnvironment", return_value=failed), \
                    mock.patch.object(cli, "encode_episode_videos", return_value={}), mock.patch("builtins.print"):
                self.assertEqual(cli.main(command), 1)
            session = folder / "run/sessions/test-session"
            state = json.loads((session / "session_result.json").read_text())
            self.assertEqual(state["attempted_episodes"], 1)
            first_result = json.loads((session / "episodes/0000/result.json").read_text())
            self.assertEqual(first_result["session_stop"], "policy_worker_unavailable")
            self.assertIn("identity changed", first_result["session_stop_error"])

    def test_dry_run_prices_a_sail_model_at_its_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            command = self.inputs(folder)
            model = {"provider": "anthropic", "model": "moonshotai/Kimi-K3",
                     "endpoint": "https://api.sailresearch.com/v1/messages", "api_key_env": "SAIL_API_KEY"}
            (folder / "model.json").write_text(json.dumps(model))
            timing = json.loads((folder / "time.json").read_text())
            timing["call_seconds"] = {"moonshotai/Kimi-K3": 4.7}
            (folder / "time.json").write_text(json.dumps(timing))
            with mock.patch("builtins.print") as output:
                self.assertEqual(cli.main(command + ["--dry-run"]), 0)
            report = json.loads(output.call_args.args[0])
            self.assertAlmostEqual(report["minimum_required_reservation"], 2.5 + 12.5 * 4096 / 1e6)

    def test_time_config_changes_session_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            command = self.inputs(folder)
            with mock.patch("builtins.print") as output:
                cli.main(command + ["--dry-run"])
            first = json.loads(output.call_args.args[0])["session_contract_hash"]
            timing = json.loads((folder / "time.json").read_text())
            timing["call_seconds"]["claude-sonnet-5-5"] = 3.0
            (folder / "time.json").write_text(json.dumps(timing))
            with mock.patch("builtins.print") as output:
                cli.main(command + ["--dry-run"])
            second = json.loads(output.call_args.args[0])["session_contract_hash"]
            self.assertNotEqual(first, second)

    def test_pairing_cli_preserves_source_plan_and_refuses_overwrite(self):
        from tests import test_session
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.inputs(folder)
            plan = [test_session.plan()]
            source = folder / "pair-plan.json"
            source.write_text(json.dumps(plan))
            test_session.BaselinePairingTests().baseline(folder / "baselines")
            output = folder / "paired.json"
            command = ["pair-session", "--plan", str(source), "--reference-root", str(folder / "baselines"),
                       "--output", str(output)]
            with mock.patch("builtins.print"):
                self.assertEqual(cli.main(command), 0)
            paired = json.loads(output.read_text())
            self.assertEqual(paired[0]["expect_state"], "a" * 64)
            self.assertEqual(json.loads(source.read_text()), plan)
            self.assertTrue(output.with_suffix(".pairing.json").exists())
            original = output.read_bytes()
            with mock.patch("builtins.print"):
                self.assertEqual(cli.main(command), 2)
            self.assertEqual(output.read_bytes(), original)

    def test_live_session_requires_explicit_cap_before_worker_contact(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            command = self.inputs(folder)
            offset = command.index("--api-dollar-cap")
            del command[offset:offset + 2]
            with mock.patch.object(cli, "RemotePolicy") as policy, mock.patch("builtins.print"):
                self.assertEqual(cli.main(command), 2)
            policy.assert_not_called()

    def test_insufficient_cap_cannot_start_workers_or_model(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            command = self.inputs(folder)
            command[command.index("--api-dollar-cap") + 1] = "0.01"
            with mock.patch.object(cli, "RemotePolicy") as policy, \
                    mock.patch.object(cli, "HTTPAgent") as agent, mock.patch("builtins.print"):
                self.assertEqual(cli.main(command), 2)
            policy.assert_not_called()
            agent.assert_not_called()

    def test_release_tag_guard_requires_matching_clean_checkout(self):
        def git_state(tagged, head, dirty):
            return [mock.Mock(stdout=tagged), mock.Mock(stdout=head), mock.Mock(stdout=dirty)]

        with mock.patch.object(cli.subprocess, "run", side_effect=git_state("release", "release", "")):
            self.assertEqual(cli.check_session_release_tag("release-test"), "release")
        for values in (("release", "changed", ""), ("release", "release", " M config.json"),
                       ("release", "release", "?? source.py")):
            with self.subTest(values=values), mock.patch.object(cli.subprocess, "run", side_effect=git_state(*values)):
                with self.assertRaisesRegex(ValueError, "clean checkout"):
                    cli.check_session_release_tag("release-test")
        with mock.patch.object(cli.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["git"])):
            with self.assertRaisesRegex(ValueError, "must exist"):
                cli.check_session_release_tag("missing-tag")

    def test_dollar_cap_type_rejects_nonfinite_or_nonpositive_values(self):
        self.assertEqual(cli.positive_float("1.25"), 1.25)
        for value in ("0", "-1", "nan", "inf", "True", "none"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                cli.positive_float(value)


class FrozenSessionTests(unittest.TestCase):
    def fixture(self, folder):
        from tests.test_session import BaselinePairingTests, plan
        command = CliSessionTests().inputs(folder)
        source = [plan()]
        (folder / "configs/final/plans").mkdir(parents=True)
        (folder / "configs/final/plans/scene0.json").write_text(json.dumps(source))
        model = json.loads((folder / "model.json").read_text())
        (folder / "configs/model-test.json").write_text(json.dumps(model))
        timing = json.loads((folder / "time.json").read_text())
        timing["status"] = "frozen"
        (folder / "time.json").write_text(json.dumps(timing))
        (folder / "configs/time_pressure.json").write_text(json.dumps(timing))
        baseline = BaselinePairingTests().baseline(folder / "baselines")
        paired, pairs = cli.attach_baseline_states(source, folder / "baselines", {"OpenDrawer"})
        (folder / "plan.json").write_text(json.dumps(paired))
        (folder / "workers.json").write_text(json.dumps({"K": "http://127.0.0.1:8765"}))
        audit = {"source_plan_hash": cli.digest(source), "paired_plan_hash": cli.digest(paired),
                 "reference_root": str(folder / "baselines"), "pairs": pairs}
        (folder / "plan.pairing.json").write_text(json.dumps(audit))
        args = cli.parser().parse_args(command)
        return args, paired, model, timing, baseline

    def check(self, folder, args, plan, model, timing):
        with mock.patch.object(cli, "PROJECT_ROOT", folder), \
                mock.patch.object(cli, "DEFAULT_TIME_PRESSURE", folder / "configs/time_pressure.json"):
            return cli.check_session_frozen_inputs(args, plan, model, timing, {"OpenDrawer"})

    def test_valid_inputs_recheck_baselines_and_preserve_failed_twins(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            args, plan, model, timing, _ = self.fixture(folder)
            pairs = self.check(folder, args, plan, model, timing)
            self.assertEqual(len(pairs), 1)
            cli.check_session_baseline_contracts(plan, pairs, {"K": "code-contract"})
            with self.assertRaisesRegex(ValueError, "baseline contract"):
                cli.check_session_baseline_contracts(plan, pairs, {"K": "changed-contract"})

    def test_nonfrozen_or_modified_timing_and_model_are_rejected(self):
        for change in ("provisional", "timing", "story", "model", "experience", "recording"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                args, plan, model, timing, _ = self.fixture(folder)
                if change == "provisional":
                    timing["status"] = "provisional"
                elif change == "timing":
                    timing["call_seconds"][model["model"]] = 7
                elif change == "story":
                    timing["tasks"]["OpenDrawer"]["story"]["limit_seconds"] = None
                    (folder / "configs/time_pressure.json").write_text(json.dumps(timing))
                elif change == "model":
                    model["timeout_seconds"] = 99
                elif change == "experience":
                    args.experience_limit = 2
                else:
                    args.video_record_interval = 1
                with self.assertRaises(ValueError):
                    self.check(folder, args, plan, model, timing)

    def test_plan_audit_or_baseline_mutation_is_rejected(self):
        for change in ("plan", "source_hash", "paired_hash", "pairs", "state", "contract", "missing_audit"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                args, plan, model, timing, baseline = self.fixture(folder)
                audit_path = folder / "plan.pairing.json"
                audit = json.loads(audit_path.read_text())
                if change == "plan":
                    plan[0]["scene_seed"] = 1
                elif change in ("source_hash", "paired_hash"):
                    audit["source_plan_hash" if change == "source_hash" else "paired_plan_hash"] = "b" * 64
                elif change == "pairs":
                    audit["pairs"] = []
                elif change == "state":
                    (baseline / "evaluator/states.jsonl").write_text(json.dumps({"step": 0, "state_sha256": "b" * 64}))
                elif change == "contract":
                    manifest = json.loads((baseline / "manifest.json").read_text())
                    manifest["contract_hash"] = "changed-contract"
                    (baseline / "manifest.json").write_text(json.dumps(manifest))
                if change == "missing_audit":
                    audit_path.unlink()
                else:
                    audit_path.write_text(json.dumps(audit))
                with self.assertRaises(ValueError):
                    self.check(folder, args, plan, model, timing)

    def test_final_input_rejection_precedes_worker_and_model_contact(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            command = CliSessionTests().inputs(folder)
            command[command.index("--development"):command.index("--development") + 1] = ["--release-tag", "test-tag"]
            with mock.patch.object(cli, "check_session_release_tag", return_value="commit"), \
                    mock.patch.object(cli, "RemotePolicy") as policy, \
                    mock.patch.object(cli, "HTTPAgent") as agent, mock.patch("builtins.print"):
                self.assertEqual(cli.main(command), 2)
            policy.assert_not_called()
            agent.assert_not_called()

    def test_final_baseline_contract_mismatch_precedes_model_construction(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            args, plan, model, timing, _ = self.fixture(folder)
            args.release_tag = "test-tag"
            args.dry_run = False
            policy = mock.Mock(identity={"backend": "groot", "checkpoint_manifest_sha256": "verified"})
            with mock.patch.object(cli, "PROJECT_ROOT", folder), \
                    mock.patch.object(cli, "DEFAULT_TIME_PRESSURE", folder / "configs/time_pressure.json"), \
                    mock.patch.object(cli, "check_session_release_tag", return_value="commit"), \
                    mock.patch.object(cli, "implementation_hashes", return_value={"fixture": "test-code"}), \
                    mock.patch.object(cli, "RemotePolicy", return_value=policy), \
                    mock.patch.object(cli, "HTTPAgent") as agent:
                with self.assertRaisesRegex(ValueError, "baseline contract"):
                    cli.command_session(args)
            agent.assert_not_called()
            self.assertFalse((folder / "run/sessions/test-session").exists())

    def test_matching_final_inputs_run_the_existing_episode_path(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            args, plan, model, timing, baseline = self.fixture(folder)
            args.release_tag = "test-tag"
            policy = FakePolicy()
            policy.identity = {"backend": "groot", "checkpoint_manifest_sha256": "verified"}
            env = FakeEnvironment(success=lambda step: step >= 5, native="Open the drawer.")
            env.horizon = 750
            with mock.patch.object(cli, "PROJECT_ROOT", folder), \
                    mock.patch.object(cli, "DEFAULT_TIME_PRESSURE", folder / "configs/time_pressure.json"), \
                    mock.patch.object(cli, "check_session_release_tag", return_value="commit"), \
                    mock.patch.object(cli, "implementation_hashes", return_value={"fixture": "test-code"}), \
                    mock.patch.object(cli, "RemotePolicy", return_value=policy), \
                    mock.patch.object(cli, "HTTPAgent", side_effect=PublicAgent), \
                    mock.patch("robot_benchmark.adapters.robocasa.RoboCasaEnvironment", return_value=env), \
                    mock.patch.object(cli, "encode_episode_videos", return_value={}), mock.patch("builtins.print"):
                _, contract_hash = cli.benchmark_contract([cli.task_pool()["OpenDrawer"]], policy.identity,
                                                          cli.validate_splits(cli.read_json(args.splits)))
                manifest = json.loads((baseline / "manifest.json").read_text())
                manifest["contract_hash"] = contract_hash
                (baseline / "manifest.json").write_text(json.dumps(manifest))
                audit_path = folder / "plan.pairing.json"
                audit = json.loads(audit_path.read_text())
                audit["pairs"][0]["baseline_contract_hash"] = contract_hash
                audit_path.write_text(json.dumps(audit))
                self.assertEqual(cli.command_session(args), 0)
            episode = folder / "run/sessions/test-session/episodes/0000"
            retained = json.loads((episode / "manifest.json").read_text())
            self.assertEqual(retained["kind"], "llm")
            self.assertEqual(retained["contract_hash"], contract_hash)
            session_contract = json.loads((episode.parent.parent / "manifest.json").read_text())["session_contract"]
            self.assertEqual(session_contract["baseline_pairing"], audit["pairs"])


if __name__ == "__main__":
    unittest.main()
