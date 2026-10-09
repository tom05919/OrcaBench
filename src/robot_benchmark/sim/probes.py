"""Experience logs, probe situations, Monte Carlo action values and the regret estimator (docs/env_design.md, Decision 2).

Probe situations are generated from each VLA's own process by rule, so they are the same for every agent. An answer is
scored by its action value: the expected utility of taking that decision from the situation and then following pi*_v,
estimated over fresh futures (K continuations). Nothing here calls a model."""
import random
from functools import lru_cache

from ..contracts import ModelReply
from .harness import GOAL, Setup, SimEpisode
from .perception import COMPLETE, STAGES
from .process import PROFILES, _mix
from .references import FixedRule

CLASSES = ("S1", "S2", "S3")
S2_STALL_STEPS, S2_MIN_REMAINING, SCOUT_STEPS = 160, 300, 80
CONTINUE_STEPS = (20, 40, 80, 160, 300)
FIRST_INTERVALS = (50, 100, 150, 200, 300, 400)
LOG_SEED_BASE, SITUATION_SEED_BASE, SESSION_SEED_BASE, REGRET_SEED_BASE = 4_000_000, 5_000_000, 3_000_000, 6_000_000


class Scripted:
    """Returns the given decisions in order, then delegates to `then`."""

    def __init__(self, decisions, then=None):
        self.decisions, self.then, self.identity = list(decisions), then, {"kind": "scripted"}

    def decide(self, obs):
        if self.decisions:
            return ModelReply(self.decisions.pop(0))
        return self.then.decide(obs)


def decision_points(obs):
    """(step, reading) at every decision point so far, including the unseen start."""
    points = [(0, STAGES[0])] + [(e["step_after"], e["reading"]) for e in obs["history"]
                                 if e["accepted"] and e["decision"]["op"] == "run_policy"]
    return points if points[-1][0] == obs["step"] else points + [(obs["step"], obs["reading"])]


def last_rise(points):
    top, step = 0, 0
    for s, r in points:
        if STAGES.index(r) > top:
            top, step = STAGES.index(r), s
    return step


def situation_met(cls, obs):
    if cls == "S2":
        return (obs["reading"] != STAGES[COMPLETE] and obs["remaining_steps"] >= S2_MIN_REMAINING
                and obs["step"] - last_rise(decision_points(obs)) >= S2_STALL_STEPS)
    if cls == "S3":
        return obs["step"] > 0 and obs["reading"] == STAGES[COMPLETE] and all(
            r != STAGES[COMPLETE] for _, r in decision_points(obs)[:-1])
    return obs["step"] == 0


def find_situation(profile_name, cls, seed, label="K"):
    """Run a scout observer (look every 80 steps, never restart, never declare) from `seed` until the situation holds;
    return the paused episode, or None if the seed never produces it."""
    ep = SimEpisode(Setup(PROFILES[profile_name], seed, label))
    if cls == "S1":
        return ep
    scout = Scripted([], then=_Scout())
    while True:
        obs = ep.observation(with_experience=False)
        if situation_met(cls, obs):
            return ep
        if not ep.decide_once(scout) or obs["remaining_steps"] < S2_MIN_REMAINING and cls == "S2":
            return None


class _Scout:
    identity = {"kind": "scout"}

    def decide(self, obs):
        rem = obs["remaining_steps"]
        if obs["active_instruction"] is None:
            return ModelReply({"op": "run_policy", "prompt": obs["goal"], "steps": min(SCOUT_STEPS, rem - 1)})
        return ModelReply({"op": "run_policy", "steps": min(SCOUT_STEPS, rem - 1)})


def situations(profile_name, cls, count, label="K", first_seed=SITUATION_SEED_BASE):
    """The first `count` seeds from a fixed range that produce the situation, chosen by rule, never by outcome."""
    found, seed = [], first_seed
    while len(found) < count and seed < first_seed + 5000:
        ep = find_situation(profile_name, cls, seed, label)
        if ep is not None:
            found.append((seed, ep))
        seed += 1
    return found


# -- action values -------------------------------------------------------------------------------------------------
def candidates(cls):
    if cls == "S1":
        return [{"op": "run_policy", "prompt": GOAL, "steps": n} for n in FIRST_INTERVALS]
    if cls == "S2":
        return ([{"op": "run_policy", "steps": n} for n in CONTINUE_STEPS]
                + [{"op": "run_policy", "prompt": GOAL, "steps": n} for n in CONTINUE_STEPS])
    return [{"op": "complete"}] + [{"op": "run_policy", "steps": n} for n in CONTINUE_STEPS[:4]]


def action_value(ep, decision, params, k=300, salt=0):
    """Expected utility of `decision` from the paused episode, then pi*_v, over k fresh futures."""
    total = 0.0
    for j in range(k):
        fork = ep.fork(_mix(ep.setup.seed * 31 + ep.steps * 7 + salt * 1009 + j))
        total += fork.run(Scripted([dict(decision)], then=FixedRule(**params)))["utility"]
    return total / k


def start_value(profile_name, decision, params, k=300, first_seed=REGRET_SEED_BASE):
    """S1: the value of a first call averaged over k fresh worlds (the start has no latent state worth conditioning on)."""
    total = 0.0
    for j in range(k):
        ep = SimEpisode(Setup(PROFILES[profile_name], first_seed + j))
        total += ep.run(Scripted([dict(decision)], then=FixedRule(**params)))["utility"]
    return total / k


class Scorer:
    """Scores answers and caches action values per situation."""

    def __init__(self, best_rules, k=300):
        self.best, self.k, self.cache = best_rules, k, {}

    def value(self, profile_name, cls, ep, decision):
        key = (profile_name, cls, ep.setup.seed if ep else 0, repr(sorted(decision.items())))
        if key not in self.cache:
            params = self.best[profile_name]
            self.cache[key] = (start_value(profile_name, decision, params, self.k) if cls == "S1"
                               else action_value(ep, decision, params, self.k))
        return self.cache[key]

    def best_value(self, profile_name, cls, ep):
        return max(self.value(profile_name, cls, ep, d) for d in candidates(cls))

    def advantage(self, profile_name, cls, ep, decision):
        """Value of the answer minus the best candidate's (about 0 or negative)."""
        return self.value(profile_name, cls, ep, decision) - self.best_value(profile_name, cls, ep)


# -- experience logs -----------------------------------------------------------------------------------------------
def explore_rule(rng):
    return dict(t0=rng.choice(range(100, 501, 50)), every=rng.choice((50, 100, 150, 200, 300, 400)),
                tau=rng.choice((80, 160, None)), rule=rng.choice(("first", "confirm")))


def make_log(labels, per_vla, log_seed):
    """Raw B8 records from an exploring behaviour policy: interleaved in blocks of three, each VLA once per block."""
    rng, records, number = random.Random(_mix(log_seed)), [], 0
    names = list(PROFILES)
    for block in range(per_vla):
        order = names[:]
        rng.shuffle(order)
        for name in order:
            number += 1
            seed = LOG_SEED_BASE + log_seed * 10_000 + names.index(name) * 100 + block
            ep = SimEpisode(Setup(PROFILES[name], seed, labels[name], number))
            ep.run(FixedRule(**explore_rule(rng)))
            records.append(ep.record())
    return records


def probe_observation(ep, experience):
    obs = ep.observation(with_experience=False)
    obs["experience"] = list(experience)
    obs["episode"] = len(experience) + 1
    return obs


# -- regret ---------------------------------------------------------------------------------------------------------
def advantage_sum(profile_name, seed, label, history, params, k=200):
    """Estimated regret of one logged episode against pi*_v: -sum over the agent's decisions of
    Q(s, agent's decision) - Q(s, pi*'s decision), each by Monte Carlo from the true latent state."""
    ep = SimEpisode(Setup(PROFILES[profile_name], seed, label))
    star, total = FixedRule(**params), 0.0
    for t, entry in enumerate(history):
        if ep.status != "running":
            break
        obs = ep.observation(with_experience=False)
        chosen, preferred = entry["decision"], star.decide(obs).decision
        if chosen != preferred:
            total += action_value(ep, chosen, params, k, salt=t) - action_value(ep, preferred, params, k, salt=t)
        ep.decide_once(Scripted([chosen]))
    return -total
