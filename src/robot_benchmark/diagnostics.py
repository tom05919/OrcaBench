"""Privileged rescue supervisors: they read simulator truth, so they only show
that a scene can be rescued by re-prompting and never count as model results.
Every physical action still comes from the frozen policy."""
from .contracts import ModelReply
from .tasks.predicates import SEQUENCES


def _steps(interval, observation):
    return min(interval, observation["max_interval"], observation["remaining_steps"])


class PrivilegedRetrySupervisor:
    """Issue the native goal; re-issue it after `stall_steps` without success.
    The success check runs every 100 steps, the same granularity as the plain-policy reference."""
    identity = {"kind": "diagnostic", "model": "privileged_retry_v1"}

    def __init__(self, env, stall_steps=300, interval=100):
        self.env, self.stall_steps, self.interval = env, stall_steps, interval
        self.prompted_at = None

    def decide(self, observation):
        if self.env.evaluate()["success"]:
            return ModelReply({"op": "complete"})
        decision = {"op": "run_policy", "steps": _steps(self.interval, observation)}
        if (self.prompted_at is None or observation["active_instruction"] is None
                or observation["step"] - self.prompted_at >= self.stall_steps):
            decision["prompt"], self.prompted_at = observation["goal"], observation["step"]
        return ModelReply(decision)


class PrivilegedSequencer:
    """Prompt the first unmet step of SEQUENCES[task]; keep the last step if all are met without success."""
    identity = {"kind": "diagnostic", "model": "privileged_sequencer_v1"}

    def __init__(self, env, task, interval=50):
        if task not in SEQUENCES:
            raise ValueError(f"no diagnostic sequence for task {task!r}")
        self.env, self.steps, self.interval = env, SEQUENCES[task], interval

    def decide(self, observation):
        truth = self.env.evaluate()
        if truth["success"]:
            return ModelReply({"op": "complete"})
        missing = [name for name, _ in self.steps if name not in truth]
        if "predicate_error" in truth or missing:
            raise RuntimeError(f"diagnostic-only infrastructure error: predicates unavailable "
                               f"({truth.get('predicate_error') or f'missing {missing}'})")
        prompt = next((prompt for name, prompt in self.steps if not truth[name]), self.steps[-1][1])
        decision = {"op": "run_policy", "steps": _steps(self.interval, observation)}
        if observation["active_instruction"] != prompt:
            decision["prompt"] = prompt
        return ModelReply(decision)
