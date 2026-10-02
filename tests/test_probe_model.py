from contextlib import redirect_stderr
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from robot_benchmark.adapters.http import HTTPStatusError
from robot_benchmark.contracts import CAMERAS, sensor_payload
from robot_benchmark.records import Records

from scripts.probe_model import main, replayed_observations, synthetic_observations

OK = ({"stop_reason": "end_turn", "usage": {"input_tokens": 900, "output_tokens": 120},
       "content": [{"type": "thinking", "thinking": "The fridge door is open.", "signature": "s"},
                   {"type": "text", "text": '{"op":"run_policy","prompt":"Close the fridge door.","steps":100}'}]},
      {"status": 200, "headers": {}})
CONFIG = {"provider": "anthropic", "model": "claude-opus-5-5",
          "endpoint": "https://api.anthropic.com/v1/messages", "api_key_env": "ANTHROPIC_API_KEY"}


class ProbeModelTests(unittest.TestCase):
    def run_probe(self, side_effect, *extra):
        with tempfile.TemporaryDirectory() as folder:
            config, output = Path(folder) / "model.json", Path(folder) / "probe.json"
            config.write_text(json.dumps(CONFIG))
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "secret-test-key"}), \
                 patch("robot_benchmark.adapters.agents.request_json", side_effect=side_effect) as request, \
                 patch("robot_benchmark.adapters.agents.sleep"), patch("builtins.print"):
                status = main(["--agent-configs", str(config), "--output", str(output), *extra])
            return status, json.loads(output.read_text()), request

    def test_synthetic_observations_match_the_public_sensor_schema(self):
        (_, first), (_, mid) = synthetic_observations()
        for observation in (first, mid):
            sensor_payload(observation)  # raises on a malformed image or proprioception
        self.assertEqual(len(mid["interval_frames"]), 4)
        self.assertIsNone(first["active_instruction"])

    def test_each_effort_is_sent_with_the_decision_schema_and_reported(self):
        status, report, request = self.run_probe([OK] * 4, "--efforts", "medium", "high")
        self.assertEqual(status, 0)
        self.assertEqual([call.args[1]["output_config"]["effort"] for call in request.call_args_list],
                         ["medium", "medium", "high", "high"])
        self.assertTrue(all("format" in call.args[1]["output_config"] for call in request.call_args_list))
        mid_images = [b for b in request.call_args_list[1].args[1]["messages"][0]["content"] if b["type"] == "image"]
        self.assertEqual(len(mid_images), 15)  # three cameras plus four keyframes each
        self.assertEqual([row["effort"] for row in report["summary"]], ["medium", "high"])
        self.assertEqual(report["summary"][0]["parse"], {"strict": 2, "extracted": 0, "unparsed": 0})
        self.assertTrue(all(row["valid"] for row in report["calls"]))
        stored = json.dumps(report)
        self.assertNotIn("iVBOR", stored)  # PNG bytes are not stored again
        self.assertNotIn("secret-test-key", stored)

    def test_rejected_request_fails_the_probe_without_retrying(self):
        status, report, request = self.run_probe([HTTPStatusError(400, "output_config.format not supported")] * 2)
        self.assertEqual(status, 1)
        self.assertEqual(request.call_count, 2)
        self.assertIn("HTTP 400", report["calls"][0]["error"])

    def test_recovered_or_invalid_reply_is_flagged(self):
        narrated = ({**OK[0], "content": [{"type": "text", "text": 'Running.\n{"op":"run_policy","steps":100}'}]}, OK[1])
        status, report, _ = self.run_probe([narrated, OK])
        self.assertEqual(status, 2)
        first = report["calls"][0]
        self.assertEqual(first["parse"], "extracted")
        self.assertFalse(first["valid"])  # no instruction is active yet, so a prompt is required
        self.assertIn("requires a prompt", first["validation_error"])

    def test_oversized_probe_is_refused_before_any_call(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            self.run_probe([OK], "--efforts", "low", "medium", "high", "--repeats", "20")

    def test_replay_restores_the_exact_recorded_observation(self):
        (_, original), (_, mid) = synthetic_observations()
        with tempfile.TemporaryDirectory() as folder:
            records = Records(Path(folder) / "episode", {"episode": 1})
            records.observation(0, original)
            records.observation(1, mid)
            replayed = replayed_observations(Path(folder) / "episode", [1])
        self.assertEqual(replayed[0][1], mid)
        self.assertEqual(set(replayed[0][1]["images"]), set(CAMERAS))


if __name__ == "__main__":
    unittest.main()
