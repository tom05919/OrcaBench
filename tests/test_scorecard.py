import json
import tempfile
import unittest
from pathlib import Path

from robot_benchmark.evaluation import wilson_interval
from robot_benchmark.scorecard import attribute_failure, load_scored_episodes, scorecard

RELEASE = {"schema_version": 1, "status": "frozen", "contract_hash": "h", "models": ["m"],
           "reference_policy_seeds": [5, 6],
           "tasks": {"T": {"config": {}, "leave_alone": [1, 2], "needs_help": [3]}}}


def ep(kind="llm", model="m", task="T", scene=1, policy=5, status="success", goal="g", transitions=(), success_steps=(), contract="h", **result):
    result = {"status": status, "success": status == "success", "goal": goal, "scene_seed": scene,
              "policy_seed": policy, **result}
    manifest = {"kind": kind, "agent": {"kind": kind, "model": model}, "task": task, "seed": scene,
                "scene_seed": scene, "policy_seed": policy, "contract_hash": contract}
    return {"manifest": manifest, "result": result, "transitions": list(transitions), "success_steps": list(success_steps)}


def ref(scene, policy, ok, task="T"):
    return ep("diagnostic_reference", "none", task, scene, policy, "success" if ok else "step_budget_exhausted",
              success_steps=[10] if ok else [])


def sysep(scene, policy, ok, **kw):
    return ep(scene=scene, policy=policy, status="success" if ok else "step_budget_exhausted", **kw)


class AttributionTests(unittest.TestCase):
    def test_false_completion(self):
        self.assertEqual(attribute_failure(ep(status="false_completion"), "leave_alone", None), "false_completion")

    def test_missed_completion(self):
        for status in ("step_budget_exhausted", "decision_budget_exhausted"):
            e = ep(status=status, physical_success_any=True)
            self.assertEqual(attribute_failure(e, "needs_help", None), "missed_completion")
        e = ep(status="infrastructure_error", physical_success_any=True)
        self.assertEqual(attribute_failure(e, "needs_help", None), "missed_intervention")

    def test_unnecessary_intervention_second_transition(self):
        e = ep(status="step_budget_exhausted", transitions=[{"step": 0, "instruction": "g"}, {"step": 4, "instruction": "g"}])
        self.assertEqual(attribute_failure(e, "leave_alone", ref(1, 5, True)), "unnecessary_intervention")

    def test_unnecessary_intervention_changed_instruction(self):
        e = ep(status="step_budget_exhausted", transitions=[{"step": 2, "instruction": "other"}])
        self.assertEqual(attribute_failure(e, "leave_alone", ref(1, 5, True)), "unnecessary_intervention")

    def test_deviation_after_reference_success_is_not_unnecessary(self):
        e = ep(status="step_budget_exhausted", transitions=[{"step": 0, "instruction": "g"}, {"step": 10, "instruction": "g"}])
        self.assertEqual(attribute_failure(e, "leave_alone", ref(1, 5, True)), "executor_or_other")

    def test_no_reference_success_is_not_unnecessary(self):
        e = ep(status="step_budget_exhausted", transitions=[{"step": 0, "instruction": "g"}, {"step": 4, "instruction": "g"}])
        for paired in (None, ref(1, 5, False)):
            self.assertEqual(attribute_failure(e, "leave_alone", paired), "executor_or_other")

    def test_missed_intervention(self):
        e = ep(status="step_budget_exhausted", transitions=[{"step": 0, "instruction": "g"}])
        self.assertEqual(attribute_failure(e, "needs_help", None), "missed_intervention")
        self.assertEqual(attribute_failure(ep(status="step_budget_exhausted"), "needs_help", ref(3, 5, True)), "missed_intervention")

    def test_needs_help_with_deviation_is_other(self):
        e = ep(status="step_budget_exhausted", transitions=[{"step": 0, "instruction": "g"}, {"step": 4, "instruction": "h"}])
        self.assertEqual(attribute_failure(e, "needs_help", ref(3, 5, False)), "executor_or_other")

    def test_leave_alone_no_deviation_is_other(self):
        self.assertEqual(attribute_failure(ep(status="step_budget_exhausted"), "leave_alone", ref(1, 5, True)), "executor_or_other")


class ScorecardTests(unittest.TestCase):
    def leave_alone_example(self):
        # Ten scene seeds with one policy seed each: reference succeeds on 9, the system on 5.
        release = {**RELEASE, "reference_policy_seeds": [5], "tasks": {"T": {"config": {}, "leave_alone": list(range(10)), "needs_help": []}}}
        eps = [ref(s, 5, s != 0) for s in range(10)] + [sysep(s, 5, s < 5) for s in range(10)]
        return eps, release

    def system(self, card):
        self.assertEqual(len(card["systems"]), 1)
        return card["systems"][0]

    def test_harm_hand_computed(self):
        eps, release = self.leave_alone_example()
        card = scorecard(eps, release, bootstrap_samples=200)
        s = self.system(card)
        self.assertAlmostEqual(s["harm"]["estimate"], 0.4)
        self.assertEqual(s["groups"]["leave_alone"]["successes"], 5)
        self.assertEqual(s["groups"]["leave_alone"]["wilson_95"], wilson_interval(5, 10))
        self.assertEqual(card["reference"]["leave_alone"]["successes"], 9)
        self.assertIsNone(s["rescue"]["estimate"])
        self.assertIn("privileged", card["note"])

    def test_rescue_hand_computed(self):
        release = {**RELEASE, "tasks": {"T": {"config": {}, "leave_alone": [], "needs_help": [3, 4, 5, 6]}}}
        eps = [ref(s, 5, s == 3) for s in (3, 4, 5, 6)] + [sysep(s, 5, s in (3, 4, 5)) for s in (3, 4, 5, 6)]
        s = self.system(scorecard(eps, release, bootstrap_samples=100))
        self.assertAlmostEqual(s["rescue"]["estimate"], 0.75 - 0.25)
        self.assertIsNone(s["harm"]["estimate"])

    def test_bootstrap_brackets_and_is_deterministic(self):
        eps, release = self.leave_alone_example()
        a = self.system(scorecard(eps, release, bootstrap_samples=500, rng_seed=3))["harm"]
        b = self.system(scorecard(eps, release, bootstrap_samples=500, rng_seed=3))["harm"]
        self.assertEqual(a, b)
        lo, hi = a["ci_95"]
        self.assertLessEqual(lo, a["estimate"])
        self.assertGreaterEqual(hi, a["estimate"])
        self.assertLess(lo, hi)

    def test_bootstrap_resamples_clusters_not_episodes(self):
        # Three scenes x two policy seeds. The system fails every episode of scene 1 only. Resampling the three
        # clusters gives harm 1.0 in 1/27 of draws and 0.0 in 8/27, so the interval is [0, 1]; resampling the six
        # episodes independently would almost never reach 1.0.
        release = {**RELEASE, "tasks": {"T": {"config": {}, "leave_alone": [1, 2, 3], "needs_help": []}}}
        eps = [ref(s, p, True) for s in (1, 2, 3) for p in (5, 6)] + [sysep(s, p, s != 1) for s in (1, 2, 3) for p in (5, 6)]
        harm = self.system(scorecard(eps, release, bootstrap_samples=2000))["harm"]
        self.assertAlmostEqual(harm["estimate"], 1 / 3)
        self.assertEqual(harm["ci_95"], [0.0, 1.0])
        self.assertEqual(harm["valid_draws"], 2000)

    def test_different_rng_seed_changes_interval(self):
        release = {**RELEASE, "reference_policy_seeds": [5], "tasks": {"T": {"config": {}, "leave_alone": list(range(30)), "needs_help": []}}}
        eps = [ref(s, 5, s % 7 != 0) for s in range(30)] + [sysep(s, 5, s % 3 == 0) for s in range(30)]
        cis = [self.system(scorecard(eps, release, bootstrap_samples=60, rng_seed=r))["harm"]["ci_95"] for r in range(6)]
        self.assertGreater(len(set(map(tuple, cis))), 1)

    def test_no_paired_cluster_gives_null_estimate(self):
        # Reference only on scene 1, system only on scene 2, scene 3 has a system infrastructure error and a reference:
        # no cluster has a usable episode on both sides.
        release = {**RELEASE, "reference_policy_seeds": [5], "tasks": {"T": {"config": {}, "leave_alone": [1, 2, 3], "needs_help": []}}}
        eps = [ref(1, 5, True), sysep(2, 5, False), ep(scene=3, policy=5, status="infrastructure_error"), ref(3, 5, True)]
        s = self.system(scorecard(eps, release, bootstrap_samples=200))
        self.assertEqual(s["harm"], {"estimate": None, "ci_95": None, "valid_draws": 0, "unpaired_clusters": 3})
        self.assertEqual(s["groups"]["leave_alone"]["successes"], 0)
        self.assertEqual(s["rescue"]["unpaired_clusters"], 0)

    def test_unpaired_clusters_are_left_out_of_harm_but_not_success_rates(self):
        eps, release = self.leave_alone_example()
        release = {**release, "tasks": {"T": {"config": {}, "leave_alone": list(range(12)), "needs_help": []}}}
        card = scorecard(eps + [ref(10, 5, False), sysep(11, 5, True)], release, bootstrap_samples=200)
        s = self.system(card)
        self.assertAlmostEqual(s["harm"]["estimate"], 0.4)
        self.assertEqual(s["harm"]["unpaired_clusters"], 2)
        self.assertEqual((s["groups"]["leave_alone"]["usable"], s["groups"]["leave_alone"]["successes"]), (11, 6))
        self.assertEqual((card["reference"]["leave_alone"]["usable"], card["reference"]["leave_alone"]["successes"]), (11, 9))

    def test_exclusions_and_reference_not_a_system(self):
        eps, release = self.leave_alone_example()
        release = {**release, "tasks": {"T": {"config": {}, "leave_alone": list(range(10)), "needs_help": []}}}
        extra = [sysep(0, 9, True), sysep(99, 5, True), ep(task="Other", scene=0, policy=5)]
        s = self.system(scorecard(eps + extra, release, bootstrap_samples=50))
        self.assertEqual(s["groups"]["leave_alone"]["attempted"], 10)
        self.assertEqual({(x["kind"], x["model"]) for x in scorecard(eps, release, bootstrap_samples=50)["systems"]}, {("llm", "m")})

    def test_infrastructure_errors_counted_separately(self):
        release = {**RELEASE, "tasks": {"T": {"config": {}, "leave_alone": [1, 2, 3], "needs_help": []}}, "reference_policy_seeds": [5]}
        eps = [sysep(1, 5, True), sysep(2, 5, False), ep(scene=3, policy=5, status="infrastructure_error"), ref(1, 5, True)]
        g = self.system(scorecard(eps, release, bootstrap_samples=20))["groups"]["leave_alone"]
        self.assertEqual((g["attempted"], g["infrastructure_errors"], g["usable"], g["successes"]), (3, 1, 2, 1))
        self.assertEqual(g["success_rate"], 0.5)

    def test_totals_and_no_declaration(self):
        release = {**RELEASE, "tasks": {"T": {"config": {}, "leave_alone": [1, 2, 3], "needs_help": []}}, "reference_policy_seeds": [5]}
        eps = [ep(scene=1, policy=5, steps=10, model_calls=2, wall_seconds=1.5, usage=[{"input_tokens": 5, "x": "y"}], intervals=[100, 400]),
               ep(scene=2, policy=5, status="step_budget_exhausted", steps=30, model_calls=4, prompt_submissions=3, usage=[{"input_tokens": 7}], intervals=[400]),
               ep(scene=3, policy=5, status="decision_budget_exhausted", steps=20, discarded_actions=2),
               ep(scene=1, policy=6, status="false_completion")]
        g = self.system(scorecard(eps, release, bootstrap_samples=20))["groups"]["leave_alone"]
        self.assertEqual(g["no_declaration"], 2)
        self.assertEqual((g["no_declaration_rate"], g["false_completion_rate"]), (2 / 3, 0.0))  # policy 6 is outside the release
        self.assertEqual(g["interval_histogram"], {"100": 1, "400": 2})
        self.assertEqual((g["total_steps"], g["total_model_calls"], g["prompt_submissions"], g["discarded_actions"]), (60, 6, 3, 2))
        self.assertEqual(g["token_usage_totals"], {"input_tokens": 12})
        self.assertAlmostEqual(g["mean_steps"], 20)
        self.assertEqual(g["wall_seconds"], 1.5)

    def test_timing_reports_simulated_and_real_time_with_success_only_means(self):
        release = {**RELEASE, "tasks": {"T": {"config": {}, "leave_alone": [1, 2, 3], "needs_help": []}}, "reference_policy_seeds": [5]}
        eps = [ep(scene=1, policy=5, simulated_seconds=10.0, wall_seconds=100.0, model_seconds=40.0, policy_seconds=30.0),
               ep(scene=2, policy=5, status="step_budget_exhausted", simulated_seconds=30.0, wall_seconds=300.0,
                  model_seconds=80.0, policy_seconds=50.0),
               ep(scene=3, policy=5, status="step_budget_exhausted")]  # no timing fields: unknown, not zero
        timing = self.system(scorecard(eps, release, bootstrap_samples=20))["groups"]["leave_alone"]["timing"]
        self.assertEqual(timing["simulated_seconds"], {"total": 40.0, "mean": 20.0, "mean_success": 10.0})
        self.assertEqual(timing["wall_seconds"], {"total": 400.0, "mean": 200.0, "mean_success": 100.0})
        self.assertEqual(timing["model_seconds"]["mean"], 60.0)
        self.assertEqual(timing["policy_seconds"]["mean_success"], 30.0)
        empty = self.system(scorecard([ep(scene=3, policy=5, status="step_budget_exhausted")], release,
                                      bootstrap_samples=20))["groups"]["leave_alone"]["timing"]
        self.assertEqual(empty["simulated_seconds"], {"total": None, "mean": None, "mean_success": None})

    def test_false_completions_and_attribution(self):
        release = {**RELEASE, "reference_policy_seeds": [5], "tasks": {"T": {"config": {}, "leave_alone": [1, 2], "needs_help": [3]}}}
        eps = [ref(1, 5, True), ref(2, 5, True), ref(3, 5, False),
               ep(scene=1, policy=5, status="false_completion"),
               ep(scene=2, policy=5, status="step_budget_exhausted", transitions=[{"step": 0, "instruction": "g"}, {"step": 3, "instruction": "g"}]),
               ep(scene=3, policy=5, status="step_budget_exhausted", transitions=[{"step": 0, "instruction": "g"}])]
        s = self.system(scorecard(eps, release, bootstrap_samples=20))
        self.assertEqual(s["groups"]["leave_alone"]["false_completions"], 1)
        self.assertEqual((s["groups"]["leave_alone"]["false_completion_rate"], s["groups"]["leave_alone"]["no_declaration_rate"]), (0.5, 0.5))
        att = s["attribution"]
        self.assertEqual((att["false_completion"], att["unnecessary_intervention"], att["missed_intervention"]), (1, 1, 1))

    def test_always_defer_reference_agreement(self):
        defer = lambda scene, policy, status: ep("baseline_always_defer", "always_defer_v1", scene=scene, policy=policy, status=status)
        eps = [ref(1, 5, True), ref(1, 6, False), ref(3, 5, False), sysep(1, 5, False),
               defer(1, 5, "success"), defer(1, 6, "success"), defer(3, 5, "step_budget_exhausted"),
               defer(2, 5, "success"), defer(3, 6, "infrastructure_error")]
        systems = {x["kind"]: x for x in scorecard(eps, RELEASE, bootstrap_samples=20)["systems"]}
        self.assertEqual(systems["baseline_always_defer"]["reference_agreement"], {"paired": 3, "agreements": 2, "rate": 2 / 3})
        self.assertNotIn("reference_agreement", systems["llm"])

    def test_unknown_is_null(self):
        s = self.system(scorecard([sysep(1, 5, True)], RELEASE, bootstrap_samples=20))
        self.assertIsNone(s["groups"]["needs_help"]["false_completion_rate"])
        self.assertIsNone(s["groups"]["needs_help"]["no_declaration_rate"])
        self.assertIsNone(s["harm"]["estimate"])
        self.assertIsNone(s["harm"]["ci_95"])
        self.assertIsNone(s["groups"]["needs_help"]["success_rate"])
        self.assertIsNone(s["groups"]["needs_help"]["wilson_95"])


class ValidationTests(unittest.TestCase):
    def test_two_usable_attempts_of_one_episode_raise(self):
        for dup in (sysep(1, 5, True), ref(1, 5, True)):
            with self.assertRaises(ValueError):
                scorecard([dup, dup], RELEASE, bootstrap_samples=10)
        # a different model or policy seed is not a duplicate
        scorecard([sysep(1, 5, True), ep(model="n", scene=1, policy=5), sysep(1, 6, True)], RELEASE, bootstrap_samples=10)

    def test_missing_model_is_one_key_everywhere(self):
        a, b = ep(scene=1, policy=5), ep(scene=1, policy=5)
        del a["manifest"]["agent"]["model"]
        b["manifest"]["agent"] = None
        with self.assertRaises(ValueError):
            scorecard([a, b], RELEASE, bootstrap_samples=10)
        self.assertEqual(scorecard([a], RELEASE, bootstrap_samples=10)["systems"][0]["model"], "setup_pending")

    def test_infrastructure_retry_is_allowed_and_counted(self):
        infra = ep(scene=1, policy=5, status="infrastructure_error")
        card = scorecard([infra, infra, sysep(1, 5, True)], RELEASE, bootstrap_samples=10)
        g = card["systems"][0]["groups"]["leave_alone"]
        self.assertEqual((g["attempted"], g["infrastructure_errors"], g["usable"], g["successes"]), (3, 2, 1, 1))
        with self.assertRaises(ValueError):
            scorecard([infra, sysep(1, 5, True), sysep(1, 5, False)], RELEASE, bootstrap_samples=10)

    def test_infrastructure_retry_of_reference_pairs_with_usable_attempt(self):
        release = {**RELEASE, "reference_policy_seeds": [5]}
        infra = ep("diagnostic_reference", "none", scene=1, policy=5, status="infrastructure_error")
        e = ep(status="step_budget_exhausted", scene=1, policy=5, transitions=[{"step": 0, "instruction": "g"}, {"step": 4, "instruction": "g"}])
        card = scorecard([infra, ref(1, 5, True), e], release, bootstrap_samples=10)
        self.assertEqual(card["systems"][0]["attribution"]["unnecessary_intervention"], 1)
        self.assertEqual(card["reference"]["leave_alone"]["infrastructure_errors"], 1)

    def test_privileged_diagnostics_are_never_systems(self):
        release = {**RELEASE, "reference_policy_seeds": [5]}
        extra = [ep("diagnostic_retry", "none", scene=1, policy=5, status="step_budget_exhausted"),
                 ep("diagnostic_sequencer", "none", scene=2, policy=5)]
        card = scorecard([ref(1, 5, True), sysep(1, 5, True)] + extra, release, bootstrap_samples=10)
        self.assertEqual([(x["kind"], x["model"]) for x in card["systems"]], [("llm", "m")])
        self.assertEqual(card["excluded_diagnostic"], 2)
        self.assertEqual(sum(card["systems"][0]["attribution"].values()), 0)
        self.assertEqual(card["reference"]["leave_alone"]["attempted"], 1)

    def test_baselines_are_systems_and_development_runs_are_excluded(self):
        release = {**RELEASE, "reference_policy_seeds": [5]}
        kinds = ("llm", "llm_development", "baseline_always_defer", "baseline_reissue")
        card = scorecard([ep(k, "none", scene=1, policy=5) for k in kinds] + [ep("llm_development", "none", scene=2, policy=5)],
                         release, bootstrap_samples=10)
        self.assertEqual(sorted(x["kind"] for x in card["systems"]), ["baseline_always_defer", "baseline_reissue", "llm"])
        self.assertEqual((card["excluded_diagnostic"], card["excluded_development"]), (0, 2))

    def test_contract_mismatch_excluded_and_reported(self):
        eps = [sysep(1, 5, True), ep(scene=1, policy=5, contract="other"), ep(scene=2, policy=5, contract="other")]
        card = scorecard(eps, RELEASE, bootstrap_samples=10)
        self.assertEqual(card["excluded_contract_mismatch"], 2)
        self.assertEqual(card["systems"][0]["groups"]["leave_alone"]["attempted"], 1)
        self.assertEqual(scorecard([sysep(1, 5, True)], RELEASE, bootstrap_samples=10)["excluded_contract_mismatch"], 0)

    def test_scene_seed_in_both_groups_raises(self):
        release = {**RELEASE, "tasks": {"T": {"config": {}, "leave_alone": [1, 2], "needs_help": [2, 3]}}}
        with self.assertRaises(ValueError):
            scorecard([], release, bootstrap_samples=10)


class LoadTests(unittest.TestCase):
    def test_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good, bad, other = root / "a", root / "b", root / "c"
            for d in (good, bad, other):
                (d / "evaluator").mkdir(parents=True)
            manifest = ep()["manifest"]
            (good / "manifest.json").write_text(json.dumps({**manifest, "artifact_type": "episode"}))
            (good / "result.json").write_text(json.dumps({"status": "success", "success": True, "goal": "g"}))
            (good / "policy_transitions.jsonl").write_text('{"step": 0, "instruction": "g"}\n{"step": 5, "instruction": "h"}\n')
            (good / "evaluator" / "events.jsonl").write_text('{"step": 3, "success": false}\n{"step": 8, "success": true}\n{"step": 9, "success": true}\n')
            (bad / "manifest.json").write_text(json.dumps({**manifest, "artifact_type": "episode"}))
            (other / "manifest.json").write_text(json.dumps({"artifact_type": "other"}))
            eps = load_scored_episodes(root)
            self.assertEqual(len(eps), 2)
            by_status = {e["result"]["status"]: e for e in eps}
            self.assertEqual(by_status["success"]["success_steps"], [8, 9])
            self.assertEqual([t["step"] for t in by_status["success"]["transitions"]], [0, 5])
            self.assertEqual(by_status["infrastructure_error"]["transitions"], [])
            self.assertEqual(by_status["infrastructure_error"]["success_steps"], [])

    def test_truncated_final_log_line_is_ignored_but_corruption_elsewhere_raises(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "episode"
            (folder / "evaluator").mkdir(parents=True)
            (folder / "manifest.json").write_text(json.dumps({"artifact_type": "episode"}))
            (folder / "result.json").write_text(json.dumps({"status": "success", "success": True}))
            events = folder / "evaluator" / "events.jsonl"
            events.write_text('{"step": 1, "success": false}\n{"step": 2, "success": true}\n{"step": 3, "succ')
            (episode,) = load_scored_episodes(temporary)
            self.assertEqual(episode["success_steps"], [2])
            events.write_text('{"step": 1, "succ\n{"step": 2, "success": true}\n')
            with self.assertRaises(json.JSONDecodeError):
                load_scored_episodes(temporary)

    def test_truncated_result_is_infrastructure_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "a"
            folder.mkdir()
            (folder / "manifest.json").write_text(json.dumps({**ep()["manifest"], "artifact_type": "episode"}))
            (folder / "result.json").write_text('{"status": "success", "succ')
            (e,) = load_scored_episodes(tmp)
            self.assertEqual((e["result"]["status"], e["result"]["success"]), ("infrastructure_error", False))
            (folder / "manifest.json").write_text("{")
            with self.assertRaises(ValueError):
                load_scored_episodes(tmp)


if __name__ == "__main__":
    unittest.main()
