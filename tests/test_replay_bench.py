import json
import tempfile
import unittest
from pathlib import Path

from robot_benchmark.replay_bench import (Ledger, SpendCapReached, frame_index, parse_decision, parse_probe,
                                          run_episode, run_session, sample_probes)

CONFIG = {"call_seconds": {}, "tasks": {
    "Plain": {"deadline_seconds": 50.0},
    "Story": {"deadline_seconds": 50.0, "story": {"text": "It cools.", "clock_starts": "off", "limit_seconds": 10}},
}}


def traj(first=305, steps=999, task="Plain", ident="pod/groot/Plain/1000", extra_true=None):
    success = [False] * (steps + 1) if first is None else [False] * first + [True] * (steps + 1 - first)
    return {"id": ident, "pod": "pod", "folder": "", "task": task, "backend": "groot", "scene": 1000, "goal": "Do it.",
            "steps": steps, "success_by_step": success, "first_success": first,
            "first_true": {**({"success": first} if first is not None else {}), **(extra_true or {})},
            "logged": {"off"} if task == "Story" else set()}


class Frames:
    def __init__(self):
        self.asked = []

    def png(self, t, step):
        self.asked.append(step)
        return b"png"


class Client:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def call(self, model, system, content, tag=""):
        self.calls.append(content)
        return {"text": self.replies.pop(0), "usage": {"input_tokens": 10, "output_tokens": 5}, "seconds": 1.0,
                "dollars": 0.001}


class ReplayBenchTests(unittest.TestCase):
    def test_frame_index_matches_the_recording_rule(self):
        self.assertEqual([frame_index(s, 899) for s in (0, 10, 890, 899)], [0, 1, 89, 90])
        self.assertEqual(frame_index(900, 900), 90)
        with self.assertRaises(ValueError):
            frame_index(15, 899)

    def test_probe_labels_skip_the_ambiguity_band_and_follow_the_checker(self):
        probes = {p["step"]: p["label"] for p in sample_probes([traj(first=305)])}
        self.assertEqual(probes, {310: True, 410: True, 260: False, 100: False})  # 305 - 40 = 265, snapped to 260
        failed = {p["step"]: p["label"] for p in sample_probes([traj(first=None, ident="pod/x")])}
        self.assertEqual(failed, {490: False, 999: False})

    def test_reply_parsing(self):
        self.assertEqual(parse_decision('thinking... {"op": "wait", "steps": 123}'), ("wait", 130))
        self.assertEqual(parse_decision('{"op":"wait","steps":5000}'), ("wait", 400))
        self.assertEqual(parse_decision('{"op": "done"}'), ("done", None))
        self.assertIsNone(parse_decision("no idea")[0])
        self.assertIs(parse_probe('{"done": true}'), True)
        self.assertIsNone(parse_probe('{"done": "yes"}'))

    def test_episode_declares_and_is_scored_with_the_look_cost(self):
        frames, client = Frames(), Client(['{"op":"wait","steps":200}', '{"op":"wait","steps":150}', '{"op":"done"}'])
        record = run_episode(client, "m", frames, traj(first=305), "K", [], CONFIG, 2.0)
        self.assertEqual((record["outcome"], record["final_step"], record["looks"], record["first_wait"]),
                         ("success", 350, 3, 200))
        self.assertAlmostEqual(record["value"], 1 - (350 / 20 + 3 * 2.0) / 50)
        self.assertTrue(all(s % 10 == 0 for s in frames.asked))
        self.assertEqual(frames.asked, [0, 200, 100, 0, 350, 270, 200])  # now, mid-interval, previous look

    def test_early_done_fails_and_budget_end_gives_one_final_look(self):
        early = run_episode(Client(['{"op":"done"}']), "m", Frames(), traj(first=305), "K", [], CONFIG, 2.0)
        self.assertEqual((early["outcome"], early["value"]), ("false_done", 0.0))
        late = run_episode(Client(['{"op":"wait","steps":400}'] * 3 + ['{"op":"wait","steps":10}']), "m", Frames(),
                           traj(first=None, steps=999), "K", [], CONFIG, 2.0)
        self.assertEqual((late["outcome"], late["final_step"], late["looks"]), ("timeout", 999, 4))

    def test_story_limit_counts_robot_time_and_looks_after_the_trigger(self):
        t = traj(first=300, task="Story", extra_true={"off": 200})
        ok = run_episode(Client(['{"op":"wait","steps":300}', '{"op":"done"}']), "m", Frames(), t, "K", [], CONFIG, 2.0)
        self.assertEqual((ok["outcome"], ok["scored_success"], ok["story"]["seconds"]), ("success", True, 7.0))
        late = run_episode(Client(['{"op":"wait","steps":300}', '{"op":"wait","steps":200}', '{"op":"done"}']), "m",
                           Frames(), t, "K", [], CONFIG, 2.0)  # 15 s of robot time after the trigger > 10 s
        self.assertEqual((late["outcome"], late["scored_success"], late["value"]), ("success", False, 0.0))

    def test_three_invalid_replies_end_the_episode(self):
        record = run_episode(Client(["?", "??", "???"]), "m", Frames(), traj(), "K", [], CONFIG, 2.0)
        self.assertEqual((record["outcome"], record["looks"], record["value"]), ("invalid", 3, 0.0))

    def test_ledger_stops_before_the_cap(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = Ledger(Path(d) / "spend.jsonl", cap=0.01)
            worst = ledger.reserve("zai-org/GLM-5.3-Flash", 1000, 1000)
            ledger.settle("zai-org/GLM-5.3-Flash", worst, {"input_tokens": 1000, "output_tokens": 100}, "t")
            self.assertAlmostEqual(ledger.spent, (1000 * 0.11 + 100 * 0.35) / 1e6)
            with self.assertRaises(SpendCapReached):
                ledger.reserve("moonshotai/Kimi-K3", 1000, 1000)
            self.assertAlmostEqual(Ledger(Path(d) / "spend.jsonl", cap=1).spent, ledger.spent)  # reloads the file

    def test_session_resumes_with_the_same_experience(self):
        trajs = {("groot", "Plain", 1000): traj(first=305), ("pi05", "Plain", 1000): traj(first=None, ident="b")}
        plan = [{"task": "Plain", "scene_seed": 1000, "policy_label": "K", "backend": "groot"},
                {"task": "Plain", "scene_seed": 1000, "policy_label": "R", "backend": "pi05"}]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "s.jsonl"
            run_session(Client(['{"op":"wait","steps":400}', '{"op":"done"}']), "m", Frames(), plan[:1], trajs,
                        CONFIG, 2.0, out)
            client = Client(['{"op":"done"}'])
            run_session(client, "m", Frames(), plan, trajs, CONFIG, 2.0, out)
            records = [json.loads(l) for l in out.read_text().splitlines()]
            self.assertEqual([r["outcome"] for r in records], ["success", "false_done"])
            self.assertIn("Episode 1: policy K", client.calls[0][0]["text"])
            self.assertIn("success: declared done at 20.0 s after 2 looks", client.calls[0][0]["text"])


if __name__ == "__main__":
    unittest.main()


class ReplayBaselineTests(unittest.TestCase):
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "replay_analyze", Path(__file__).resolve().parents[1] / "scripts" / "replay_analyze.py")
        self.a = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.a)

    def test_detector_timer_and_oracle_pay_the_same_look_cost_as_a_model(self):
        t = traj(first=305)
        # Looks at 0, 100, 200, 300, 400: true first at 400, five looks.
        self.assertAlmostEqual(self.a.detector_value(t, 100, CONFIG, 2.0), 1 - (400 / 20 + 5 * 2.0) / 50)
        self.assertAlmostEqual(self.a.timer_value(t, 320, CONFIG, 2.0), 1 - (320 / 20 + 2 * 2.0) / 50)
        self.assertEqual(self.a.timer_value(t, 300, CONFIG, 2.0), 0.0)  # declared before success
        self.assertAlmostEqual(self.a.oracle_value(t, CONFIG, 2.0), 1 - (310 / 20 + 2 * 2.0) / 50)
        self.assertEqual(self.a.detector_value(traj(first=None), 100, CONFIG, 2.0), 0.0)

    def test_held_out_rule_is_tuned_on_other_scenes_of_the_same_policy_and_task(self):
        target = traj(first=305, ident="a")
        other = {**traj(first=95, ident="b"), "scene": 1001}
        same_scene = {**traj(first=900, ident="c")}  # same scene as the target: must be ignored
        value = self.a.held_out([target, other, same_scene], target, self.a.timer_value,
                                lambda x: range(10, x["steps"] + 1, 10), CONFIG, 2.0)
        self.assertEqual(value, 0.0)  # tuned to declare at 100 (the other scene), too early for the target
