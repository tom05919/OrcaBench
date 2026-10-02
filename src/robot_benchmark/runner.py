"""Synchronous physics with interruptible learned-policy execution."""
from collections import deque
from dataclasses import asdict
from time import perf_counter, time_ns
import copy

from .contracts import Limits, ModelReply, sensor_payload, validate_action, validate_decision


class Runner:
    def __init__(self, env, policy, agent, reference_prompts, goal, limits: Limits, records=None, recording_interval=1,
                 interval_keyframes=0):
        self.env, self.policy, self.agent = env, policy, agent
        self.reference_prompts = {item.id: item for item in reference_prompts}
        if len(self.reference_prompts) != len(reference_prompts) or not reference_prompts or any(
            not isinstance(item.id, str) or not item.id for item in reference_prompts
        ):
            raise ValueError("reference prompt IDs must be nonempty and unique")
        self.goal, self.limits, self.records = goal, limits, records
        if type(recording_interval) is not int or recording_interval < 1:
            raise ValueError("recording interval must be a positive integer")
        self.recording_interval = recording_interval
        if type(interval_keyframes) is not int or interval_keyframes < 0:
            raise ValueError("interval keyframe count must be a nonnegative integer")
        self.interval_keyframes = interval_keyframes
        self.interval_frames = []
        self.steps = self.decisions = self.policy_calls = 0
        self.active_instruction = None
        self.queue = deque()
        self.prompt_submissions = self.prompt_changes = self.prompt_restarts = self.discarded_actions = 0
        self.history = []
        self.usage = []
        self.reply_parse = {}
        self.physical_any = False
        self.last_physical = None
        self.last_error = None
        self.status = "not_started"
        self._episode_start = perf_counter()
        self.model_seconds = self.policy_seconds = self.simulation_seconds = 0.0
        self.simulated_seconds = 0.0
        self.recording_seconds = self.evaluation_seconds = 0.0

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

    def _public_card(self, item):
        # A card whose prompt is exactly "{goal}" shows the already-public goal text.
        card = item.public()
        if card["prompt"] == "{goal}":
            card["prompt"] = self.goal
        return card

    def observation(self):
        return {
            "schema_version": 4,
            "goal": self.goal,
            **sensor_payload(self.env.sensors()),
            "interval_frames": copy.deepcopy(self.interval_frames),
            "reference_prompts": [self._public_card(item) for item in self.reference_prompts.values()],
            "active_instruction": self.active_instruction,
            "step": self.steps,
            "remaining_steps": self.limits.max_steps - self.steps,
            "remaining_decisions": self.limits.max_decisions - self.decisions,
            "max_interval": self.limits.max_interval,
            "history": copy.deepcopy(self.history),
            "last_error": self.last_error,
        }

    def _validate_state(self, decision):
        if decision["op"] == "run_policy" and "prompt" not in decision and self.active_instruction is None:
            raise ValueError("run_policy requires a prompt when no instruction is active")
        if decision.get("steps", 0) > self.limits.max_steps - self.steps:
            raise ValueError("requested interval exceeds remaining steps")

    def apply(self, decision):
        """Validate fully before mutation; physics only advances here."""
        decision = validate_decision(decision, self.limits)
        self._validate_state(decision)
        op = decision["op"]
        if op == "complete":
            self._evaluate()
            self.status = "success" if self.last_physical else "false_completion"
            return
        if "prompt" in decision:
            prior = self.active_instruction
            discarded = len(self.queue)
            self.prompt_submissions += 1
            if prior is not None:
                if decision["prompt"] == prior:
                    self.prompt_restarts += 1
                else:
                    self.prompt_changes += 1
            self.discarded_actions += discarded
            self.queue.clear()
            self.policy.reset_skill()
            self.active_instruction = decision["prompt"]
            self._record("policy_transitions.jsonl", {
                "step": self.steps,
                "previous_instruction": prior,
                "instruction": self.active_instruction,
                "discarded_actions": discarded,
            })
        # Evenly spaced frames strictly inside the interval; the next observation
        # already shows its final step.
        start, count, k = self.steps, decision["steps"], self.interval_keyframes
        keyframe_steps = {start + count * i // (k + 1) for i in range(1, k + 1)} - {start, start + count}
        for _ in range(decision["steps"]):
            step_start = perf_counter()
            started_at_unix_ns = time_ns()
            sim_time_before = self.env.sim_time_seconds()
            policy_wait_seconds = 0.0
            if not self.queue:
                start = perf_counter()
                policy_started_at_unix_ns = time_ns()
                self.policy_calls += 1
                self._record("policy_requests.jsonl", {
                    "policy_call": self.policy_calls,
                    "step": self.steps,
                    "instruction": self.active_instruction,
                })
                try:
                    chunk = self.policy.predict(self.env.policy_observation(), self.active_instruction)
                finally:
                    policy_wait_seconds = perf_counter() - start
                    self.policy_seconds += policy_wait_seconds
                    self._record("policy_timings.jsonl", {"policy_call": self.policy_calls,
                        "step_before": self.steps, "started_at_unix_ns": policy_started_at_unix_ns,
                        "episode_elapsed_seconds": perf_counter() - self._episode_start,
                        "wall_seconds": policy_wait_seconds})
                if not isinstance(chunk, list) or not chunk:
                    raise RuntimeError("policy returned an empty or invalid action chunk")
                self.queue.extend(validate_action(action) for action in chunk)
                self._record("policy_calls.jsonl", {"policy_call": self.policy_calls,
                    "step": self.steps, "instruction": self.active_instruction, "actions": list(self.queue)})
            action = self.queue.popleft()
            # Record an attempted step before calling physics; a failure may leave
            # simulator state uncertain and must never be retried automatically.
            self._record("action_attempts.jsonl", {"step": self.steps + 1, "action": action})
            physics_start = perf_counter()
            try:
                self.env.step(action)
            except Exception:
                physics_seconds = perf_counter() - physics_start
                self.simulation_seconds += physics_seconds
                self._record("step_timings.jsonl", {"attempted_step": self.steps + 1,
                    "started_at_unix_ns": started_at_unix_ns, "status": "step_error",
                    "physics_seconds": physics_seconds, "policy_wait_seconds": policy_wait_seconds,
                    "sim_time_before": sim_time_before,
                    "episode_elapsed_seconds": perf_counter() - self._episode_start,
                    "wall_seconds": perf_counter() - step_start})
                raise
            physics_seconds = perf_counter() - physics_start
            self.simulation_seconds += physics_seconds
            sim_time_after = self.env.sim_time_seconds()
            self.simulated_seconds += sim_time_after - sim_time_before
            self.steps += 1
            self._record("actions.jsonl", {"step": self.steps, "instruction": self.active_instruction, "action": action})
            recording_start = perf_counter()
            recording_seconds = evaluation_seconds = 0.0
            try:
                if self.records and hasattr(self.records, "video_frames") and self.steps % self.recording_interval == 0:
                    self.records.video_frames(self.steps, self.env.recording_frames())
                recording_seconds = perf_counter() - recording_start
                self.recording_seconds += recording_seconds
                evaluation_start = perf_counter()
                try:
                    self._evaluate()
                    self._record("evaluator/states.jsonl", {"step": self.steps, **self.env.snapshot()})
                finally:
                    evaluation_seconds = perf_counter() - evaluation_start
                    self.evaluation_seconds += evaluation_seconds
            except Exception:
                self._record("step_timings.jsonl", {"step": self.steps,
                    "started_at_unix_ns": started_at_unix_ns, "status": "post_step_error",
                    "physics_seconds": physics_seconds, "policy_wait_seconds": policy_wait_seconds,
                    "recording_seconds": perf_counter() - recording_start if not recording_seconds else recording_seconds,
                    "evaluation_seconds": evaluation_seconds,
                    "sim_time_before": sim_time_before, "sim_time_after": sim_time_after,
                    "sim_step_seconds": sim_time_after - sim_time_before,
                    "episode_elapsed_seconds": perf_counter() - self._episode_start,
                    "wall_seconds": perf_counter() - step_start})
                raise
            self._record("step_timings.jsonl", {"step": self.steps,
                "started_at_unix_ns": started_at_unix_ns, "status": "ok",
                "physics_seconds": physics_seconds, "policy_wait_seconds": policy_wait_seconds,
                "recording_seconds": recording_seconds, "evaluation_seconds": evaluation_seconds,
                "sim_time_before": sim_time_before, "sim_time_after": sim_time_after,
                "sim_step_seconds": sim_time_after - sim_time_before,
                "episode_elapsed_seconds": perf_counter() - self._episode_start,
                "wall_seconds": perf_counter() - step_start})
            if self.steps in keyframe_steps:
                sensed = sensor_payload(self.env.sensors())
                self.interval_frames.append({"step": self.steps, "images": sensed["images"],
                                             "proprio": sensed["proprio"]})

    def run(self, seed, policy_seed=None):
        """Scene seed resets the simulator; policy seed (default: scene seed) resets the policy."""
        policy_seed = seed if policy_seed is None else policy_seed
        if self.status != "not_started":
            raise RuntimeError("Runner instances execute exactly one episode")
        start = perf_counter()
        self._episode_start = start
        episode_started_at_unix_ns = time_ns()
        infrastructure_error = None
        self.status = "running"
        try:
            self.env.reset(seed)
            if self.goal is None:
                goal = self.env.native_instruction()
                if not isinstance(goal, str) or not goal.strip():
                    raise ValueError("native instruction must be nonblank text")
                self.goal = goal
            self.policy.reset_episode(policy_seed)
            if self.records and hasattr(self.records, "video_frames"):
                self.records.video_frames(0, self.env.recording_frames())
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
                started_at_unix_ns = time_ns()
                try:
                    reply = self.agent.decide(observation)
                finally:
                    model_seconds = perf_counter() - tick
                    self.model_seconds += model_seconds
                    self._record("model_timings.jsonl", {"decision_index": self.decisions,
                        "started_at_unix_ns": started_at_unix_ns,
                        "episode_elapsed_seconds": perf_counter() - self._episode_start,
                        "wall_seconds": model_seconds})
                    api_trace = getattr(self.agent, "last_trace", None)
                    if api_trace is not None:
                        self._record("model_api_traces.jsonl", {"decision_index": self.decisions, **api_trace})
                if not isinstance(reply, ModelReply):
                    raise TypeError("agent adapter must return ModelReply")
                self.usage.append(reply.usage)
                if reply.parse is not None:
                    self.reply_parse[reply.parse] = self.reply_parse.get(reply.parse, 0) + 1
                self._record("model_replies.jsonl", {"decision_index": self.decisions, **asdict(reply)})
                entry = {"decision_index": self.decisions, "step_before": self.steps}
                self.last_error = None
                self.interval_frames = []
                # Catch agent validation errors separately from executor failures.
                try:
                    decision = validate_decision(reply.decision, self.limits)
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
            # Keep the final state in the replay when it falls between recording steps.
            if self.records and hasattr(self.records, "video_frames") and self.steps % self.recording_interval:
                self.records.video_frames(self.steps, self.env.recording_frames())
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
        result = {
            "started_at_unix_ns": episode_started_at_unix_ns,
            "ended_at_unix_ns": time_ns(),
            "status": self.status,
            "goal": self.goal, "scene_seed": seed, "policy_seed": policy_seed,
            "success": self.status == "success",
            "physical_success_final": self.last_physical,
            "physical_success_any": self.physical_any,
            "false_completion": self.status == "false_completion",
            "steps": self.steps, "model_calls": self.decisions, "policy_calls": self.policy_calls,
            "prompt_submissions": self.prompt_submissions,
            "prompt_changes": self.prompt_changes,
            "prompt_restarts": self.prompt_restarts,
            "discarded_actions": self.discarded_actions,
            "rejected_decisions": sum(not entry["accepted"] for entry in self.history),
            "reply_parse": self.reply_parse,
            "intervals": [e["decision"]["steps"] for e in self.history if e["accepted"] and "steps" in e["decision"]],
            "model_seconds": self.model_seconds, "policy_seconds": self.policy_seconds,
            "simulation_seconds": self.simulation_seconds,
            "simulated_seconds": self.simulated_seconds,
            "recording_seconds": self.recording_seconds,
            "evaluation_seconds": self.evaluation_seconds,
            "wall_seconds": perf_counter() - start, "usage": self.usage,
            "infrastructure_error": infrastructure_error,
        }
        if self.records:
            self.records.write("result.json", result)
        return result
