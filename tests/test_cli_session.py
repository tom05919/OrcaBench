import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from robot_benchmark import cli
from robot_benchmark.contracts import ModelReply
from tests.fakes import FakeEnvironment, FakePolicy, SENTINEL

ROOT = Path(__file__).resolve().parents[1]


class PublicAgent:
    def __init__(self, config, *, session_mode=False):
        self.identity = {"model": config["model"], "prompt_version": 6 if session_mode else 5}
        self.observations = []

    def decide(self, observation):
        self.observations.append(copy.deepcopy(observation))
        if observation["step"] == 0:
            return ModelReply({"op": "run_policy", "prompt": observation["goal"], "steps": 5})
        return ModelReply({"op": "complete"})


class CliSessionTests(unittest.TestCase):
    def inputs(self, folder):
        model = {"provider": "json_http", "model": "test-model", "endpoint": "http://localhost:9000"}
        plan = [{"task": "OpenDrawer", "scene_seed": seed, "policy_seed": 0,
                 "policy_label": label, "backend": backend, "expect_state": "a" * 64}
                for seed, label, backend in ((1, "K", "groot"), (2, "R", "pi05"))]
        workers = {"K": "http://127.0.0.1:8765", "R": "http://127.0.0.1:8766"}
        timing = {"version": 1, "call_seconds": {"test-model": 2.2},
                  "tasks": {"OpenDrawer": {"deadline_seconds": 37.5,
                            "story": {"text": "The food is cooling.", "clock_starts": SENTINEL,
                                      "limit_seconds": 10}}}}
        for name, data in (("plan", plan), ("workers", workers), ("model", model), ("time", timing)):
            (folder / f"{name}.json").write_text(json.dumps(data))
        return ["session", "--plan", str(folder / "plan.json"), "--workers", str(folder / "workers.json"),
                "--agent-config", str(folder / "model.json"), "--time-pressure", str(folder / "time.json"),
                "--session-id", "test-session", "--development", "--output", str(folder / "run")]

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

    def test_time_config_changes_session_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            command = self.inputs(folder)
            with mock.patch("builtins.print") as output:
                cli.main(command + ["--dry-run"])
            first = json.loads(output.call_args.args[0])["session_contract_hash"]
            timing = json.loads((folder / "time.json").read_text())
            timing["call_seconds"]["test-model"] = 3.0
            (folder / "time.json").write_text(json.dumps(timing))
            with mock.patch("builtins.print") as output:
                cli.main(command + ["--dry-run"])
            second = json.loads(output.call_args.args[0])["session_contract_hash"]
            self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
