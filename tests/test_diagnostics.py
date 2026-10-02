import unittest

from robot_benchmark.diagnostics import PrivilegedRetrySupervisor, PrivilegedSequencer
from robot_benchmark.tasks.predicates import SEQUENCES

GOAL = "Pick the kettle from the counter and place it on a stove burner. Then turn the burner on."


class ScriptedEnv:
    """evaluate() returns the next scripted truth dict (the last one repeats)."""
    def __init__(self, *truths):
        self.truths = list(truths)

    def evaluate(self):
        return dict(self.truths.pop(0) if len(self.truths) > 1 else self.truths[0])


def observation(step, active=None, remaining=1500, max_interval=400):
    return {"goal": GOAL, "active_instruction": active, "step": step,
            "remaining_steps": remaining, "max_interval": max_interval, "reference_prompts": []}


class RetrySupervisorTests(unittest.TestCase):
    def test_identity_is_diagnostic(self):
        self.assertEqual(PrivilegedRetrySupervisor.identity, {"kind": "diagnostic", "model": "privileged_retry_v1"})
        self.assertEqual(PrivilegedSequencer.identity, {"kind": "diagnostic", "model": "privileged_sequencer_v1"})

    def test_default_success_check_interval_matches_reference(self):
        agent = PrivilegedRetrySupervisor(ScriptedEnv({"success": False}))
        self.assertEqual((agent.interval, agent.stall_steps), (100, 300))
        self.assertEqual(agent.decide(observation(0)).decision, {"op": "run_policy", "steps": 100, "prompt": GOAL})

    def test_issues_goal_waits_then_reissues_after_stall(self):
        agent = PrivilegedRetrySupervisor(ScriptedEnv({"success": False}), interval=50)
        self.assertEqual(agent.decide(observation(0)).decision, {"op": "run_policy", "steps": 50, "prompt": GOAL})
        self.assertEqual(agent.decide(observation(50, GOAL)).decision, {"op": "run_policy", "steps": 50})
        self.assertEqual(agent.decide(observation(299, GOAL)).decision, {"op": "run_policy", "steps": 50})
        self.assertEqual(agent.decide(observation(300, GOAL)).decision, {"op": "run_policy", "steps": 50, "prompt": GOAL})
        self.assertEqual(agent.decide(observation(350, GOAL)).decision, {"op": "run_policy", "steps": 50})
        self.assertEqual(agent.decide(observation(600, GOAL)).decision["prompt"], GOAL)

    def test_steps_respect_interval_and_remaining_budget(self):
        agent = PrivilegedRetrySupervisor(ScriptedEnv({"success": False}), interval=50)
        self.assertEqual(agent.decide(observation(0, max_interval=30)).decision["steps"], 30)
        self.assertEqual(agent.decide(observation(10, GOAL, remaining=7)).decision["steps"], 7)

    def test_completes_as_soon_as_success(self):
        agent = PrivilegedRetrySupervisor(ScriptedEnv({"success": False}, {"success": True}), interval=50)
        agent.decide(observation(0))
        self.assertEqual(agent.decide(observation(50, GOAL)).decision, {"op": "complete"})


class SequencerTests(unittest.TestCase):
    def setUp(self):
        (self.first, self.p1), (self.second, self.p2) = SEQUENCES["KettleBoiling"]

    def truth(self, success=False, **values):
        return {"success": success, self.first: False, self.second: False, **values}

    def test_rejects_task_without_sequence(self):
        with self.assertRaises(ValueError):
            PrivilegedSequencer(ScriptedEnv(self.truth()), "OpenDrawer")

    def test_walks_steps_and_completes(self):
        env = ScriptedEnv(self.truth(), self.truth(), self.truth(**{self.first: True}),
                          self.truth(**{self.first: True}), self.truth(True, **{self.first: True, self.second: True}))
        agent = PrivilegedSequencer(env, "KettleBoiling")
        self.assertEqual(agent.decide(observation(0)).decision, {"op": "run_policy", "steps": 50, "prompt": self.p1})
        self.assertEqual(agent.decide(observation(50, self.p1)).decision, {"op": "run_policy", "steps": 50})
        self.assertEqual(agent.decide(observation(100, self.p1)).decision, {"op": "run_policy", "steps": 50, "prompt": self.p2})
        self.assertEqual(agent.decide(observation(150, self.p2)).decision, {"op": "run_policy", "steps": 50})
        self.assertEqual(agent.decide(observation(200, self.p2)).decision, {"op": "complete"})

    def test_regressed_step_is_prompted_again(self):
        agent = PrivilegedSequencer(ScriptedEnv(self.truth(**{self.second: True})), "KettleBoiling")
        self.assertEqual(agent.decide(observation(100, self.p2)).decision["prompt"], self.p1)

    def test_missing_predicate_or_predicate_error_raises(self):
        for truth in ({"success": False, self.first: False},
                      {"success": False, "predicate_error": "KeyError: 'burner'"}):
            agent = PrivilegedSequencer(ScriptedEnv(truth), "KettleBoiling")
            with self.assertRaisesRegex(RuntimeError, "diagnostic-only infrastructure error"):
                agent.decide(observation(0))

    def test_all_predicates_true_without_success_keeps_last_prompt(self):
        env = ScriptedEnv(self.truth(**{self.first: True, self.second: True}))
        agent = PrivilegedSequencer(env, "KettleBoiling", interval=40)
        self.assertEqual(agent.decide(observation(500, self.p2)).decision, {"op": "run_policy", "steps": 40})
        self.assertEqual(agent.decide(observation(540, self.p2)).decision, {"op": "run_policy", "steps": 40})


if __name__ == "__main__":
    unittest.main()
