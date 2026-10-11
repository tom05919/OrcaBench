"""Non-privileged reference strategies; they read only public observation fields."""
from .contracts import ModelReply


def _decide(observation, every, reissue):
    # The runner ends the episode when remaining_steps hits 0, so complete with one step left.
    remaining = observation["remaining_steps"]
    if remaining <= 1:
        return ModelReply({"op": "complete"})
    steps = min(every or observation["max_interval"], observation["max_interval"], remaining - 1)
    decision = {"op": "run_policy", "steps": steps}
    if reissue or observation["active_instruction"] is None:
        decision["prompt"] = observation["goal"]
    return ModelReply(decision)


class AlwaysDeferAgent:
    """Submits the goal once, then lets the policy run in maximum-length intervals."""
    identity = {"kind": "baseline", "model": "always_defer_v1"}

    def decide(self, observation):
        return _decide(observation, None, False)


class ReissueAgent:
    """Re-submits the goal every `every` steps, restarting the policy each time."""

    def __init__(self, every=100):
        if type(every) is not int or every < 1:
            raise ValueError("every must be a positive integer")
        self.every = every
        self.identity = {"kind": "baseline", "model": f"reissue_every_{every}_v1"}

    def decide(self, observation):
        return _decide(observation, self.every, True)


class Reissue50Agent(ReissueAgent):
    """The interruption-interval sweep: the same baseline restarted every 50, 200 or 400 steps."""
    def __init__(self, every=50):
        super().__init__(every)


class Reissue200Agent(ReissueAgent):
    def __init__(self, every=200):
        super().__init__(every)


class Reissue400Agent(ReissueAgent):
    def __init__(self, every=400):
        super().__init__(every)


class ReplayAgent:
    """Replays the accepted decisions of an earlier episode with no model call, to ask which part of those decisions
    cost the episode. A diagnostic, never a scored system. It reads only the public goal, so nothing private reaches it.
    exact: the decisions as logged. native_text: every submitted prompt becomes the native goal, so wording changes
    and timing and restarts stay. no_interruption: only the first call submits the goal, so the policy is never
    restarted but every interval and the final complete stay where they were."""
    ABLATIONS = ("exact", "native_text", "no_interruption")

    def __init__(self, decisions, ablation="exact", source=None):
        if ablation not in self.ABLATIONS:
            raise ValueError(f"ablation must be one of {self.ABLATIONS}")
        # A log may end in complete or at a budget: the runner stops at an exhausted budget before asking again, so a
        # replay that diverges and needs more decisions than were logged raises in decide() instead.
        if not decisions:
            raise ValueError("a replayable episode has at least one accepted decision")
        self.decisions, self.ablation, self.calls = [dict(d) for d in decisions], ablation, 0
        self.identity = {"kind": "diagnostic", "model": f"replay_{ablation}_v1", "source_episode": source}

    def decide(self, observation):
        if self.calls >= len(self.decisions):
            raise RuntimeError("replay ran past the recorded decisions")
        decision, first = dict(self.decisions[self.calls]), self.calls == 0
        self.calls += 1
        if decision["op"] == "run_policy":
            if self.ablation == "native_text" and "prompt" in decision:
                decision["prompt"] = observation["goal"]
            elif self.ablation == "no_interruption":
                if first:
                    decision["prompt"] = observation["goal"]
                else:
                    decision.pop("prompt", None)
        return ModelReply(decision)
