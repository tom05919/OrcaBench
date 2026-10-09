import json
import os
import tempfile
import unittest

from robot_benchmark.baselines import AlwaysDeferAgent, ReissueAgent
from robot_benchmark.contracts import ModelReply
from robot_benchmark.sim.agent import BudgetExceeded, Tracker, build_content, current_block
from robot_benchmark.sim.harness import GOAL, Setup, SimEpisode, utility
from robot_benchmark.sim.perception import reading
from robot_benchmark.sim.probes import Scripted, candidates, make_log, situations
from robot_benchmark.sim.process import BRITTLE, HESITANT, STEADY, World
from robot_benchmark.sim.references import FixedRule, Oracle, opus_like

SEEDS = range(900_000, 900_400)


def run(agent, profile=STEADY, seed=1, **kwargs):
    return SimEpisode(Setup(profile, seed, **kwargs)).run(agent)


class ProcessTests(unittest.TestCase):
    def test_same_seed_gives_the_same_world_and_agents_face_the_same_latent_draws(self):
        a, b = World(STEADY, 7), World(STEADY, 7)
        self.assertEqual((a.W, a.lag, a.loss_after, a.events), (b.W, b.lag, b.loss_after, b.events))
        self.assertEqual(run(AlwaysDeferAgent(), seed=7)["success"], run(AlwaysDeferAgent(), seed=7)["success"])
        self.assertNotEqual(World(STEADY, 7).W, World(STEADY, 8).W)

    def test_visual_completion_leads_the_checker_by_the_lag(self):
        w = World(STEADY, 3)
        w.advance(w.W)
        self.assertEqual(w.mode, "RETREAT" if w.lag else "DONE")
        self.assertFalse(w.checker())
        w.advance(w.lag)
        self.assertTrue(w.checker())

    def test_a_stalled_policy_only_moves_after_a_restart_that_frees_it(self):
        w = World(BRITTLE, 11)
        w.events = [(50, "STUCK", 0)]
        w.advance(500)
        self.assertEqual((w.mode, w.work_done), ("STUCK", 50))
        freed = False
        for _ in range(40):
            if w.restart() == "freed":
                freed = True
                break
        self.assertTrue(freed)
        w.advance(w.W + 400)
        self.assertIn(w.mode, ("DONE", "RETREAT", "BROKEN", "STUCK", "WORK", "LOST"))

    def test_a_hover_resolves_on_its_own(self):
        w = World(HESITANT, 5)
        w.events = [(40, "HOVER", 100)]
        w.advance(139)
        self.assertEqual((w.mode, w.work_done), ("HOVER", 40))
        w.advance(2)
        self.assertEqual(w.mode, "WORK")

    def test_restart_after_completion_can_undo_it(self):
        undone = sum(1 for k in range(400) if self._restart_after_done(k) == "undo")
        self.assertTrue(60 < undone < 180)   # q_undo = 0.3 of 400

    @staticmethod
    def _restart_after_done(seed):
        w = World(STEADY, seed + 1000)
        w.advance(w.W + w.lag)
        return w.restart()

    def test_fork_keeps_the_latent_state_and_changes_the_future(self):
        w = World(BRITTLE, 21)
        w.advance(60)
        f = w.fork(999)
        self.assertEqual((f.mode, f.work_done, f.W, f.lag, f.t), (w.mode, w.work_done, w.W, w.lag, w.t))
        self.assertTrue(all(x > w.work_done for x, _, _ in f.events))


class PerceptionTests(unittest.TestCase):
    def test_complete_state_looks_complete_about_seventy_percent_and_early_work_almost_never(self):
        w = World(STEADY, 1)
        after = sum(reading(w, "DONE", w.W, s) == "looks complete" for s in range(4000)) / 4000
        early = sum(reading(w, "WORK", 10, s) == "looks complete" for s in range(4000)) / 4000
        near = sum(reading(w, "WORK", w.W - 30, s) == "looks complete" for s in range(4000)) / 4000
        self.assertAlmostEqual(after, 0.70, delta=0.03)
        self.assertAlmostEqual(early, 0.02, delta=0.01)
        self.assertAlmostEqual(near, 0.30, delta=0.03)

    def test_two_agents_looking_at_the_same_step_see_the_same_reading(self):
        w = World(STEADY, 4)
        self.assertEqual([reading(w, "WORK", 100, 55)] * 3, [reading(w, "WORK", 100, 55) for _ in range(3)])


class HarnessTests(unittest.TestCase):
    def test_first_run_needs_a_prompt_and_an_invalid_reply_costs_a_decision(self):
        ep = SimEpisode(Setup(STEADY, 1))
        ep.decide_once(Scripted([{"op": "run_policy", "steps": 50}], then=AlwaysDeferAgent()))
        self.assertEqual((ep.decisions, ep.steps, ep.history[0]["accepted"]), (1, 0, False))
        self.assertIn("requires a prompt", ep.last_error)

    def test_prompt_counters_follow_the_real_runner(self):
        ep = SimEpisode(Setup(STEADY, 1))
        for d in ({"op": "run_policy", "prompt": GOAL, "steps": 10}, {"op": "run_policy", "prompt": GOAL, "steps": 10},
                  {"op": "run_policy", "prompt": "Other text", "steps": 10}, {"op": "run_policy", "steps": 10}):
            ep.decide_once(Scripted([d]))
        self.assertEqual((ep.prompt_submissions, ep.prompt_restarts, ep.prompt_changes), (3, 1, 1))
        self.assertEqual(len(ep.restart_log), 2)   # the first submission is not a restart

    def test_keyframes_are_evenly_spaced_strictly_inside_the_interval(self):
        ep = SimEpisode(Setup(STEADY, 1))
        ep.decide_once(Scripted([{"op": "run_policy", "prompt": GOAL, "steps": 100}]))
        self.assertEqual([f["step"] for f in ep.interval_frames], [20, 40, 60, 80])
        ep.decide_once(Scripted([{"op": "run_policy", "steps": 3}]))
        self.assertEqual([f["step"] for f in ep.interval_frames], [101, 102])

    def test_complete_succeeds_only_while_the_checker_is_true(self):
        early = SimEpisode(Setup(STEADY, 1))
        early.decide_once(Scripted([{"op": "run_policy", "prompt": GOAL, "steps": 10}, ]))
        early.decide_once(Scripted([{"op": "complete"}]))
        self.assertEqual(early.status, "false_completion")

    def test_budgets_end_the_episode(self):
        r = run(Scripted([{"op": "run_policy", "prompt": GOAL, "steps": 400}] * 2 + [{"op": "run_policy", "steps": 100}], then=Scripted([{"op": "run_policy", "steps": 1}] * 1)),
                BRITTLE, 3)
        self.assertIn(r["status"], ("step_budget_exhausted", "false_completion", "success"))

    def test_the_real_baselines_run_unchanged(self):
        r = run(AlwaysDeferAgent())
        self.assertEqual((r["steps"], r["model_calls"]), (899, 4))
        self.assertEqual(run(ReissueAgent())["prompt_restarts"], 8)

    def test_the_experience_record_holds_no_latent_state_or_statistics(self):
        ep = SimEpisode(Setup(HESITANT, 2))
        ep.run(FixedRule(200, 200, None, "first"))
        record = ep.record()
        self.assertEqual(set(record), {"policy", "episode", "decisions", "outcome", "steps", "calls", "score"})
        text = json.dumps(record)
        for leaked in ("mode", "STUCK", "HOVER", "RETREAT", "work_done", "lag", "profile", "hesitant"):
            self.assertNotIn(leaked, text)

    def test_the_observation_shown_to_a_model_has_no_latent_state(self):
        ep = SimEpisode(Setup(BRITTLE, 9, "K", 1, ()))
        ep.decide_once(Scripted([{"op": "run_policy", "prompt": GOAL, "steps": 200}]))
        text = current_block(ep.observation())
        for leaked in ("STUCK", "HOVER", "RETREAT", "work_done", "brittle", "profile", "latent"):
            self.assertNotIn(leaked, text)

    def test_utility_matches_the_stated_exchange_rates(self):
        self.assertAlmostEqual(utility(True, 4, 899), 1 - 0.08 - 0.002 * 899 / 20)
        self.assertAlmostEqual(utility(False, 3, 0), -0.06)


class ReferenceTests(unittest.TestCase):
    def mean(self, factory, profile, key="success"):
        return sum(run(factory(), profile, s)[key] for s in SEEDS) / len(SEEDS)

    def test_always_defer_success_is_near_the_calibration_targets(self):
        self.assertAlmostEqual(self.mean(AlwaysDeferAgent, STEADY), 0.97, delta=0.04)
        self.assertAlmostEqual(self.mean(AlwaysDeferAgent, HESITANT), 0.83, delta=0.05)
        self.assertAlmostEqual(self.mean(AlwaysDeferAgent, BRITTLE), 0.27, delta=0.06)

    def test_declaring_at_the_first_sight_fails_more_often_than_confirming(self):
        first = self.mean(lambda: FixedRule(200, 100, None, "first"), STEADY)
        confirm = self.mean(lambda: FixedRule(200, 100, None, "confirm"), STEADY)
        self.assertGreater(confirm, first)

    def test_blind_restarts_hurt_the_hesitant_vla_and_help_the_brittle_one(self):
        self.assertLess(self.mean(lambda: ReissueAgent(100), HESITANT), self.mean(AlwaysDeferAgent, HESITANT) - 0.4)
        self.assertGreater(self.mean(lambda: ReissueAgent(100), BRITTLE), self.mean(AlwaysDeferAgent, BRITTLE) + 0.2)

    def test_the_oracle_is_the_upper_bound(self):
        for profile in (STEADY, HESITANT):
            oracle = sum(SimEpisode(Setup(profile, s)).run(Oracle(), privileged=True)["utility"] for s in SEEDS) / len(SEEDS)
            self.assertGreater(oracle, self.mean(lambda: opus_like(), profile, "utility"))

    def test_fixed_rules_are_stateless_so_a_fork_can_continue_them(self):
        ep = SimEpisode(Setup(STEADY, 5))
        agent = FixedRule(100, 100, None, "first")
        for _ in range(2):
            ep.decide_once(agent)
        fork = ep.fork(77)
        self.assertEqual(fork.run(FixedRule(100, 100, None, "first"))["status"] in ("success", "false_completion", "step_budget_exhausted"), True)


class ProbeTests(unittest.TestCase):
    def test_situations_are_generated_by_rule_and_are_the_same_every_time(self):
        a = [(s, e.steps) for s, e in situations("brittle", "S2", 2)]
        b = [(s, e.steps) for s, e in situations("brittle", "S2", 2)]
        self.assertEqual(a, b)
        for _, ep in situations("steady", "S3", 2):
            self.assertEqual(ep.reading, "looks complete")

    def test_candidate_sets_cover_declaring_waiting_and_restarting(self):
        self.assertIn({"op": "complete"}, candidates("S3"))
        self.assertTrue(any("prompt" in c for c in candidates("S2")) and any("prompt" not in c for c in candidates("S2")))

    def test_experience_logs_are_interleaved_in_blocks_of_three_with_a_label_each(self):
        log = make_log({"steady": "K", "hesitant": "R", "brittle": "T"}, 3, 1)
        self.assertEqual(len(log), 9)
        for block in range(3):
            self.assertEqual(sorted(r["policy"] for r in log[3 * block: 3 * block + 3]), ["K", "R", "T"])
        self.assertEqual([r["episode"] for r in log], list(range(1, 10)))


class AgentPlumbingTests(unittest.TestCase):
    def test_the_last_experience_block_carries_the_cache_breakpoint(self):
        ep = SimEpisode(Setup(STEADY, 1, "K", 3, ({"a": 1}, {"b": 2})))
        blocks = build_content(ep.observation())
        self.assertEqual([("cache_control" in b) for b in blocks], [False, False, True, False])
        self.assertTrue(blocks[-1]["text"].startswith("Current episode:"))
        self.assertEqual(len(build_content(SimEpisode(Setup(STEADY, 1)).observation())), 1)

    def test_the_tracker_stops_at_the_limit_and_shares_a_ledger(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = os.path.join(folder, "spend.jsonl")
            t = Tracker(0.01, ledger)
            t.add("claude-opus-5-5", {"input_tokens": 1000, "output_tokens": 500})   # $0.014
            with self.assertRaises(BudgetExceeded):
                t.check()
            self.assertAlmostEqual(Tracker(1.0, ledger).spent, 0.014, places=6)


if __name__ == "__main__":
    unittest.main()
