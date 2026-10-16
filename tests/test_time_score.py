import json
import tempfile
import unittest
from pathlib import Path

from robot_benchmark.time_score import (best_fixed_rules, load_config, pooled_rules, read_episode, read_session,
                                        score_episode, session_summary, success_at, supervisor_measures, value)

LLM_AGENT = {"provider": "anthropic", "model": "claude-opus-5-5"}
SCRIPTED = {"kind": "diagnostic", "model": "ordinary_full_task_policy"}
CONFIG = {"call_seconds": {"claude-opus-5-5": 5.0}, "tasks": {
    "Plain": {"deadline_seconds": 100.0},
    "Iced": {"deadline_seconds": 100.0, "story": {"text": "Ice melts.", "clock_starts": "ice_out", "limit_seconds": 10.0}},
}}


def episode(root, name, task="Plain", kind="llm_development", agent=LLM_AGENT, steps=400, success=True,
            truth=None, extra=None, decisions=(), model_calls=0, false_completion=False, backend="groot", **result):
    """An episode folder; `truth` is the per-step checker state, `extra` maps predicate names to per-step lists."""
    folder = Path(root) / name
    (folder / "evaluator").mkdir(parents=True)
    truth = truth if truth is not None else [False] * steps + [success]
    (folder / "result.json").write_text(json.dumps({
        "scene_seed": 1000, "policy_seed": 0, "steps": steps, "success": success, "false_completion": false_completion,
        "model_calls": model_calls, "infrastructure_error": None, "intervals": [100] * (steps // 100), **result}))
    (folder / "manifest.json").write_text(json.dumps({"task": task, "kind": kind, "agent": agent,
                                                      "policy": {"backend": backend}}))
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

    def test_each_model_pays_its_own_calibrated_latency_and_unlisted_models_fail(self):
        config = {**CONFIG, "call_seconds": {"claude-opus-5-5": 4.0, "claude-sonnet-5-5": 2.0}}
        sonnet = episode(self.root, "sonnet", agent={"provider": "anthropic", "model": "claude-sonnet-5-5"},
                         model_calls=3, decisions=[run(0, 400, "go"), COMPLETE(400)])
        self.assertEqual(score_episode(sonnet, config)["charged_seconds"], 20.0 + 6.0)
        other = episode(self.root, "other", agent={"provider": "anthropic", "model": "claude-other"}, model_calls=1)
        with self.assertRaises(ValueError):
            score_episode(other, config)

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

    def test_fixed_rules_apply_the_story_limit_like_the_model_score(self):
        from robot_benchmark.time_score import fixed_rule_values, oracle_value, rule_value
        ice = {"ice_out": [False] * 100 + [True] * 301}  # trigger at step 100; limit 10 s = 200 steps, so step 300
        ref = episode(self.root, "ref", task="Iced", kind="diagnostic_reference", agent=SCRIPTED,
                      truth=[False] * 250 + [True] * 151, extra=ice)
        self.assertAlmostEqual(rule_value([ref], CONFIG, "Iced", 300), 1 - 15 / 100)  # 10 s after the trigger: in time
        self.assertEqual(rule_value([ref], CONFIG, "Iced", 320), 0.0)  # 11 s after the trigger: the story expired
        table = fixed_rule_values([ref], CONFIG, "Iced", 400)
        self.assertAlmostEqual(table[260], 1 - 13 / 100)
        self.assertEqual(table[320], 0.0)
        self.assertAlmostEqual(oracle_value([ref], CONFIG, "Iced"), 1 - 12.5 / 100)
        late = episode(self.root, "late", task="Iced", kind="diagnostic_reference", agent=SCRIPTED,
                       truth=[False] * 350 + [True] * 51, extra=ice)  # first success 12.5 s after the trigger
        self.assertEqual(oracle_value([late], CONFIG, "Iced"), 0.0)
        old = episode(self.root, "old", task="Iced", kind="diagnostic_reference", agent=SCRIPTED,
                      truth=[False] * 250 + [True] * 151)  # trigger not logged: no story, as in score_episode
        self.assertAlmostEqual(rule_value([old], CONFIG, "Iced", 320), 1 - 16 / 100)

    def test_fixed_rule_story_cases_from_w3_issue_10(self):
        from robot_benchmark.time_score import rule_value
        warm = {**CONFIG, "tasks": {**CONFIG["tasks"], "Warm": {"deadline_seconds": 100.0, "story": {
            "text": "It cools.", "clock_starts": "step0", "limit_seconds": 10.0}}}}
        ref = lambda name, task, truth, extra=None: episode(self.root, name, task=task, kind="diagnostic_reference",
                                                            agent=SCRIPTED, truth=truth, extra=extra)
        step0 = ref("step0", "Warm", [False] * 150 + [True] * 251)  # the clock starts at step 0
        self.assertAlmostEqual(rule_value([step0], warm, "Warm", 200), 1 - 10 / 100)  # exactly 10 s: valid
        self.assertEqual(rule_value([step0], warm, "Warm", 220), 0.0)  # 11 s: expired
        later = ref("later", "Iced", [False] * 150 + [True] * 251, {"ice_out": [False] * 300 + [True] * 101})
        self.assertAlmostEqual(rule_value([later], CONFIG, "Iced", 200), 1 - 10 / 100)  # trigger after T: clock not started
        never = ref("never", "Iced", [False] * 150 + [True] * 251, {"ice_out": [False] * 401})
        self.assertAlmostEqual(rule_value([never], CONFIG, "Iced", 380), 1 - 19 / 100)  # trigger logged, never true

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
            path.write_text(json.dumps({"call_seconds": {"m": 5}, "tasks": {"T": {"deadline_seconds": 0}}}))
            load_config(path)
        with self.assertRaises(ValueError):  # a single number is no longer accepted: every model is calibrated
            path.write_text(json.dumps({"call_seconds": 5, "tasks": {"T": {"deadline_seconds": 10}}}))
            load_config(path)
        shipped = load_config(Path(__file__).resolve().parents[1] / "configs" / "time_pressure.json")
        tasks = {p.stem for p in (Path(__file__).resolve().parents[1] / "configs" / "tasks").glob("*.json")}
        self.assertEqual(set(shipped["tasks"]), tasks)


class PooledAndSessionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        for backend, first in (("fast", 100), ("slow", 400)):
            for i in range(2):
                episode(self.root / "runs", f"{backend}{i}", kind="diagnostic_reference", agent=SCRIPTED,
                        backend=backend, steps=first, truth=[False] * first + [True])
        self.runs = [read_episode(p) for p in sorted((self.root / "runs").iterdir())]

    def test_pooled_rule_is_one_step_for_every_policy_and_adaptation_has_a_value(self):
        steps, values = pooled_rules(self.runs, CONFIG, {"Plain": 1000})
        self.assertEqual(steps, {"Plain": 400})  # declaring at 100 would fail every slow run
        own = best_fixed_rules(self.runs, CONFIG, {"Plain": 1000})
        self.assertAlmostEqual(own[("fast", "Plain", "no_restart")]["value"], 0.95)
        self.assertAlmostEqual(values[("fast", "Plain")], 0.80)  # adapting to the fast policy is worth 0.15

    def test_session_summary_scores_each_label_and_its_learning(self):
        session = self.root / "sessions" / "s1"
        session.mkdir(parents=True)
        lines = []
        for order, (label, backend, steps) in enumerate((("K", "fast", 300), ("R", "slow", 450), ("K", "fast", 120),
                                                         ("R", "slow", 420))):
            name = f"ep{order}"
            episode(session / "episodes", name, backend=backend, steps=steps, truth=[False] * steps + [True],
                    model_calls=2, decisions=[run(0, steps, "go"), COMPLETE(steps)])
            lines.append(json.dumps({"session_id": "s1", "index": order, "policy_label": label, "backend": backend,
                                     "task": "Plain", "scene_seed": 1000, "policy_seed": 0,
                                     "episode_dir": f"episodes/{name}"}) + "\n")
        (session / "session.jsonl").write_text("".join(lines))
        rules = best_fixed_rules(self.runs, CONFIG, {"Plain": 1000})
        _, pooled = pooled_rules(self.runs, CONFIG, {"Plain": 1000})
        summary = session_summary(read_session(session / "session.jsonl"), CONFIG, rules, pooled)["policies"]
        k = summary["K"]  # values 1 - (15 + 10)/100 = 0.75, then 1 - (6 + 10)/100 = 0.84; own rule 0.95
        self.assertEqual((k["backend"], k["n"]), ("fast", 2))
        self.assertAlmostEqual(k["regret"], ((0.95 - 0.75) + (0.95 - 0.84)) / 2)
        self.assertAlmostEqual(k["learning"], (0.95 - 0.84) - (0.95 - 0.75))  # negative: it improved
        self.assertAlmostEqual(k["pooled_rule_value"], 0.80)


if __name__ == "__main__":
    unittest.main()
