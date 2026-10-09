"""A runner mirroring `Runner.run` and `Runner.apply` on the abstract process (B7, B8, B11).

Same decision schema (`contracts.validate_decision`), same limits semantics, same restart rule (any prompt after the
first restarts, even the same text), same keyframe rule (evenly spaced strictly inside the interval), same invalid-reply
handling. Observations carry text readings instead of images. Kind `sim_development`; never a benchmark score."""
import copy
from dataclasses import dataclass

from ..contracts import Limits, ModelReply, validate_decision
from .perception import COMPLETE, STAGES, reading
from .process import World

GOAL = "Complete the task."
LIMITS = Limits(max_steps=900, max_decisions=100, max_interval=400)
KEYFRAMES = 4
SUCCESS_VALUE, CALL_COST, SECOND_COST = 1.00, 0.02, 0.002   # dollars: correct declaration, per response, per robot second
STEPS_PER_SECOND = 20


def utility(success, calls, steps):
    return (SUCCESS_VALUE if success else 0.0) - CALL_COST * calls - SECOND_COST * steps / STEPS_PER_SECOND


@dataclass
class Setup:
    profile: object
    seed: int
    label: str = "K"
    episode: int = 0
    experience: tuple = ()
    limits: Limits = LIMITS
    goal: str = GOAL
    variant: str = None


class SimEpisode:
    def __init__(self, setup):
        self.setup = setup
        self.world = World(setup.profile, setup.seed)
        self.limits, self.goal = setup.limits, setup.goal
        self.steps = self.decisions = 0
        self.active_instruction = None
        self.history, self.interval_frames, self.last_error = [], [], None
        self.prompt_submissions = self.prompt_changes = self.prompt_restarts = 0
        self.intervals, self.usage, self.trace, self.restart_log = [], [], [], []
        self.status, self.reading = "running", self._read()
        self.reading_log = [(0, self.reading)]

    def _read(self, mode_snapshot=None, step=None):
        mode, work = mode_snapshot or (self.world.mode, self.world.work_done)
        return reading(self.world, mode, work, self.steps if step is None else step, self.setup.variant)

    def observation(self, with_experience=True):
        o = {"goal": self.goal, "policy": self.setup.label, "episode": self.setup.episode, "step": self.steps,
             "remaining_steps": self.limits.max_steps - self.steps,
             "remaining_decisions": self.limits.max_decisions - self.decisions, "max_interval": self.limits.max_interval,
             "active_instruction": self.active_instruction, "reading": self.reading,
             "interval_frames": copy.deepcopy(self.interval_frames), "history": copy.deepcopy(self.history),
             "last_error": self.last_error}
        if with_experience:
            o["experience"] = list(self.setup.experience)
        return o

    def fork(self, future_seed):
        """A copy for Monte Carlo continuations from the current state with fresh future randomness."""
        other = copy.copy(self)
        other.world = self.world.fork(future_seed)
        for name in ("history", "interval_frames", "intervals", "usage", "trace", "restart_log", "reading_log"):
            setattr(other, name, copy.deepcopy(getattr(self, name)))
        return other

    def _validate_state(self, decision):
        if decision["op"] == "run_policy" and "prompt" not in decision and self.active_instruction is None:
            raise ValueError("run_policy requires a prompt when no instruction is active")
        if decision.get("steps", 0) > self.limits.max_steps - self.steps:
            raise ValueError("requested interval exceeds remaining steps")

    def apply(self, decision):
        decision = validate_decision(decision, self.limits)
        self._validate_state(decision)
        if decision["op"] == "complete":
            self.status = "success" if self.world.checker() else "false_completion"
            return
        if "prompt" in decision:
            prior = self.active_instruction
            self.prompt_submissions += 1
            if prior is not None:
                if decision["prompt"] == prior:
                    self.prompt_restarts += 1
                else:
                    self.prompt_changes += 1
                self.restart_log.append((self.steps, self.world.mode, self.world.restart(decision["prompt"] == self.goal)))
            self.active_instruction = decision["prompt"]
        n, start = decision["steps"], self.steps
        marks = sorted({start + n * i // (KEYFRAMES + 1) for i in range(1, KEYFRAMES + 1)} - {start, start + n})
        snaps = self.world.advance(n, marks)
        self.steps += n
        self.intervals.append(n)
        self.interval_frames = [{"step": s, "reading": self._read(snaps[s], s)} for s in marks]
        self.reading = self._read()
        self.reading_log.append((self.steps, self.reading))
        self.trace.append((self.steps, self.world.mode))

    def decide_once(self, agent):
        """One decision cycle (budget checks, the agent's reply, validation, physics). False once the episode ended."""
        if self.status != "running":
            return False
        if self.steps >= self.limits.max_steps:
            self.status = "step_budget_exhausted"
            return False
        if self.decisions >= self.limits.max_decisions:
            self.status = "decision_budget_exhausted"
            return False
        observation = self.observation()
        self.decisions += 1
        reply = agent.decide(observation)
        if not isinstance(reply, ModelReply):
            raise TypeError("agent must return ModelReply")
        self.usage.append(reply.usage)
        entry = {"decision_index": self.decisions, "step_before": self.steps}
        self.last_error = None
        self.interval_frames = []
        try:
            self.apply(reply.decision)
        except ValueError as error:
            self.last_error = str(error)
            entry.update({"decision": reply.decision, "accepted": False, "error": self.last_error})
        else:
            entry.update({"decision": validate_decision(reply.decision, self.limits), "accepted": True})
        entry["step_after"], entry["reading"] = self.steps, self.reading
        self.history.append(entry)
        return self.status == "running"

    def run(self, agent, privileged=False):
        if privileged:
            agent.episode = self
        while self.decide_once(agent):
            pass
        if self.status == "running":   # the final cycle ended on a budget limit
            self.decide_once(agent)
        return self.result()

    def result(self):
        success = self.status == "success"
        accepted = [e for e in self.history if e["accepted"]]
        return {"status": self.status, "success": success, "false_completion": self.status == "false_completion",
                "physical_success_final": self.world.checker(), "steps": self.steps, "model_calls": self.decisions,
                "prompt_submissions": self.prompt_submissions, "prompt_changes": self.prompt_changes,
                "prompt_restarts": self.prompt_restarts, "intervals": list(self.intervals),
                "rejected_decisions": len(self.history) - len(accepted),
                "utility": utility(success, self.decisions, self.steps), "policy": self.setup.label,
                "profile": self.setup.profile.name, "seed": self.setup.seed, "episode": self.setup.episode,
                "latent_final": self.world.mode, "restarts": list(self.restart_log), "usage": list(self.usage)}

    def record(self):
        """B8: the raw record appended to the experience after the episode. No latent state, no statistics."""
        steps_decisions = []
        for e in self.history:
            d = e["decision"] if isinstance(e["decision"], dict) else {}
            steps_decisions.append({"step": e["step_before"], **{k: d[k] for k in ("op", "prompt", "steps") if k in d},
                                    "after": e["reading"]})
        result = self.result()
        return {"policy": self.setup.label, "episode": self.setup.episode, "decisions": steps_decisions,
                "outcome": {"success": "success", "false_completion": "false completion"}.get(self.status, self.status),
                "steps": self.steps, "calls": self.decisions, "score": round(result["utility"], 3)}
