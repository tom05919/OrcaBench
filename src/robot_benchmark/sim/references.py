"""Reference policies (B10): CPU only, never shown to the agent, never mixed with model scores.

The fixed family F(t0, N, tau, rule) is stateless: it reads only the observation, so it can be resumed from any
history, which Monte Carlo continuations need. `rule` is 'first' (declare on the first sight of 'looks complete')
or 'confirm' (declare when a second sighting comes at least 40 steps after the first)."""
import itertools

from ..baselines import AlwaysDeferAgent, ReissueAgent
from ..contracts import ModelReply
from .perception import COMPLETE, STAGES

CONFIRM_STEPS = 40
REWRITE = "Carefully complete the task, step by step."   # a different text: logged as a change, same restart effect


def stage(name):
    return STAGES.index(name)


class FixedRule:
    def __init__(self, t0=300, every=300, tau=None, rule="first", prompt=None):
        self.t0, self.every, self.tau, self.rule, self.prompt = t0, every, tau, rule, prompt
        self.identity = {"kind": "reference", "model": f"F({t0},{every},{tau},{rule})"}

    def _readings(self, obs):
        points = [(0, "not started")] + [(e["step_after"], e["reading"]) for e in obs["history"]
                                         if e["accepted"] and e["decision"]["op"] == "run_policy"]
        return points if points[-1][0] == obs["step"] else points + [(obs["step"], obs["reading"])]

    def decide(self, obs):
        rem, step = obs["remaining_steps"], obs["step"]
        if rem <= 1:
            return ModelReply({"op": "complete"})
        if obs["active_instruction"] is None:
            return ModelReply({"op": "run_policy", "prompt": obs["goal"], "steps": min(self.t0, rem - 1, obs["max_interval"])})
        points = self._readings(obs)
        seen = [s for s, r in points if stage(r) == COMPLETE]
        look = obs["reading"] == STAGES[COMPLETE]
        interval = min(self.every, rem - 1, obs["max_interval"])
        if look:
            if self.rule == "first" or (len(seen) >= 2 and seen[-1] - seen[-2] >= CONFIRM_STEPS):
                return ModelReply({"op": "complete"})
            return ModelReply({"op": "run_policy", "steps": min(CONFIRM_STEPS, rem - 1, obs["max_interval"])})
        if self.tau is not None:
            top, last_rise = 0, 0
            for s, r in points:
                if stage(r) > top:
                    top, last_rise = stage(r), s
            if step - last_rise >= self.tau:
                return ModelReply({"op": "run_policy", "prompt": self.prompt or obs["goal"], "steps": interval})
        return ModelReply({"op": "run_policy", "steps": interval})


def opus_like():
    """The calibration check: first look at 150, then every 150; declare at the first 'looks complete'; reword whenever the
    visible stage did not rise since the last look."""
    return FixedRule(150, 150, tau=150, rule="first", prompt=REWRITE)


class Oracle:
    """Privileged bound: sees the latent state. Restarts only a stalled policy, declares the moment the checker is true."""
    identity = {"kind": "oracle", "model": "privileged_oracle"}

    def decide(self, obs):
        w, rem = self.episode.world, obs["remaining_steps"]
        if w.checker() or rem <= 1:
            return ModelReply({"op": "complete"})
        stuck_in = [x - w.work_done for x, kind, _ in w.events if kind == "STUCK"] if w.mode == "WORK" else []
        run = max(1, min(400, w.time_to_done() or 1, (min(stuck_in) + 1) if stuck_in else 400, rem - 1))
        if obs["active_instruction"] is None:
            return ModelReply({"op": "run_policy", "prompt": obs["goal"], "steps": run})
        if w.mode == "STUCK":
            return ModelReply({"op": "run_policy", "prompt": obs["goal"], "steps": min(30, rem - 1)})
        return ModelReply({"op": "run_policy", "steps": run})


GRID = [dict(t0=t0, every=n, tau=tau, rule=rule)
        for t0, n, tau, rule in itertools.product((100, 200, 300, 400), (50, 100, 200, 400), (80, 160, None), ("first", "confirm"))]


def baselines():
    return {"always_defer": AlwaysDeferAgent, "reissue_50": lambda: ReissueAgent(50), "reissue_100": ReissueAgent,
            "reissue_200": lambda: ReissueAgent(200), "observe_100": lambda: FixedRule(100, 100, None, "first"),
            "observe_200_confirm": lambda: FixedRule(200, 200, None, "confirm"), "opus_like": opus_like}
