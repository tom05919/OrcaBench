import json
import tempfile
import unittest
from pathlib import Path

from robot_benchmark.records import Records

from tests.fakes import PNG_BYTES, SENTINEL, FakeEnvironment, FakePolicy, action, make_runner


class RecordsContractTests(unittest.TestCase):
    def test_episode_record_is_self_contained_and_keeps_evaluator_data_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            episode = Path(temporary) / "episode-0001"
            manifest = {"episode": 1, "source": "contract-test"}
            records = Records(episode, manifest)
            runner = make_runner(
                [{"op": "start", "skill": "pick", "steps": 1}, {"op": "complete"}],
                env=FakeEnvironment(success=lambda step: step >= 1),
                policy=FakePolicy(chunks=[[action(7)]]),
                records=records,
            )

            result = runner.run(seed=23)

            self.assertEqual(json.loads((episode / "manifest.json").read_text()), manifest)
            self.assertEqual(json.loads((episode / "result.json").read_text()), result)
            observations = [
                json.loads(line) for line in (episode / "observations.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len(observations), 2)
            for observation in observations:
                self.assertNotIn(SENTINEL, repr(observation))
                for relative in observation["images"].values():
                    frame = episode / relative
                    self.assertTrue(frame.is_file(), relative)
                    self.assertEqual(frame.read_bytes(), PNG_BYTES)
                    self.assertTrue(str(relative).startswith("frames/"))

            evaluator_events = (episode / "evaluator" / "events.jsonl").read_text()
            self.assertIn(SENTINEL, evaluator_events)
            self.assertNotIn(SENTINEL, (episode / "observations.jsonl").read_text())
            self.assertTrue((episode / "actions.jsonl").is_file())
            self.assertTrue((episode / "policy_requests.jsonl").is_file())
            self.assertTrue((episode / "policy_calls.jsonl").is_file())
            self.assertTrue((episode / "decisions.jsonl").is_file())
            self.assertTrue((episode / "model_replies.jsonl").is_file())
            self.assertEqual(
                sorted(path.name for path in (episode / "video_frames").glob("*.png")),
                ["000000.png"],
            )


if __name__ == "__main__":
    unittest.main()
