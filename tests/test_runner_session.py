import unittest
from tests.fakes import CaptureRecords, FakeEnvironment, FakePolicy, make_runner


class InterruptedEpisodeTests(unittest.TestCase):
    def test_interruption_retains_partial_result_and_closes_environment(self):
        records, env = CaptureRecords(), FakeEnvironment()
        runner = make_runner([{"op": "run_policy", "prompt": "Do the task.", "steps": 3}, KeyboardInterrupt()],
                             records=records, env=env, policy=FakePolicy())
        with self.assertRaises(KeyboardInterrupt):
            runner.run(1, 2)
        result = records.writes["result.json"]
        self.assertEqual(result["status"], "infrastructure_error")
        self.assertEqual(result["steps"], 3)
        self.assertEqual(result["model_calls"], 2)
        self.assertTrue(result["interrupted"])
        self.assertTrue(env.closed)


if __name__ == "__main__":
    unittest.main()
