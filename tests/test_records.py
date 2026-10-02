import json
import tempfile
import unittest
from pathlib import Path

from robot_benchmark.contracts import CAMERAS, PROPRIO
from robot_benchmark.records import Records

from tests.fakes import PNG_BYTES, SENTINEL, FakeEnvironment, FakePolicy, action, make_runner


class RecordsContractTests(unittest.TestCase):
    def test_episode_record_is_self_contained_and_keeps_evaluator_data_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            episode = Path(temporary) / "episode-0001"
            manifest = {"episode": 1, "source": "contract-test"}
            records = Records(episode, manifest)
            runner = make_runner(
                [{"op": "run_policy", "prompt": "pick", "steps": 1}, {"op": "complete"}],
                env=FakeEnvironment(success=lambda step: step >= 1),
                policy=FakePolicy(chunks=[[action(7)]]),
                records=records,
            )

            runner.agent.last_trace = {"request": {"body": {"model": "test"}},
                                       "response": {"body": {"content": [
                                           {"type": "thinking", "thinking": "visible summary"}]}}}
            result = runner.run(seed=23)

            traces = [json.loads(line) for line in (episode / "model_api_traces.jsonl").read_text().splitlines()]
            self.assertEqual(len(traces), 2)
            self.assertEqual(traces[0]["response"]["body"]["content"][0]["thinking"],
                             "visible summary")
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
            transition = json.loads((episode / "policy_transitions.jsonl").read_text().splitlines()[0])
            self.assertEqual(transition["instruction"], "pick")
            self.assertEqual(transition["discarded_actions"], 0)
            self.assertTrue((episode / "decisions.jsonl").is_file())
            self.assertTrue((episode / "model_replies.jsonl").is_file())
            step_timing = json.loads((episode / "step_timings.jsonl").read_text().splitlines()[0])
            self.assertEqual(step_timing["step"], 1)
            self.assertAlmostEqual(step_timing["sim_step_seconds"], 0.05)
            self.assertGreaterEqual(step_timing["physics_seconds"], 0)
            self.assertGreaterEqual(step_timing["wall_seconds"], step_timing["physics_seconds"])
            self.assertGreater(result["ended_at_unix_ns"], result["started_at_unix_ns"])
            self.assertAlmostEqual(result["simulated_seconds"], 0.05)
            self.assertEqual(len((episode / "model_timings.jsonl").read_text().splitlines()), 2)
            self.assertEqual(len((episode / "policy_timings.jsonl").read_text().splitlines()), 1)
            for camera in CAMERAS:
                frames = episode / "video_frames" / camera.removeprefix("video.")
                self.assertEqual(sorted(path.name for path in frames.glob("*.png")),
                                 ["000000.png", "000001.png"])
                self.assertTrue(all(path.read_bytes() == PNG_BYTES for path in frames.glob("*.png")))


    def test_interval_keyframes_are_archived_as_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            episode = Path(temporary) / "episode-0002"
            records = Records(episode, {"episode": 2})
            runner = make_runner(
                [{"op": "run_policy", "prompt": "pick", "steps": 4}, {"op": "complete"}],
                policy=FakePolicy(chunks=[[action()] * 4]),
                records=records,
                interval_keyframes=1,
            )
            runner.run(seed=5)

            text = (episode / "observations.jsonl").read_text()
            self.assertNotIn("base64", text)
            frames = json.loads(text.splitlines()[1])["interval_frames"]
            self.assertEqual([frame["step"] for frame in frames], [2])
            self.assertEqual(set(frames[0]["proprio"]), set(PROPRIO))
            for relative in frames[0]["images"].values():
                self.assertTrue(relative.startswith("frames/"))
                self.assertEqual((episode / relative).read_bytes(), PNG_BYTES)


if __name__ == "__main__":
    unittest.main()
