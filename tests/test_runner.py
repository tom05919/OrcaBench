import unittest

from robot_benchmark.contracts import Limits, Skill

from tests.fakes import (
    SENTINEL,
    CaptureRecords,
    FakeAgent,
    FakeEnvironment,
    FakePolicy,
    action,
    make_runner,
)


class RunnerValidationTests(unittest.TestCase):
    def test_reference_prompt_ids_must_be_nonempty_and_unique(self):
        common = (FakeEnvironment(), FakePolicy(), FakeAgent([]), "goal", Limits(1))
        with self.assertRaisesRegex(ValueError, "nonempty and unique"):
            from robot_benchmark.runner import Runner

            Runner(*common[:3], [Skill("", "i", "d", {})], *common[3:])
        with self.assertRaisesRegex(ValueError, "nonempty and unique"):
            from robot_benchmark.runner import Runner

            duplicate = [Skill("same", "i", "d", {}), Skill("same", "j", "e", {})]
            Runner(*common[:3], duplicate, *common[3:])

    def test_malformed_decisions_consume_budget_without_physics(self):
        env = FakeEnvironment()
        runner = make_runner(
            [
                {"op": "run_policy", "prompt": "pick", "steps": 0},
                {"op": "complete", "unexpected": True},
            ],
            env=env,
            limits=Limits(max_steps=5, max_decisions=2, max_interval=5),
        )

        result = runner.run(seed=7)

        self.assertEqual(result["status"], "decision_budget_exhausted")
        self.assertEqual(result["model_calls"], 2)
        self.assertEqual(result["steps"], 0)
        self.assertEqual(result["policy_calls"], 0)
        self.assertEqual(env.step_attempts, [])
        self.assertEqual([entry["accepted"] for entry in runner.history], [False, False])
        self.assertIsNotNone(runner.agent.observations[1]["last_error"])

    def test_interval_exceeding_remaining_budget_is_rejected_whole(self):
        env = FakeEnvironment()
        policy = FakePolicy(chunks=[[action(1), action(2), action(3)]])
        runner = make_runner(
            [
                {"op": "run_policy", "prompt": "pick", "steps": 2},
                {"op": "run_policy", "steps": 2},
                {"op": "complete"},
            ],
            env=env,
            policy=policy,
            limits=Limits(max_steps=3, max_decisions=3, max_interval=3),
        )

        result = runner.run(seed=11)

        self.assertEqual(result["status"], "false_completion")
        self.assertEqual(result["steps"], 2)
        self.assertEqual(len(env.step_attempts), 2)
        self.assertEqual([entry["accepted"] for entry in runner.history], [True, False, True])
        rejected = runner.history[1]
        self.assertEqual((rejected["step_before"], rejected["step_after"]), (2, 2))
        self.assertIn("remaining steps", rejected["error"])

    def test_observation_is_allowlisted_and_detached_from_runner_state(self):
        runner = make_runner([])
        runner.history = [{"nested": {"items": [1]}}]
        observation = runner.observation()

        self.assertNotIn(SENTINEL, repr(observation))
        self.assertEqual(set(observation["images"]), {
            "video.robot0_agentview_left",
            "video.robot0_agentview_right",
            "video.robot0_eye_in_hand",
        })
        observation["history"][0]["nested"]["items"].append(2)
        self.assertEqual(observation["active_instruction"], None)
        self.assertNotIn("active_skill", observation)
        self.assertNotIn("last_skill", observation)
        observation["reference_prompts"][0]["performance"]["success_rate"] = 1.0
        self.assertEqual(runner.history[0]["nested"]["items"], [1])
        self.assertIsNone(runner.reference_prompts["pick"].performance["success_rate"])

    def test_policy_observation_never_enters_agent_observation(self):
        policy = FakePolicy(chunks=[[action()]])
        runner = make_runner(
            [{"op": "run_policy", "prompt": "pick", "steps": 1}, {"op": "complete"}],
            policy=policy,
        )
        runner.run(seed=3)

        self.assertIn(SENTINEL, repr(policy.predict_calls[0][0]))
        for observation in runner.agent.observations:
            self.assertNotIn(SENTINEL, repr(observation))


class RunnerPolicyStateTests(unittest.TestCase):
    def test_omitted_prompt_consumes_the_existing_action_chunk(self):
        env = FakeEnvironment()
        policy = FakePolicy(chunks=[[action(1), action(2), action(3)]])
        runner = make_runner([], env=env, policy=policy)

        runner.apply({"op": "run_policy", "prompt": "pick the red bowl", "steps": 1})
        runner.apply({"op": "run_policy", "steps": 2})

        self.assertEqual(len(policy.predict_calls), 1)
        self.assertEqual([value["action.end_effector_position"][0] for value in env.step_attempts], [1, 2, 3])

    def test_new_prompt_is_forwarded_verbatim_and_discards_stale_actions(self):
        env = FakeEnvironment()
        policy = FakePolicy(chunks=[[action(1), action(2), action(3)], [action(10)]])
        runner = make_runner([], env=env, policy=policy)
        first = "  grasp whichever object is nearest  "
        second = "close the left cabinet door"

        runner.apply({"op": "run_policy", "prompt": first, "steps": 1})
        runner.apply({"op": "run_policy", "prompt": second, "steps": 1})

        self.assertEqual([call[1] for call in policy.predict_calls], [first, second])
        self.assertEqual(
            [value["action.end_effector_position"][0] for value in env.step_attempts],
            [1, 10],
        )
        self.assertEqual(runner.active_instruction, second)

    def test_resubmitting_same_prompt_restarts_policy_and_discards_queue(self):
        env = FakeEnvironment()
        policy = FakePolicy(chunks=[[action(1), action(2)], [action(10)]])
        runner = make_runner([], env=env, policy=policy)
        prompt = "pick the bowl"

        runner.apply({"op": "run_policy", "prompt": prompt, "steps": 1})
        runner.apply({"op": "run_policy", "prompt": prompt, "steps": 1})

        self.assertEqual([call[1] for call in policy.predict_calls], [prompt, prompt])
        self.assertEqual(
            [value["action.end_effector_position"][0] for value in env.step_attempts],
            [1, 10],
        )
        self.assertEqual(policy.reset_skill_calls, 2)

    def test_prompt_is_required_before_continuation(self):
        runner = make_runner([])
        with self.assertRaisesRegex(ValueError, "prompt"):
            runner.apply({"op": "run_policy", "steps": 1})

    def test_prompt_metrics_distinguish_submissions_changes_and_restarts(self):
        policy = FakePolicy(chunks=[
            [action(1), action(2), action(3), action(4)],
            [action(10), action(11)],
            [action(20)],
        ])
        runner = make_runner(
            [
                {"op": "run_policy", "prompt": "pick", "steps": 1},
                {"op": "run_policy", "steps": 1},
                {"op": "run_policy", "prompt": "place", "steps": 1},
                {"op": "run_policy", "prompt": "place", "steps": 1},
                {"op": "complete"},
            ],
            policy=policy,
        )

        result = runner.run(seed=1)

        self.assertEqual(result["prompt_submissions"], 3)
        self.assertEqual(result["prompt_changes"], 1)
        self.assertEqual(result["prompt_restarts"], 1)
        self.assertEqual(result["discarded_actions"], 3)
        self.assertEqual(result["intervals"], [1, 1, 1, 1])

    def test_run_resets_policy_episode_with_environment_seed(self):
        env = FakeEnvironment()
        policy = FakePolicy()
        runner = make_runner([{"op": "complete"}], env=env, policy=policy)

        runner.run(seed=314)

        self.assertEqual(env.reset_seeds, [314])
        self.assertEqual(policy.reset_episode_seeds, [314])


class RunnerOutcomeTests(unittest.TestCase):
    def test_success_requires_physical_success_and_complete(self):
        env = FakeEnvironment(success=lambda step: step >= 1)
        runner = make_runner(
            [{"op": "run_policy", "prompt": "pick", "steps": 1}, {"op": "complete"}],
            env=env,
        )

        result = runner.run(seed=1)

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["success"])
        self.assertTrue(result["physical_success_final"])
        self.assertTrue(result["physical_success_any"])
        self.assertFalse(result["false_completion"])

    def test_false_completion_ends_episode(self):
        runner = make_runner([{"op": "complete"}])

        result = runner.run(seed=1)

        self.assertEqual(result["status"], "false_completion")
        self.assertFalse(result["success"])
        self.assertTrue(result["false_completion"])
        self.assertEqual(result["steps"], 0)
        self.assertEqual(result["model_calls"], 1)

    def test_physical_success_reached_then_lost_tracks_final_and_any(self):
        env = FakeEnvironment(success=lambda step: step == 1)
        runner = make_runner(
            [{"op": "run_policy", "prompt": "pick", "steps": 2}, {"op": "complete"}],
            env=env,
        )

        result = runner.run(seed=1)

        self.assertEqual(result["status"], "false_completion")
        self.assertFalse(result["physical_success_final"])
        self.assertTrue(result["physical_success_any"])

    def test_reaching_physical_horizon_does_not_grant_success(self):
        env = FakeEnvironment(success=lambda step: step >= 2)
        runner = make_runner(
            [{"op": "run_policy", "prompt": "pick", "steps": 2}],
            env=env,
            limits=Limits(max_steps=2, max_decisions=3, max_interval=2),
        )

        result = runner.run(seed=1)

        self.assertEqual(result["status"], "step_budget_exhausted")
        self.assertFalse(result["success"])
        self.assertTrue(result["physical_success_final"])
        self.assertEqual(result["steps"], 2)
        self.assertEqual(result["model_calls"], 1)

    def test_decision_budget_stops_exactly_at_boundary(self):
        runner = make_runner(
            [{"op": "no-such-operation"}],
            limits=Limits(max_steps=2, max_decisions=1, max_interval=2),
        )

        result = runner.run(seed=1)

        self.assertEqual(result["status"], "decision_budget_exhausted")
        self.assertEqual(result["model_calls"], 1)
        self.assertEqual(len(runner.agent.observations), 1)


class InfrastructureFailureTests(unittest.TestCase):
    def test_non_boolean_evaluator_result_is_an_infrastructure_error(self):
        env = FakeEnvironment(success=lambda step: 1)
        runner = make_runner([{"op": "complete"}], env=env)

        result = runner.run(seed=5)

        self.assertEqual(result["status"], "infrastructure_error")
        self.assertFalse(result["success"])
        self.assertIn("ValueError: evaluator must return a boolean success", result["infrastructure_error"])
        self.assertEqual(result["model_calls"], 0)

    def test_transport_inference_and_simulator_failures_are_infrastructure_errors(self):
        cases = {
            "transport": {
                "replies": [ConnectionError("transport unavailable")],
                "policy": FakePolicy(),
                "env": FakeEnvironment(),
                "needle": "ConnectionError: transport unavailable",
            },
            "inference": {
                "replies": [{"op": "run_policy", "prompt": "pick", "steps": 1}],
                "policy": FakePolicy(predict_error=TimeoutError("inference timeout")),
                "env": FakeEnvironment(),
                "needle": "TimeoutError: inference timeout",
            },
            "simulator": {
                "replies": [{"op": "run_policy", "prompt": "pick", "steps": 1}],
                "policy": FakePolicy(chunks=[[action(1)]]),
                "env": FakeEnvironment(step_error=RuntimeError("simulator failed")),
                "needle": "RuntimeError: simulator failed",
            },
        }
        for name, case in cases.items():
            with self.subTest(failure=name):
                records = CaptureRecords()
                runner = make_runner(
                    case["replies"], env=case["env"], policy=case["policy"], records=records
                )

                result = runner.run(seed=5)

                self.assertEqual(result["status"], "infrastructure_error")
                self.assertFalse(result["success"])
                self.assertIn(case["needle"], result["infrastructure_error"])
                self.assertTrue(case["env"].closed)
                if name == "inference":
                    self.assertEqual(result["policy_calls"], 1)

    def test_failed_simulator_step_is_attempted_once_and_never_retried(self):
        env = FakeEnvironment(step_error=RuntimeError("uncertain simulator state"))
        records = CaptureRecords()
        runner = make_runner(
            [{"op": "run_policy", "prompt": "pick", "steps": 3}],
            env=env,
            policy=FakePolicy(chunks=[[action(1), action(2), action(3)]]),
            records=records,
        )

        result = runner.run(seed=9)

        self.assertEqual(result["status"], "infrastructure_error")
        self.assertEqual(len(env.step_attempts), 1)
        self.assertEqual(result["steps"], 0)
        attempts = [value for name, value in records.events if name == "action_attempts.jsonl"]
        completed = [value for name, value in records.events if name == "actions.jsonl"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(completed, [])


if __name__ == "__main__":
    unittest.main()
