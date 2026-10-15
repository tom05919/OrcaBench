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
                status = main(["--agent-configs", str(config), "--output", str(output), "--api-dollar-cap", "100", *extra])
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


class SessionProbeTests(unittest.TestCase):
    def setup_files(self, folder, *, model="claude-opus-5-5"):
        root = Path(folder)
        config, pressure, output = root / "model.json", root / "time.json", root / "probe.json"
        config.write_text(json.dumps({**CONFIG, "model": model}))
        pressure.write_text(json.dumps({"call_seconds": {"claude-opus-5-5": 4.7, "claude-sonnet-5-5": 2.2},
                                       "tasks": {"CloseFridge": {"deadline_seconds": 45}}}))
        return config, pressure, output

    def test_dry_run_requires_no_key_and_has_exact_session_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            config, pressure, output = self.setup_files(folder)
            with patch.dict("os.environ", {}, clear=True), patch("builtins.print") as printing, \
                 patch("robot_benchmark.adapters.agents.request_json") as request:
                status = main(["--agent-configs", str(config), "--time-pressure", str(pressure), "--dry-run",
                               "--output", str(output)])
            request.assert_not_called()
            self.assertEqual(status, 0)
            report = json.loads(output.read_text())
            self.assertTrue(report["dry_run"])
            self.assertEqual(report["requests"][0]["prompt_version"], 6)
            body = report["requests"][0]["payload"]
            self.assertIn("4.7", body["system"])
            self.assertEqual(json.loads(body["messages"][0]["content"][-1]["text"])["policy"], "K")
            self.assertNotIn("iVBOR", json.dumps(report))
            self.assertNotIn("api_key_env", json.dumps(report))
            self.assertFalse((Path(folder) / "model_timings.jsonl").exists())

    def test_dry_run_projects_experience_and_rejects_bad_credential_field(self):
        from tests.test_agents_session import RECORD
        with tempfile.TemporaryDirectory() as folder:
            config, pressure, output = self.setup_files(folder)
            experience = Path(folder) / 'experience.json'
            experience.write_text(json.dumps([{**RECORD, 'backend': 'private-backend', 'reward': 98765}]))
            with patch.dict('os.environ', {}, clear=True), patch('builtins.print'):
                self.assertEqual(main(['--agent-configs', str(config), '--time-pressure', str(pressure),
                                       '--experience', str(experience), '--dry-run', '--output', str(output)]), 0)
            report = json.loads(output.read_text())
            self.assertEqual(json.loads(report['requests'][0]['payload']['messages'][0]['content'][0]['text']), RECORD)
            self.assertNotIn('private-backend', json.dumps(report))
            output.unlink()
            config.write_text(json.dumps({**CONFIG, 'api_key_env': ['invalid']}))
            with patch('builtins.print'), self.assertRaises(ValueError):
                main(['--agent-configs', str(config), '--dry-run', '--output', str(output)])

    def test_per_model_charges_are_projected_without_trigger_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            config, pressure, output = self.setup_files(folder, model="claude-sonnet-5-5")
            value = json.loads(pressure.read_text())
            value['tasks']['CloseFridge']['story'] = {'text': 'Cooling', 'clock_starts': 'private_trigger', 'limit_seconds': 8}
            pressure.write_text(json.dumps(value))
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "secret-test-key"}), patch("builtins.print"), \
                 patch("robot_benchmark.adapters.agents.request_json", return_value=OK) as request:
                status = main(["--agent-configs", str(config), "--time-pressure", str(pressure), "--output", str(output), "--api-dollar-cap", "100"])
            self.assertEqual(status, 0)
            self.assertIn("2.2", request.call_args.args[1]['system'])
            self.assertNotIn('private_trigger', json.dumps(request.call_args.args[1]))
            summary = json.loads(output.read_text())['summary'][0]
            self.assertEqual(summary['prompt_version'], 6)
            self.assertIsInstance(summary['median_seconds'], (int, float))
            timings = [json.loads(line) for line in (Path(folder) / 'model_timings.jsonl').read_text().splitlines()]
            self.assertEqual(len(timings), 2)
            self.assertTrue(all(row['prompt_version'] == 6 and row['effort'] == 'medium' for row in timings))

    def test_session_probe_refuses_unknown_model_bad_config_and_effort_without_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            config, pressure, output = self.setup_files(folder)
            with patch('robot_benchmark.adapters.agents.request_json') as request, patch('builtins.print'):
                for values in ({'call_seconds': {}}, {'call_seconds': {'claude-opus-5-5': float('nan')}}):
                    data = {'tasks': {'CloseFridge': {'deadline_seconds': 45}}, **values}
                    pressure.write_text(json.dumps(data))
                    with self.subTest(data=data), self.assertRaises(ValueError):
                        main(['--agent-configs', str(config), '--time-pressure', str(pressure), '--dry-run', '--output', str(output)])
                with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                    main(['--agent-configs', str(config), '--time-pressure', str(pressure), '--efforts', 'high', '--dry-run'])
                request.assert_not_called()

    def test_existing_output_and_timing_ledger_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            config, pressure, output = self.setup_files(folder)
            for prior in (output, Path(folder) / 'model_timings.jsonl'):
                prior.write_text('retained')
                with patch('robot_benchmark.adapters.agents.request_json') as request, self.assertRaises(FileExistsError):
                    main(['--agent-configs', str(config), '--output', str(output), '--api-dollar-cap', '100'])
                request.assert_not_called()
                self.assertEqual(prior.read_text(), 'retained')
                prior.unlink()

    def test_interrupt_preserves_completed_call_and_attempted_call(self):
        with tempfile.TemporaryDirectory() as folder:
            config, pressure, output = self.setup_files(folder)
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'secret-test-key'}), patch('builtins.print'), \
                 patch('robot_benchmark.adapters.agents.request_json', side_effect=[OK, KeyboardInterrupt]):
                with self.assertRaises(KeyboardInterrupt):
                    main(['--agent-configs', str(config), '--output', str(output), '--api-dollar-cap', '100'])
            timings = [json.loads(line) for line in (Path(folder) / 'model_timings.jsonl').read_text().splitlines()]
            self.assertEqual(len(timings), 2)
            self.assertTrue(timings[0]['ok'])
            self.assertFalse(timings[1]['ok'])
            self.assertIn('KeyboardInterrupt', timings[1]['error'])
            report = json.loads(output.read_text())
            self.assertEqual(len(report['calls']), 2)

    def test_calibration_median_uses_successful_calls_only_and_reports_version(self):
        from scripts.probe_model import summarize
        rows = [{'model': 'model', 'effort': 'medium', 'prompt_version': 6, 'ok': ok,
                 'usage': {}, 'seconds': seconds, 'retries': [], 'parse': 'strict'}
                for ok, seconds in ((True, 1), (True, 3), (False, 100))]
        summary = summarize(rows)[0]
        self.assertEqual(summary['median_seconds'], 2)
        self.assertEqual(summary['prompt_version'], 6)

    def test_json_http_probe_and_dry_run_do_not_require_anthropic_output_config(self):
        with tempfile.TemporaryDirectory() as folder:
            config, pressure, output = self.setup_files(folder)
            config.write_text(json.dumps({**CONFIG, 'provider': 'json_http'}))
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'secret-test-key'}), patch('builtins.print'), \
                 patch('robot_benchmark.adapters.agents.request_json', return_value=({'decision': {'op': 'complete'}, 'usage': {}}, {})):
                self.assertEqual(main(['--agent-configs', str(config), '--output', str(output), '--dry-run']), 0)


class ProbeSpendCapTests(unittest.TestCase):
    def test_live_probe_requires_cap_before_any_network_request(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'model.json'; config.write_text(json.dumps(CONFIG))
            with patch('robot_benchmark.adapters.agents.request_json') as request, \
                 self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                main(['--agent-configs', str(config)])
            request.assert_not_called()

    def test_cap_exhaustion_stops_probe_and_preserves_budget_error(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'model.json'; config.write_text(json.dumps(CONFIG))
            output = Path(folder) / 'probe.json'
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'secret-test-key'}), patch('builtins.print'), \
                 patch('robot_benchmark.adapters.agents.request_json') as request:
                status = main(['--agent-configs', str(config), '--output', str(output), '--api-dollar-cap', '.01'])
            self.assertEqual(status, 1)
            request.assert_not_called()
            report = json.loads(output.read_text())
            self.assertEqual(len(report['calls']), 1)
            self.assertIn('BudgetLimitError', report['calls'][0]['error'])
            self.assertGreater(report['calls'][0]['minimum_required_reservation'], 5)

    def test_dry_run_discloses_full_context_headroom_without_credentials_or_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'model.json'; config.write_text(json.dumps(CONFIG))
            output = Path(folder) / 'dry.json'
            with patch.dict('os.environ', {}, clear=True), patch('builtins.print'), \
                 patch('robot_benchmark.adapters.agents.request_json') as request:
                main(['--agent-configs', str(config), '--output', str(output), '--dry-run'])
            request.assert_not_called()
            row = json.loads(output.read_text())['requests'][0]
            self.assertAlmostEqual(row['minimum_required_reservation'], 5.08192)

    def test_multiple_models_share_total_probe_dollars(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); config = root / 'opus.json'; sonnet = root / 'sonnet.json'
            config.write_text(json.dumps(CONFIG)); sonnet.write_text(json.dumps({**CONFIG, 'model': 'claude-sonnet-5-5'}))
            output = root / 'probe.json'
            # One unknown billed Opus failure consumes $5.08192. A second Opus
            # attempt is unaffordable, so no other configured model can be sent.
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'secret-test-key'}), patch('builtins.print'), \
                 patch('robot_benchmark.adapters.agents.request_json', side_effect=HTTPStatusError(400, 'bad')) as request:
                self.assertEqual(main(['--agent-configs', str(config), str(sonnet), '--output', str(output), '--api-dollar-cap', '6']), 1)
            self.assertEqual(request.call_count, 1)
            rows = [json.loads(line) for line in (root / 'api_spend.jsonl').read_text().splitlines()]
            self.assertTrue(all(row['budget_dollars'] == 6 for row in rows))


if __name__ == "__main__":
    unittest.main()
