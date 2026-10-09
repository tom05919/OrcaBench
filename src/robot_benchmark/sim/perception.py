"""What the supervisor sees (B6): one reading of how far along the task looks, from an imperfect perception model.

Calibrated to the offline completion probe: 'looks complete' with probability 0.70 once the task is visually complete
(about 0.70 after the checker turned true, 0.66 in the last 20 steps before), 0.30 in the last 60 work-steps and 0.02
earlier. Noise is keyed by (seed, absolute step), so two agents looking at the same step see the same reading."""
from .process import _NORMAL, uniform

STAGES = ("not started", "early", "midway", "late", "looks complete")
COMPLETE = len(STAGES) - 1
P_COMPLETE_AFTER, P_COMPLETE_NEAR, P_COMPLETE_FAR, NEAR_STEPS = 0.70, 0.30, 0.02, 60
EDGES = (0.2, 0.45, 0.7)
HIDDEN, FALSE_POSITIVE = "hidden", "false_positive"   # legibility variants (defined, not in the main experiment)


def reading_index(world, mode, work_done, step, variant=None):
    u = uniform(world.seed, 3, step)
    if variant == HIDDEN:
        complete_p = 0.0
    elif variant == FALSE_POSITIVE:
        complete_p = 0.9
    elif mode in ("RETREAT", "DONE", "LOST"):
        complete_p = P_COMPLETE_AFTER
    else:
        complete_p = P_COMPLETE_NEAR if world.W - work_done < NEAR_STEPS else P_COMPLETE_FAR
    if u < complete_p:
        return COMPLETE
    if mode in ("RETREAT", "DONE", "LOST"):
        return COMPLETE - 1   # visually complete but not 'recognized': it looks late
    q = work_done / world.W + 0.1 * _NORMAL.inv_cdf(uniform(world.seed, 4, step))
    return sum(q >= edge for edge in EDGES)


def reading(world, mode, work_done, step, variant=None):
    return STAGES[reading_index(world, mode, work_done, step, variant)]
