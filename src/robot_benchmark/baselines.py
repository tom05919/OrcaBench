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
