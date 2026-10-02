import unittest

from robot_benchmark.baselines import AlwaysDeferAgent, ReissueAgent
from robot_benchmark.contracts import Limits, ModelReply
from robot_benchmark.runner import Runner
from tests.fakes import FakeEnvironment, FakePolicy, reference_prompts

GOAL = "goal text"
PUBLIC = {"goal", "active_instruction", "remaining_steps", "max_interval", "step"}


class PublicOnly(dict):
    """Observation that raises when a baseline reads a non-public key."""

    def __getitem__(self, key):
        if key not in PUBLIC:
            raise AssertionError(f"non-public observation key read: {key}")
        return super().__getitem__(key)

    def get(self, key, default=None):
        return self[key] if key in self else default


def public(**fields):
    return PublicOnly({"goal": GOAL, "active_instruction": None, "remaining_steps": 250, "max_interval": 100,
                       "step": 0, **fields})


def episode(agent):
    runner = Runner(FakeEnvironment(), FakePolicy(), agent, reference_prompts(), GOAL,
                    Limits(max_steps=250, max_decisions=100, max_interval=100))
    return runner.run(0)


class BaselineTests(unittest.TestCase):
    def test_identities(self):
        self.assertEqual(AlwaysDeferAgent().identity, {"kind": "baseline", "model": "always_defer_v1"})
        self.assertEqual(ReissueAgent().identity, {"kind": "baseline", "model": "reissue_every_100_v1"})
        self.assertEqual(ReissueAgent(every=40).identity, {"kind": "baseline", "model": "reissue_every_40_v1"})

    def test_reissue_rejects_invalid_every(self):
        for bad in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                ReissueAgent(every=bad)

    def test_always_defer_submits_once_and_completes_with_one_step_left(self):
        result = episode(AlwaysDeferAgent())
        self.assertIn(result["status"], ("success", "false_completion"))
        self.assertEqual((result["prompt_submissions"], result["steps"]), (1, 249))
        self.assertEqual(result["intervals"], [100, 100, 49])

    def test_reissue_every_100_resubmits_goal(self):
        result = episode(ReissueAgent(every=100))
        self.assertIn(result["status"], ("success", "false_completion"))
        self.assertEqual((result["prompt_submissions"], result["steps"]), (3, 249))
        self.assertEqual(result["prompt_restarts"], 2)

    def test_reissue_every_shorter_than_max_interval(self):
        result = episode(ReissueAgent(every=60))
        self.assertEqual(result["intervals"], [60, 60, 60, 60, 9])
        self.assertEqual(result["prompt_submissions"], 5)

    def test_decisions_and_public_only_reads(self):
        defer, reissue = AlwaysDeferAgent(), ReissueAgent(every=30)
        for agent in (defer, reissue):
            self.assertIsInstance(agent.decide(public()), ModelReply)
        self.assertEqual(defer.decide(public()).decision, {"op": "run_policy", "prompt": GOAL, "steps": 100})
        self.assertEqual(defer.decide(public(active_instruction=GOAL, remaining_steps=50, step=200)).decision,
                         {"op": "run_policy", "steps": 49})
        self.assertEqual(reissue.decide(public(active_instruction=GOAL, step=30)).decision,
                         {"op": "run_policy", "prompt": GOAL, "steps": 30})
        for agent in (defer, reissue):
            self.assertEqual(agent.decide(public(remaining_steps=1)).decision, {"op": "complete"})
            self.assertEqual(agent.decide(public(remaining_steps=2)).decision["steps"], 1)


if __name__ == "__main__":
    unittest.main()
