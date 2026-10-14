import json
import tempfile
import unittest
from pathlib import Path

from robot_benchmark.time_score import (best_fixed_rules, load_config, read_episode, score_episode, success_at,
                                        supervisor_measures, value)

LLM_AGENT = {"provider": "anthropic", "model": "claude-opus-5-5"}
SCRIPTED = {"kind": "diagnostic", "model": "ordinary_full_task_policy"}
CONFIG = {"call_seconds": 5.0, "tasks": {
    "Plain": {"deadline_seconds": 100.0},
    "Iced": {"deadline_seconds": 100.0, "story": {"text": "Ice melts.", "clock_starts": "ice_out", "limit_seconds": 10.0}},
}}


def episode(root, name, task="Plain", kind="llm_development", agent=LLM_AGENT, steps=400, success=True,
            truth=None, extra=None, decisions=(), model_calls=0, false_completion=False, **result):
    """An episode folder; `truth` is the per-step checker state, `extra` maps predicate names to per-step lists."""
    folder = Path(root) / name
    (folder / "evaluator").mkdir(parents=True)
    truth = truth if truth is not None else [False] * steps + [success]
    (folder / "result.json").write_text(json.dumps({
        "scene_seed": 1000, "policy_seed": 0, "steps": steps, "success": success, "false_completion": false_completion,
        "model_calls": model_calls, "infrastructure_error": None, "intervals": [100] * (steps // 100), **result}))
    (folder / "manifest.json").write_text(json.dumps({"task": task, "kind": kind, "agent": agent,
                                                      "policy": {"backend": "groot"}}))
    (folder / "decisions.jsonl").write_text("".join(json.dumps(d) + "\n" for d in decisions))
    rows = []
    for step, ok in enumerate(truth):
        row = {"step": step, "success": ok}
        row.update({key: values[step] for key, values in (extra or {}).items()})
        rows.append(json.dumps(row) + "\n")
    (folder / "evaluator" / "events.jsonl").write_text("".join(rows))
    return read_episode(folder)


def run(step, steps, prompt=None):
    decision = {"op": "run_policy", "steps": steps, **({"prompt": prompt} if prompt else {})}
    return {"step_before": step, "decision": decision, "accepted": True, "step_after": step + steps}


COMPLETE = lambda step: {"step_before": step, "decision": {"op": "complete"}, "accepted": True, "step_after": step}


class TimeScoreTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def test_value_is_zero_for_any_failure_and_falls_linearly_with_charged_time(self):
        self.assertEqual(value(True, 0.0, 100.0), 1.0)
        self.assertAlmostEqual(value(True, 25.0, 100.0), 0.75)
        self.assertEqual(value(True, 150.0, 100.0), 0.0)
        self.assertEqual(value(False, 1.0, 100.0), 0.0)

    def test_only_llm_responses_are_charged(self):
        llm = episode(self.root, "llm", model_calls=3, decisions=[run(0, 200, "go"), run(200, 200), COMPLETE(400)])
        scripted = episode(self.root, "ref", kind="diagnostic_reference", agent=SCRIPTED, model_calls=6)
        self.assertEqual(score_episode(llm, CONFIG)["charged_seconds"], 20.0 + 15.0)
        self.assertAlmostEqual(score_episode(llm, CONFIG)["value"], 0.65)
        self.assertEqual(score_episode(scripted, CONFIG)["charged_seconds"], 20.0)

    def test_story_limit_counts_from_the_trigger_and_includes_later_calls(self):
        ice = [False] * 100 + [True] * 301  # the ice leaves the bowl at step 100; episode ends at step 400
        late = episode(self.root, "late", task="Iced", model_calls=3, extra={"ice_out": ice},
                       decisions=[run(0, 200, "go"), run(200, 200), COMPLETE(400)])
        scored = score_episode(late, CONFIG)  # 300 steps = 15 s plus two calls after step 100 = 25 s > 10 s
        self.assertEqual((scored["story"]["status"], scored["success"], scored["value"]), ("expired", False, 0.0))
        quick = episode(self.root, "quick", task="Iced", steps=120, extra={"ice_out": [False] * 100 + [True] * 21},
                        truth=[False] * 120 + [True], model_calls=1, decisions=[run(0, 120, "go"), COMPLETE(120)])
        self.assertEqual(score_episode(quick, CONFIG)["story"]["status"], "ok")  # 1 s + one 5 s call

    def test_story_is_not_applied_when_the_trigger_was_not_logged(self):
        old = episode(self.root, "old", task="Iced", model_calls=1, decisions=[run(0, 400, "go"), COMPLETE(400)])
        scored = score_episode(old, CONFIG)
        self.assertEqual(scored["story"], {"status": "trigger not logged"})
        self.assertTrue(scored["success"])

    def test_success_persists_after_a_reference_run_stops_at_success(self):
        stopped = episode(self.root, "stop", kind="diagnostic_reference", agent=SCRIPTED, steps=200,
                          truth=[False] * 150 + [True] * 51)
        self.assertFalse(success_at(stopped, 149))
        self.assertTrue(success_at(stopped, 150))
        self.assertTrue(success_at(stopped, 900))

    def test_best_fixed_rule_skips_invalid_runs(self):
        for i, first in enumerate((200, 300)):
            episode(self.root, f"ref{i}", kind="diagnostic_reference", agent=SCRIPTED, steps=first,
                    truth=[False] * first + [True])
        episode(self.root, "defer", kind="baseline_always_defer", agent={"kind": "baseline", "model": "always_defer_v1"},
                steps=1000, success=False, truth=[False] * 1001)
        episode(self.root, "solved_at_start", kind="diagnostic_reference", agent=SCRIPTED, steps=0, truth=[True])
        runs = [read_episode(p) for p in sorted(Path(self.root).iterdir())]
        rules = best_fixed_rules(runs, CONFIG, {"Plain": 1000})
        rule = rules[("groot", "Plain", "no_restart")]  # the reference runs alone; solved-at-start skipped
        self.assertEqual((rule["n"], rule["step"]), (2, 300))  # declaring at 300 catches both successes
        self.assertAlmostEqual(rule["value"], 1 - 15 / 100)
        self.assertAlmostEqual(rule["oracle"], ((1 - 10 / 100) + (1 - 15 / 100)) / 2)
        self.assertAlmostEqual(rule["loo_value"], ((1 - 15 / 100) + 0.0) / 2)  # step 200 from one run misses the other
        defer_only = best_fixed_rules([e for e in runs if e["kind"] == "baseline_always_defer"], CONFIG, {"Plain": 1000})
        self.assertEqual(defer_only[("groot", "Plain", "no_restart")]["n"], 1)  # always-defer pools when alone

    def test_unselected_reference_runs_alone_estimate_the_rule_when_present(self):
        episode(self.root, "ref", kind="diagnostic_reference", agent=SCRIPTED, steps=1000, success=False,
                truth=[False] * 1001)
        episode(self.root, "defer", kind="baseline_always_defer", agent={"kind": "baseline", "model": "always_defer_v1"},
                steps=1000, truth=[False] * 200 + [True] * 801)  # run only where the plain policy succeeded
        rules = best_fixed_rules([read_episode(p) for p in sorted(Path(self.root).iterdir())], CONFIG, {"Plain": 1000})
        rule = rules[("groot", "Plain", "no_restart")]
        self.assertEqual((rule["n"], rule["value"], rule["step"]), (1, 0.0, None))

    def test_declaration_labels(self):
        correct = episode(self.root, "ok", steps=300, truth=[False] * 250 + [True] * 51, model_calls=2,
                          decisions=[run(0, 300, "go"), COMPLETE(300)])
        early = episode(self.root, "early", steps=200, success=False, false_completion=True, model_calls=2,
                        decisions=[run(0, 200, "go"), COMPLETE(200)])
        lost = episode(self.root, "lost", steps=300, success=False, false_completion=True, model_calls=2,
                       truth=[False] * 100 + [True] * 100 + [False] * 101, decisions=[run(0, 300, "go"), COMPLETE(300)])
        timeout = episode(self.root, "timeout", steps=400, success=False, truth=[False] * 300 + [True] * 101,
                          decisions=[run(0, 400, "go")])
        self.assertEqual((supervisor_measures(correct)["declaration"], supervisor_measures(correct)["lag_seconds"]),
                         ("correct", 2.5))
        self.assertEqual(supervisor_measures(early)["declaration"], "false: not reached yet")
        self.assertEqual(supervisor_measures(lost)["declaration"], "false: reached, then lost")
        self.assertEqual(supervisor_measures(timeout)["declaration"], "timeout, success was reached")

    def test_config_validation_and_shipped_config(self):
        with self.assertRaises(ValueError):
            path = Path(self.root) / "bad.json"
            path.write_text(json.dumps({"call_seconds": 5, "tasks": {"T": {"deadline_seconds": 0}}}))
            load_config(path)
        shipped = load_config(Path(__file__).resolve().parents[1] / "configs" / "time_pressure.json")
        tasks = {p.stem for p in (Path(__file__).resolve().parents[1] / "configs" / "tasks").glob("*.json")}
        self.assertEqual(set(shipped["tasks"]), tasks)


if __name__ == "__main__":
    unittest.main()
