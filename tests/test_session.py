"""Session privacy, plan validation, and append-before-attempt retention."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from robot_benchmark import session
from robot_benchmark.contracts import CAMERAS, ModelReply
from robot_benchmark.adapters.agents import HTTPAgent, SESSION_SCORE
from tests.fakes import PNG_URL


def plan(label="K", backend="groot", seed=0):
    return {"task": "OpenDrawer", "scene_seed": seed, "policy_seed": 0,
            "policy_label": label, "backend": backend}


def result(status="success"):
    return {"status": status, "success": status == "success", "goal": "Open the drawer.",
            "steps": 20, "model_calls": 2, "infrastructure_error": None,
            "scene_seed": 123, "reward": 1, "object_coordinates": [1, 2, 3]}


DECISIONS = [{"accepted": True, "step_before": 0,
              "decision": {"op": "run_policy", "steps": 20, "prompt": "Open the drawer."}},
             {"accepted": False, "step_before": 20, "decision": {"reward": 900}},
             {"accepted": True, "step_before": 20, "decision": {"op": "complete"}}]
WORKERS = {"K": "http://127.0.0.1:8000"}
TIME = {"call_seconds": 4.7, "deadline_seconds": 30,
        "score": "success x max(0, 1 - charged_seconds / deadline_seconds)"}


class Agent:
    identity = {"model": "model", "prompt_version": 6, "session_mode": True}
    last_trace = {"usage": 3}

    def decide(self, observation):
        self.observation = observation
        return ModelReply({"op": "complete"})


class PlanTests(unittest.TestCase):
    def test_valid_plan_is_copied_and_accepts_unsigned_seed_bounds(self):
        entries = [plan(), plan(seed=2**32 - 1)]
        parsed = session.validate_plan(entries, {"OpenDrawer"}, WORKERS)
        self.assertEqual(parsed, entries)
        parsed[0]["task"] = "other"
        self.assertEqual(entries[0]["task"], "OpenDrawer")
        self.assertEqual(session.ANONYMOUS_LABELS, ("K", "R", "T", "V", "W", "Z"))
        self.assertEqual(session.DEFAULT_EXPERIENCE_LIMIT, 24)

    def test_rejects_bad_shape_seeds_labels_tasks_and_hash(self):
        cases = [None, {}, [], [dict(plan(), extra=True)],
                 [dict(plan(), scene_seed=True)], [dict(plan(), policy_seed=-1)],
                 [dict(plan(), scene_seed=2**32)], [dict(plan(), policy_seed=1.0)],
                 [dict(plan(), task="Missing")], [dict(plan(), policy_label="groot")],
                 [dict(plan(), backend="")], [dict(plan(), expect_state="A" * 64)]]
        for entries in cases:
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                session.validate_plan(entries, {"OpenDrawer"}, WORKERS)
        session.validate_plan([dict(plan(), expect_state="a" * 64)], {"OpenDrawer"}, WORKERS)

    def test_bijection_and_exact_distinct_loopback_workers(self):
        entries = [plan(), plan("R", "pi05")]
        good = dict(WORKERS, R="http://localhost:8001")
        session.validate_plan(entries, {"OpenDrawer"}, good)
        bad_workers = [{}, dict(good, T="http://localhost:8002"),
                       dict(good, R=WORKERS["K"]), dict(good, R="https://localhost:8001"),
                       dict(good, R="http://user:pass@localhost:8001"),
                       dict(good, R="http://example.com:8001"),
                       dict(good, R="http://localhost:8001/path"),
                       dict(good, R="http://localhost:8001?token=secret")]
        for workers in bad_workers:
            with self.subTest(workers=workers), self.assertRaises(ValueError):
                session.validate_plan(entries, {"OpenDrawer"}, workers)
        for entries in ([plan(), plan("K", "pi05")], [plan(), plan("R", "groot")]):
            with self.assertRaises(ValueError):
                session.validate_plan(entries, {"OpenDrawer"}, good)


class TimeTests(unittest.TestCase):
    def config(self):
        return {"call_seconds": {"model": 4.7}, "value": "UNTRUSTED evaluator",
                "tasks": {"OpenDrawer": {"deadline_seconds": 30, "clock_starts": "hidden",
                          "story": {"text": "The food cools.", "limit_seconds": 20,
                                    "clock_starts": "private_predicate", "reward": 5}}}}

    def test_project_model_charge_story_and_fixed_score_only(self):
        context = session.public_time_context(self.config(), "model", "OpenDrawer")
        self.assertEqual(context, dict(TIME, story={"text": "The food cools.", "limit_seconds": 20.0}))
        self.assertNotIn("private_predicate", json.dumps(context))
        config = self.config()
        config["tasks"]["OpenDrawer"]["story"]["limit_seconds"] = None
        self.assertIsNone(session.public_time_context(config, "model", "OpenDrawer")["story"]["limit_seconds"])

    def test_missing_models_tasks_and_invalid_numbers_are_errors(self):
        for model, task in (("missing", "OpenDrawer"), ("model", "missing")):
            with self.assertRaises(ValueError):
                session.public_time_context(self.config(), model, task)
        for field, values in (("charge", [-1, True, float("nan"), float("inf"), None]),
                              ("deadline", [0, -1, True, float("inf")]),
                              ("limit", [0, -1, True, float("nan")])):
            for value in values:
                config = self.config()
                if field == "charge":
                    config["call_seconds"]["model"] = value
                elif field == "deadline":
                    config["tasks"]["OpenDrawer"]["deadline_seconds"] = value
                else:
                    config["tasks"]["OpenDrawer"]["story"]["limit_seconds"] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    session.public_time_context(config, "model", "OpenDrawer")


class ExperienceTests(unittest.TestCase):
    def test_projects_only_accepted_decisions_and_terminal_public_outcome(self):
        public = session.project_experience("K", result(), DECISIONS)
        self.assertEqual(public, {"policy": "K", "goal": "Open the drawer.",
                                 "decisions": [dict(DECISIONS[0]["decision"], step_before=0),
                                               {"op": "complete", "step_before": 20}],
                                 "outcome": {"success": True, "steps": 20, "model_calls": 2,
                                             "declaration_correct": True}})
        for private in ("reward", "scene_seed", "object_coordinates", "accepted"):
            self.assertNotIn(private, json.dumps(public))
        self.assertFalse(session.project_experience("K", result("false_completion"), DECISIONS)["outcome"]["declaration_correct"])
        self.assertIsNone(session.project_experience("K", result("step_budget_exhausted"), DECISIONS[:-1])["outcome"]["declaration_correct"])

    def test_running_unknown_and_infrastructure_are_not_experience(self):
        for status in ("running", "not_started", "infrastructure_error", "start_state_mismatch", "unknown"):
            self.assertIsNone(session.project_experience("K", result(status), DECISIONS))
        broken = dict(result(), infrastructure_error="crash")
        self.assertIsNone(session.project_experience("K", broken, DECISIONS))

    def test_invalid_accepted_decisions_are_omitted_and_outcome_is_validated(self):
        malformed = [{"accepted": True, "step_before": 0, "decision": {"op": "run_policy", "steps": True}},
                     {"accepted": True, "step_before": 0, "decision": {"op": "complete", "reward": 3}},
                     {"accepted": True, "step_before": -1, "decision": {"op": "complete"}}]
        self.assertEqual(session.project_experience("K", result(), malformed)["decisions"], [])
        for change in ({"steps": True}, {"success": "yes"}, {"goal": ""}, {"model_calls": -1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                session.project_experience("K", dict(result(), **change), DECISIONS)

    def test_wrapper_copies_sanitizes_caps_and_proxies(self):
        agent = Agent()
        experience = [dict(session.project_experience("K", result(), DECISIONS), reward=999) for _ in range(3)]
        experience[-1]["decisions"][0]["backend"] = "hidden"
        wrapper = session.SessionAgent(agent, "R", experience, TIME, experience_limit=2)
        observation = {"goal": "Open it.", "history": []}
        self.assertEqual(wrapper.decide(observation).decision, {"op": "complete"})
        self.assertEqual(agent.observation["policy"], "R")
        self.assertEqual(len(agent.observation["experience"]), 2)
        self.assertNotIn("reward", json.dumps(agent.observation))
        self.assertNotIn("hidden", json.dumps(agent.observation))
        agent.observation["history"].append("mutation")
        self.assertEqual(observation["history"], [])
        self.assertEqual(wrapper.identity, agent.identity)
        self.assertEqual(wrapper.last_trace, agent.last_trace)
        wrapper.decide(observation)
        self.assertEqual(len(agent.observation["experience"]), 2)
        for limit in (0, -1, True, 25):
            with self.assertRaises(ValueError):
                session.SessionAgent(agent, "K", [], TIME, experience_limit=limit)


class AdapterIntegrationTests(unittest.TestCase):
    def test_projected_experience_builds_real_version6_payload_without_network(self):
        agent = HTTPAgent({"provider": "anthropic", "model": "model",
                           "endpoint": "https://api.anthropic.com/v1/messages"}, session_mode=True)
        record = session.project_experience("K", result(), DECISIONS)
        record["outcome"]["reward"] = 777
        wrapper = session.SessionAgent(agent, "R", [record], TIME)
        captured = []
        # A payload-building adapter exercises the actual boundary without calling a provider.
        class PayloadAgent:
            identity = agent.identity
            last_trace = None
            def decide(self, observation):
                captured.append(agent.build_payload(observation))
                return ModelReply({"op": "complete"})
        wrapper.agent = PayloadAgent()
        wrapper.decide({"images": {camera: PNG_URL for camera in CAMERAS}, "goal": "Open the drawer."})
        payload = captured[0]
        content = payload["messages"][0]["content"]
        self.assertEqual(json.loads(content[0]["text"]), session.project_experience("K", result(), DECISIONS))
        self.assertEqual(content[0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(json.loads(content[-1]["text"])["policy"], "R")
        self.assertNotIn("reward", json.dumps(payload))
        self.assertEqual(agent.identity["prompt_version"], 6)
        self.assertEqual(session.SCORE, SESSION_SCORE)


class SessionTests(unittest.TestCase):
    def run_args(self, output, callback, entries=None):
        return {"output": output, "session_id": "one", "plan": entries or [plan(), plan(seed=1)],
                "workers": WORKERS, "task_names": {"OpenDrawer"}, "agent": Agent(), "run_entry": callback,
                "session_contract": {"time_pressure": {"OpenDrawer": TIME}, "code_hash": "a" * 64}}

    def test_order_reserved_index_public_experience_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            seen = []
            def run(entry, agent, episode_output, index):
                rows = [json.loads(line) for line in (Path(tmp) / "sessions/one/session.jsonl").read_text().splitlines()]
                self.assertEqual(rows[-1]["index"], index)
                self.assertEqual(Path(tmp) / "sessions/one" / rows[-1]["episode_dir"], episode_output)
                self.assertFalse(episode_output.exists())
                agent.decide({"goal": "Open the drawer."})
                seen.append((entry["scene_seed"], copy.deepcopy(agent.agent.observation)))
                episode_output.mkdir(parents=True)
                (episode_output / "result.json").write_text(json.dumps(result()))
                return episode_output, result(), DECISIONS
            rows = session.run_session(**self.run_args(tmp, run))
            self.assertEqual([seed for seed, _ in seen], [0, 1])
            self.assertEqual([len(obs["experience"]) for _, obs in seen], [0, 1])
            self.assertEqual(set(rows[0]), {"session_id", "index", "policy_label", "backend", "task", "scene_seed", "policy_seed", "episode_dir"})
            manifest = json.loads((Path(tmp) / "sessions/one/manifest.json").read_text())
            self.assertEqual(len(manifest["plan_hash"]), 64)
            self.assertEqual(len(manifest["contract_hash"]), 64)
            for contract in ({}, {"code_hash": "b" * 64}):
                args = self.run_args(tmp, run)
                args["session_contract"] = contract
                with self.assertRaises(FileExistsError):
                    session.run_session(**args)
            self.assertEqual(len(seen), 2)

    def test_raised_attempts_preserved_stop_consecutive_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fail(entry, agent, episode_output, index):
                raise ConnectionError("worker unreachable")
            entries = [plan(seed=i) for i in range(4)]
            rows = session.run_session(**self.run_args(tmp, fail, entries))
            self.assertEqual(len(rows), 2)
            for row in rows:
                retained = json.loads((Path(tmp) / "sessions/one" / row["episode_dir"] / "result.json").read_text())
                self.assertEqual(retained["status"], "infrastructure_error")
                self.assertIs(retained["success"], False)
            errors = (Path(tmp) / "sessions/one/errors.jsonl").read_text().splitlines()
            self.assertEqual(len(errors), 2)
            state = json.loads((Path(tmp) / "sessions/one/session_result.json").read_text())
            self.assertEqual(state["status"], "infrastructure_error")

    def test_budget_stop_retains_attempt_and_does_not_start_another_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            def stopped(entry, agent, episode_output, index):
                episode_output.mkdir(parents=True)
                retained = {**result("false_completion"), "session_stop": "api_spend_limit"}
                (episode_output / "result.json").write_text(json.dumps(retained))
                return episode_output, retained, DECISIONS
            rows = session.run_session(**self.run_args(tmp, stopped))
            self.assertEqual(len(rows), 1)
            outcome = json.loads((Path(tmp) / "sessions/one/session_result.json").read_text())
            self.assertEqual(outcome["status"], "api_spend_limit")
            self.assertEqual(outcome["attempted_episodes"], 1)

    def test_early_setup_error_has_conventional_manifest_and_result_for_w1_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fail(*args):
                raise ConnectionError("worker unavailable before runner setup")
            args = self.run_args(tmp, fail)
            args["session_contract"].update({
                "kind": "llm_development", "policy_identities": {"K": {"backend": "groot", "checkpoint": "pinned"}},
                "episode_contract_hashes": {"K": "b" * 64},
                "task_configs": {"OpenDrawer": {"task": "OpenDrawer", "split": "pretrain"}},
            })
            rows = session.run_session(**args)
            episode = Path(tmp) / "sessions/one" / rows[0]["episode_dir"]
            manifest = json.loads((episode / "manifest.json").read_text())
            outcome = json.loads((episode / "result.json").read_text())
            self.assertEqual(manifest["artifact_type"], "episode")
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["task"], "OpenDrawer")
            self.assertEqual(manifest["split"], "pretrain")
            self.assertEqual(manifest["kind"], "llm_development")
            self.assertEqual(manifest["policy"], {"backend": "groot", "checkpoint": "pinned"})
            self.assertEqual(manifest["agent"], args["agent"].identity)
            self.assertEqual(manifest["contract_hash"], "b" * 64)
            self.assertEqual(manifest["policy_label"], "K")
            self.assertEqual(manifest["session_id"], "one")
            self.assertEqual(manifest["scene_seed"], 0)
            self.assertEqual(manifest["policy_seed"], 0)
            self.assertEqual(outcome["status"], "infrastructure_error")
            self.assertIs(outcome["success"], False)
            self.assertIsNone(outcome["goal"])
            self.assertEqual(outcome["steps"], 0)
            self.assertEqual(outcome["model_calls"], 0)
            self.assertEqual(outcome["simulated_seconds"], 0)
            self.assertEqual(outcome["usage"], [])
            self.assertEqual(outcome["scene_seed"], 0)
            self.assertEqual(outcome["policy_seed"], 0)
            self.assertIn("ConnectionError: worker unavailable", outcome["infrastructure_error"])

    def test_early_setup_error_uses_unavailable_identity_without_inventing_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fail(*args):
                raise ConnectionError("setup unavailable")
            rows = session.run_session(**self.run_args(tmp, fail))
            episode = Path(tmp) / "sessions/one" / rows[0]["episode_dir"]
            manifest = json.loads((episode / "manifest.json").read_text())
            self.assertEqual(manifest["policy"], {"backend": "groot", "status": "setup_unavailable"})
            self.assertIsNone(manifest["contract_hash"])
            self.assertEqual(manifest["split"], "pretrain")

    def test_infrastructure_is_excluded_success_resets_streak(self):
        with tempfile.TemporaryDirectory() as tmp:
            lengths = []
            def run(entry, agent, episode_output, index):
                agent.decide({})
                lengths.append(len(agent.agent.observation["experience"]))
                episode_output.mkdir(parents=True)
                value = result("infrastructure_error" if index in (0, 2) else "success")
                (episode_output / "result.json").write_text(json.dumps(value))
                return episode_output, value, DECISIONS
            rows = session.run_session(**self.run_args(tmp, run, [plan(seed=i) for i in range(4)]))
            self.assertEqual(len(rows), 4)
            self.assertEqual(lengths, [0, 0, 1, 1])

    def test_keyboard_interrupt_keeps_partial_and_stops_visibly(self):
        with tempfile.TemporaryDirectory() as tmp:
            def interrupt(entry, agent, episode_output, index):
                episode_output.mkdir(parents=True)
                (episode_output / "partial.txt").write_text("evidence")
                raise KeyboardInterrupt()
            with self.assertRaises(KeyboardInterrupt):
                session.run_session(**self.run_args(tmp, interrupt))
            root = Path(tmp) / "sessions/one"
            rows = [json.loads(line) for line in (root / "session.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            episode = root / rows[0]["episode_dir"]
            self.assertEqual((episode / "partial.txt").read_text(), "evidence")
            self.assertEqual(json.loads((episode / "result.json").read_text())["status"], "infrastructure_error")
            self.assertEqual(json.loads((root / "session_result.json").read_text())["status"], "interrupted")

    def test_interrupt_preserves_existing_runner_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            retained = {"status": "infrastructure_error", "steps": 13,
                        "infrastructure_error": "KeyboardInterrupt", "interrupted": True}
            def interrupt(entry, agent, episode_output, index):
                episode_output.mkdir(parents=True)
                (episode_output / "result.json").write_text(json.dumps(retained))
                (episode_output / "manifest.json").write_text(json.dumps({"existing": "keep me"}))
                raise SystemExit(9)
            with self.assertRaises(SystemExit) as raised:
                session.run_session(**self.run_args(tmp, interrupt))
            self.assertEqual(raised.exception.code, 9)
            self.assertEqual(json.loads((Path(tmp) / "sessions/one/episodes/0000/manifest.json").read_text()), {"existing": "keep me"})
            self.assertEqual(json.loads((Path(tmp) / "sessions/one/episodes/0000/result.json").read_text()), retained)

    def test_returned_interruption_stops_before_next_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            def interrupt(entry, agent, episode_output, index):
                episode_output.mkdir(parents=True)
                value = dict(result("infrastructure_error"), interrupted=True)
                (episode_output / "result.json").write_text(json.dumps(value))
                return episode_output, value, []
            with self.assertRaises(KeyboardInterrupt):
                session.run_session(**self.run_args(tmp, interrupt))
            self.assertFalse((Path(tmp) / "sessions/one/episodes/0001").exists())

    def test_experience_limit_cannot_exceed_adapter_capacity_before_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.run_args(tmp, lambda *args: self.fail("must not call"))
            args["experience_limit"] = 25
            with self.assertRaises(ValueError):
                session.run_session(**args)
            self.assertFalse((Path(tmp) / "sessions").exists())

    def test_rejects_escaping_id_before_files_or_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.run_args(tmp, lambda *args: self.fail("must not call"))
            args["session_id"] = "../escape"
            with self.assertRaises(ValueError):
                session.run_session(**args)
            self.assertFalse((Path(tmp) / "sessions").exists())


class BaselinePairingTests(unittest.TestCase):
    def baseline(self, root, name="baseline", state="a" * 64, status="false_completion", backend="groot"):
        folder = root / name
        (folder / "evaluator").mkdir(parents=True)
        (folder / "manifest.json").write_text(json.dumps({"artifact_type": "episode", "task": "OpenDrawer",
            "kind": "baseline_always_defer", "scene_seed": 0, "policy_seed": 0,
            "policy": {"backend": backend}, "contract_hash": "code-contract"}))
        (folder / "result.json").write_text(json.dumps({"status": status, "success": False,
                                                       "scene_seed": 0, "policy_seed": 0}))
        (folder / "evaluator/states.jsonl").write_text(json.dumps({"step": 0, "state_sha256": state}) + "\n")
        return folder

    def test_pairing_uses_failed_baseline_without_outcome_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.baseline(root)
            paired, audit = session.attach_baseline_states([plan()], root, {"OpenDrawer"})
            self.assertEqual(paired[0]["expect_state"], "a" * 64)
            self.assertNotIn("expect_state", plan())
            self.assertEqual(audit[0]["baseline_episode"], str(baseline.resolve()))

    def test_infrastructure_and_wrong_backend_cannot_supply_a_twin(self):
        for status, backend in (("infrastructure_error", "groot"), ("false_completion", "pi05")):
            with self.subTest(status=status, backend=backend), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.baseline(root, status=status, backend=backend)
                with self.assertRaisesRegex(ValueError, "no usable"):
                    session.attach_baseline_states([plan()], root, {"OpenDrawer"})

    def test_duplicate_baselines_and_conflicting_existing_hash_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.baseline(root)
            with self.assertRaisesRegex(ValueError, "conflicts"):
                session.attach_baseline_states([dict(plan(), expect_state="b" * 64)], root, {"OpenDrawer"})
            self.baseline(root, name="duplicate")
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                session.attach_baseline_states([plan()], root, {"OpenDrawer"})

    def test_missing_or_invalid_step_zero_hash_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = self.baseline(root, state="invalid")
            with self.assertRaisesRegex(ValueError, "step-0"):
                session.attach_baseline_states([plan()], root, {"OpenDrawer"})
            (folder / "evaluator/states.jsonl").write_text(json.dumps({"step": 1, "state_sha256": "a" * 64}) + "\n")
            with self.assertRaisesRegex(ValueError, "step-0"):
                session.attach_baseline_states([plan()], root, {"OpenDrawer"})


if __name__ == "__main__":
    unittest.main()
