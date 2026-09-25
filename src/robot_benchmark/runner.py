"""Synchronous physics with interruptible learned-policy execution."""
from collections import deque
from dataclasses import asdict
from time import perf_counter
import copy

from .contracts import Limits, ModelReply, sensor_payload, validate_action, validate_decision


class Runner:
    def __init__(self, env, policy, agent, skills, goal, limits: Limits, records=None, recording_interval=2):
        self.env, self.policy, self.agent = env, policy, agent
        self.skills = {skill.id: skill for skill in skills}
        if len(self.skills) != len(skills) or not skills or any(not isinstance(s.id, str) or not s.id for s in skills):
            raise ValueError("skill IDs must be nonempty and unique")
        self.goal, self.limits, self.records = goal, limits, records
        if type(recording_interval) is not int or recording_interval < 1:
            raise ValueError("recording interval must be a positive integer")
        self.recording_interval = recording_interval
        self.steps = self.decisions = self.policy_calls = 0
        self.active = self.last_skill = None
        self.queue = deque()
        self.history = []
        self.usage = []
        self.physical_any = False
        self.last_physical = None
        self.last_error = None
        self.status = "not_started"
        self.model_seconds = self.policy_seconds = 0.0

    def _record(self, name, value):
        if self.records:
            self.records.append(name, value)

    def _evaluate(self):
        truth = self.env.evaluate()
        if type(truth.get("success")) is not bool:
            raise ValueError("evaluator must return a boolean success")
        self.last_physical = truth["success"]
        self.physical_any |= self.last_physical
        self._record("evaluator/events.jsonl", {"step": self.steps, **truth})

    def observation(self):
        return {
            "schema_version": 1,
            "goal": self.goal,
            **sensor_payload(self.env.sensors()),
            "skills": [s.public() for s in self.skills.values()],
            "active_skill": self.active,
            "last_skill": self.last_skill,
            "step": self.steps,
            "remaining_steps": self.limits.max_steps - self.steps,
            "remaining_decisions": self.limits.max_decisions - self.decisions,
            "max_interval": self.limits.max_interval,
            "history": copy.deepcopy(self.history),
            "last_error": self.last_error,
        }

    def _validate_state(self, decision):
        op = decision["op"]
        if op == "start" and self.active is not None:
            raise ValueError("start requires no active skill; use switch")
        if op in ("continue", "interrupt", "switch") and self.active is None:
            raise ValueError(f"{op} requires an active skill")
        if op == "switch" and decision["skill"] == self.active:
            raise ValueError("switch requires a different skill; use retry or continue")
        if op == "retry" and self.last_skill is None:
            raise ValueError("retry requires a previously selected skill")
        if decision.get("steps", 0) > self.limits.max_steps - self.steps:
            raise ValueError("requested interval exceeds remaining steps")

    def apply(self, decision):
        """Validate fully before mutation; physics only advances here."""
        decision = validate_decision(decision, self.skills, self.limits)
        self._validate_state(decision)
        op = decision["op"]
        if op == "complete":
            self._evaluate()
            self.status = "success" if self.last_physical else "false_completion"
            return
        if op in ("start", "switch", "retry", "interrupt"):
            self.queue.clear()
            self.policy.reset_skill()
            if op == "interrupt":
                self.active = None
                return
            self.active = self.last_skill = decision.get("skill", self.last_skill)
        for _ in range(decision["steps"]):
            if not self.queue:
                start = perf_counter()
                self.policy_calls += 1
                self._record("policy_requests.jsonl", {
                    "policy_call": self.policy_calls,
                    "step": self.steps,
                    "skill": self.active,
                    "instruction": self.skills[self.active].instruction,
                })
                try:
                    chunk = self.policy.predict(self.env.policy_observation(), self.skills[self.active].instruction)
                finally:
                    self.policy_seconds += perf_counter() - start
                if not isinstance(chunk, list) or not chunk:
                    raise RuntimeError("policy returned an empty or invalid action chunk")
                self.queue.extend(validate_action(action) for action in chunk)
                self._record("policy_calls.jsonl", {"policy_call": self.policy_calls,
                    "step": self.steps, "skill": self.active, "actions": list(self.queue)})
            action = self.queue.popleft()
            # Record an attempted step before calling physics; a failure may leave
            # simulator state uncertain and must never be retried automatically.
            self._record("action_attempts.jsonl", {"step": self.steps + 1, "action": action})
            self.env.step(action)
            self.steps += 1
            self._record("actions.jsonl", {"step": self.steps, "skill": self.active, "action": action})
            if self.records and hasattr(self.records, "video_frame") and self.steps % self.recording_interval == 0:
                self.records.video_frame(self.steps, self.env.recording_frame())
            self._evaluate()
            self._record("evaluator/states.jsonl", {"step": self.steps, **self.env.snapshot()})

    def run(self, seed):
        if self.status != "not_started":
            raise RuntimeError("Runner instances execute exactly one episode")
        start = perf_counter()
        infrastructure_error = None
        self.status = "running"
        try:
            self.env.reset(seed)
            self.policy.reset_episode(seed)
            if self.records and hasattr(self.records, "video_frame"):
                self.records.video_frame(0, self.env.recording_frame())
            self._record("evaluator/states.jsonl", {"step": 0, **self.env.snapshot()})
            self._evaluate()
            while self.status == "running":
                if self.steps >= self.limits.max_steps:
                    self.status = "step_budget_exhausted"
                    break
                if self.decisions >= self.limits.max_decisions:
                    self.status = "decision_budget_exhausted"
                    break
                observation = self.observation()
                if self.records:
                    self.records.observation(self.decisions, observation)
                self.decisions += 1  # malformed outputs and transport failures count
                tick = perf_counter()
                try:
                    reply = self.agent.decide(observation)
                finally:
                    self.model_seconds += perf_counter() - tick
                if not isinstance(reply, ModelReply):
                    raise TypeError("agent adapter must return ModelReply")
                self.usage.append(reply.usage)
                self._record("model_replies.jsonl", {"decision_index": self.decisions, **asdict(reply)})
                entry = {"decision_index": self.decisions, "step_before": self.steps}
                self.last_error = None
                # Catch agent validation errors separately from executor failures.
                try:
                    decision = validate_decision(reply.decision, self.skills, self.limits)
                    self._validate_state(decision)
                except ValueError as error:
                    self.last_error = str(error)
                    entry.update({"decision": reply.decision, "accepted": False, "error": self.last_error})
                else:
                    entry.update({"decision": decision, "accepted": True})
                    self._record("decision_attempts.jsonl", entry)
                    self.apply(decision)
                entry["step_after"] = self.steps
                self.history.append(entry)
                self._record("decisions.jsonl", entry)
        except Exception as error:
            self.status = "infrastructure_error"
            infrastructure_error = f"{type(error).__name__}: {error}"
            self._record("evaluator/errors.jsonl", {"error": infrastructure_error, "step": self.steps})
        finally:
            try:
                self.env.close()
            except Exception as error:
                self.status = "infrastructure_error"
                infrastructure_error = f"close failed: {type(error).__name__}: {error}"
        ops = [e["decision"]["op"] for e in self.history if e["accepted"]]
        result = {
            "status": self.status,
            "success": self.status == "success",
            "physical_success_final": self.last_physical,
            "physical_success_any": self.physical_any,
            "false_completion": self.status == "false_completion",
            "steps": self.steps, "model_calls": self.decisions, "policy_calls": self.policy_calls,
            "switches": ops.count("switch"), "retries": ops.count("retry"), "interrupts": ops.count("interrupt"),
            "intervals": [e["decision"]["steps"] for e in self.history if e["accepted"] and "steps" in e["decision"]],
            "model_seconds": self.model_seconds, "policy_seconds": self.policy_seconds,
            "wall_seconds": perf_counter() - start, "usage": self.usage,
            "infrastructure_error": infrastructure_error,
        }
        if self.records:
            self.records.write("result.json", result)
        return result
