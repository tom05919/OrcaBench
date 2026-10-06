import json
import tempfile
import unittest
from pathlib import Path

from robot_benchmark.baselines import ReplayAgent
from robot_benchmark.cli import BASELINES, accepted_decisions

LOGGED = [
    {"op": "run_policy", "prompt": "Turn on the faucet by pushing the handle.", "steps": 100},
    {"op": "run_policy", "steps": 60},
    {"op": "run_policy", "prompt": "Lift the handle up to turn on the water.", "steps": 100},
    {"op": "complete"},
]
OBSERVATION = {"goal": "Turn on the sink faucet."}


def replay(ablation, decisions=LOGGED):
    agent = ReplayAgent(decisions, ablation, "seed-1000-p0-x")
    return [agent.decide(OBSERVATION).decision for _ in decisions], agent


class ReplayAgentTests(unittest.TestCase):
    def test_exact_returns_the_logged_decisions(self):
        self.assertEqual(replay("exact")[0], LOGGED)

    def test_native_text_keeps_timing_and_restarts_but_restores_the_goal(self):
        got = replay("native_text")[0]
        self.assertEqual([d.get("steps") for d in got], [100, 60, 100, None])
        self.assertEqual([d.get("prompt") for d in got],
                         ["Turn on the sink faucet.", None, "Turn on the sink faucet.", None])

    def test_no_interruption_submits_the_goal_once_and_keeps_every_interval(self):
        got = replay("no_interruption")[0]
        self.assertEqual([d.get("prompt") for d in got], ["Turn on the sink faucet.", None, None, None])
        self.assertEqual([d.get("steps") for d in got], [100, 60, 100, None])
        self.assertEqual(got[-1], {"op": "complete"})

    def test_logged_decisions_are_not_mutated(self):
        replay("native_text")
        self.assertEqual(LOGGED[0]["prompt"], "Turn on the faucet by pushing the handle.")

    def test_identity_names_the_ablation_and_source_and_never_a_model(self):
        agent = ReplayAgent(LOGGED, "native_text", "seed-1000-p0-x")
        self.assertEqual(agent.identity, {"kind": "diagnostic", "model": "replay_native_text_v1",
                                          "source_episode": "seed-1000-p0-x"})

    def test_rejects_an_unknown_ablation_and_an_unfinished_log(self):
        with self.assertRaises(ValueError):
            ReplayAgent(LOGGED, "other")
        with self.assertRaises(ValueError):
            ReplayAgent(LOGGED[:-1], "exact")

    def test_running_past_the_log_raises(self):
        agent = ReplayAgent(LOGGED, "exact")
        for _ in LOGGED:
            agent.decide(OBSERVATION)
        with self.assertRaises(RuntimeError):
            agent.decide(OBSERVATION)


class LoadAndRegistryTests(unittest.TestCase):
    def test_accepted_decisions_skips_rejected_replies(self):
        with tempfile.TemporaryDirectory() as folder:
            lines = [{"decision": LOGGED[0], "accepted": True}, {"decision": {"op": "bad"}, "accepted": False},
                     {"decision": LOGGED[3], "accepted": True}]
            Path(folder, "decisions.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
            self.assertEqual(accepted_decisions(Path(folder)), [LOGGED[0], LOGGED[3]])

    def test_reissue_sweep_has_distinct_identities(self):
        names = {}
        for key in ("reissue", "reissue_50", "reissue_200", "reissue_400"):
            kind, factory = BASELINES[key]
            self.assertEqual(kind, "baseline_reissue")
            names[key] = factory(None, "CloseFridge").identity["model"]
        self.assertEqual(len(set(names.values())), 4)
        self.assertEqual(names["reissue_200"], "reissue_every_200_v1")


if __name__ == "__main__":
    unittest.main()


class ReplayCommandTests(unittest.TestCase):
    """Plumbing only: the command reads a source episode and hands a ReplayAgent to run_episode."""

    def setUp(self):
        from unittest import mock
        from tests.test_cli import POLICY
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "seed-1000-p1-source"
        self.source.mkdir()
        (self.source / "manifest.json").write_text(json.dumps({"task": "OpenDrawer", "scene_seed": 1000, "policy_seed": 1}))
        (self.source / "evaluator").mkdir()
        (self.source / "evaluator" / "states.jsonl").write_text(json.dumps({"step": 0, "state_sha256": "a" * 64}) + "\n")
        (self.source / "decisions.jsonl").write_text("\n".join(
            json.dumps({"decision": d, "accepted": True}) for d in [LOGGED[0], LOGGED[3]]) + "\n")
        from robot_benchmark import cli
        self.cli = cli
        patcher = mock.patch.object(cli, "RemotePolicy", return_value=mock.Mock(identity=POLICY))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch("builtins.print")
        self.print = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(cli, "run_episode", return_value={"status": "success"})
        self.run_episode = patcher.start()
        self.addCleanup(patcher.stop)
        self.config = Path(cli.__file__).resolve().parents[2] / "configs" / "tasks" / "OpenDrawer.json"

    def replay(self, task_config=None, ablation="native_text"):
        return self.cli.main(["replay", "--task-config", str(task_config or self.config), "--source", str(self.source),
                              "--ablation", ablation, "--video-record-interval", "5", "--output", str(self.root / "out")])

    def test_runs_the_source_pair_with_a_replay_agent_of_the_chosen_ablation(self):
        self.assertEqual(self.replay(), 0)
        kwargs = self.run_episode.call_args.kwargs
        self.assertEqual((kwargs["seed"], kwargs["policy_seed"], kwargs["kind"]), (1000, 1, "diagnostic_replay"))
        agent = kwargs["agent_factory"](None)
        self.assertEqual(agent.identity["model"], "replay_native_text_v1")
        self.assertEqual(agent.identity["source_episode"], "seed-1000-p1-source")
        self.assertEqual(kwargs["task_config"]["video_record_interval"], 5)
        self.assertEqual(kwargs["expected_start_state"], "a" * 64)  # the replay must start from the source's scene

    def test_expect_state_overrides_the_sources_start_for_a_source_from_another_machine(self):
        self.assertEqual(self.cli.main(["replay", "--task-config", str(self.config), "--source", str(self.source),
                                        "--ablation", "exact", "--expect-state", "c" * 64,
                                        "--output", str(self.root / "out2")]), 0)
        self.assertEqual(self.run_episode.call_args.kwargs["expected_start_state"], "c" * 64)

    def test_refuses_a_source_from_another_task(self):
        other = self.config.with_name("CloseFridge.json")
        self.assertEqual(self.replay(other), 2)
        self.assertIn("source episode is OpenDrawer", self.print.call_args.args[0])
        self.run_episode.assert_not_called()

    def test_infrastructure_error_gives_a_nonzero_exit_status(self):
        self.run_episode.return_value = {"status": "infrastructure_error"}
        self.assertEqual(self.replay(), 1)
