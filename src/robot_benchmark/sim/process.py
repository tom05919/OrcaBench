"""The latent task process (B2), VLA profiles (B3), restart model (B4) and common random numbers (B9).

All time is in control steps (20 steps = 1 s). One episode is (profile, seed). Three random streams keep every agent
facing the same world: the latent draws and the future onsets (a seeded Random), the restart outcomes (hash of seed and
the restart's index) and the perception noise (hash of seed and the absolute step)."""
import math
import random
from dataclasses import dataclass
from statistics import NormalDist

_M = (1 << 64) - 1
_NORMAL = NormalDist()
CHECKER, LAG_MEDIAN, LAG_SIGMA = "DONE", 20, 0.5
LOSS_HAZARD = 5e-5         # per DONE-step: the policy keeps acting after the task is done
UNDO_PROB, UNDO_STEPS = 0.3, 40   # a restart after completion undoes the last 40 steps of work with this probability
DELAY_MEDIAN, DELAY_SIGMA = 40, 0.4  # restart delay
WORDING_BREAK = 0.0        # z_w: extra break probability for non-native text (unmeasured; 0 in the main experiment)


def _mix(x):
    x = (x + 0x9E3779B97F4A7C15) & _M
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & _M
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & _M
    return x ^ (x >> 31)


def uniform(seed, stream, a, b=0):
    """A deterministic uniform in (0, 1) for (seed, stream, a, b): common random numbers without shared state."""
    return ((_mix(_mix(_mix(seed * 1000003 + stream) + a) + b) >> 11) + 0.5) / (1 << 53)


def lognormal(median, sigma, u):
    return median * math.exp(sigma * _NORMAL.inv_cdf(u))


@dataclass(frozen=True)
class Profile:
    name: str
    work_median: float      # m_W: steps of work needed
    work_sigma: float       # s_W
    hover_rate: float       # lambda_h per 100 work-steps: pauses that resolve on their own
    hover_median: float
    hover_sigma: float
    stuck_rate: float       # lambda_s per 100 work-steps: stalls that only a restart frees
    break_prob: float       # z: a restart breaks the episode
    rescue: float           # r_esc: a restart frees a stalled policy


STEADY = Profile("steady", 240, 0.20, 0.15, 30, 0.5, 0.0, 0.02, 0.0)
HESITANT = Profile("hesitant", 300, 0.30, 1.0, 80, 0.6, 0.0, 0.15, 0.0)
BRITTLE = Profile("brittle", 260, 0.25, 0.15, 30, 0.5, 0.5, 0.01, 0.85)
PROFILES = {p.name: p for p in (STEADY, HESITANT, BRITTLE)}


def poisson_positions(rng, rate, start, stop):
    """Event positions of a Poisson process with `rate` per 100 steps over (start, stop]."""
    out, x = [], start
    if rate <= 0:
        return out
    while True:
        x += rng.expovariate(rate / 100)
        if x > stop:
            return out
        out.append(int(x) + 1)


class World:
    """Latent state of one episode. `mode` is WORK, HOVER, STUCK, DELAY, RETREAT, DONE, LOST or BROKEN.
    The checker is true exactly in DONE; RETREAT is the visually complete state before it (the lag)."""

    def __init__(self, profile, seed):
        rng = random.Random(_mix(seed * 7919 + 1))
        self.profile, self.seed = profile, seed
        self.W = max(20, round(lognormal(profile.work_median, profile.work_sigma, rng.random())))
        self.lag = max(0, round(lognormal(LAG_MEDIAN, LAG_SIGMA, rng.random())))
        self.loss_after = max(1, round(rng.expovariate(LOSS_HAZARD)))
        self.mode, self.work_done, self.t, self.timer = "WORK", 0, 0, 0
        self.after_delay = ("WORK", 0)
        self.done_steps, self.restarts = 0, 0
        self.events = self._schedule(rng, 0)   # sorted (position, kind, duration) of pending onsets

    def _schedule(self, rng, start):
        p = self.profile
        events = [(x, "HOVER", max(1, round(lognormal(p.hover_median, p.hover_sigma, rng.random()))))
                  for x in poisson_positions(rng, p.hover_rate, start, self.W)]
        events += [(x, "STUCK", 0) for x in poisson_positions(rng, p.stuck_rate, start, self.W)]
        return sorted(events)

    def fork(self, future_seed):
        """A copy for Monte Carlo continuations: same latent state, fresh future onsets, restarts and perception."""
        other = World.__new__(World)
        other.__dict__.update(self.__dict__)
        other.seed = future_seed
        rng = random.Random(_mix(future_seed * 104729 + self.t))
        other.events = [e for e in self.events if e[0] < 0]  # replaced below
        other.events = [e for e in self._schedule(rng, self.work_done)]
        return other

    # -- dynamics ---------------------------------------------------------------------------------------------
    def checker(self):
        return self.mode == CHECKER

    def visually_complete(self):
        return self.mode in ("RETREAT", "DONE", "LOST")

    def advance(self, n, marks=()):
        """Run the policy for n steps. `marks` are absolute steps inside the interval whose (mode, work_done) are
        recorded: the keyframes. Returns {step: (mode, work_done)}."""
        marks, snaps, end = sorted(marks), {}, self.t + n
        while self.t < end:
            limit = end - self.t
            if marks and marks[0] > self.t:
                limit = min(limit, marks[0] - self.t)
            self._move(limit)
            while marks and marks[0] <= self.t:
                snaps[marks.pop(0)] = (self.mode, self.work_done)
        return snaps

    def _move(self, limit):
        """Advance at most `limit` steps to the next event; always makes progress."""
        mode = self.mode
        if mode in ("STUCK", "LOST", "BROKEN"):
            self.t += limit
        elif mode == "WORK":
            target = self.W
            if self.events:
                target = min(target, self.events[0][0])
            step = min(limit, max(0, target - self.work_done))
            self.t += step
            self.work_done += step
            if step == limit and self.work_done < target:
                return
            if self.events and self.work_done >= self.events[0][0]:
                _, kind, duration = self.events.pop(0)
                self.mode, self.timer = kind, duration
            elif self.work_done >= self.W:
                self.mode, self.timer = "RETREAT", self.lag
                if self.lag == 0:
                    self.mode, self.done_steps = "DONE", 0
        elif mode in ("HOVER", "DELAY", "RETREAT"):
            step = min(limit, self.timer)
            self.t += step
            self.timer -= step
            if self.timer <= 0:
                if mode == "HOVER":
                    self.mode = "WORK"
                elif mode == "DELAY":
                    self.mode, self.timer = self.after_delay
                else:
                    self.mode, self.done_steps = "DONE", 0
        elif mode == "DONE":
            step = min(limit, self.loss_after - self.done_steps)
            self.t += step
            self.done_steps += step
            if self.done_steps >= self.loss_after:
                self.mode = "LOST"

    def restart(self, native=True):
        """Any prompt after the first restarts the policy (B4). Outcomes are drawn from the restart's own stream."""
        k, self.restarts = self.restarts, self.restarts + 1
        u = [uniform(self.seed, 2, k, j) for j in range(4)]
        delay = max(1, round(lognormal(DELAY_MEDIAN, DELAY_SIGMA, u[3])))
        if self.mode in ("LOST", "BROKEN"):
            return "none"
        if u[0] < self.profile.break_prob + (0 if native else WORDING_BREAK):
            self.mode = "BROKEN"
            return "break"
        if self.mode == "STUCK":
            if u[1] < self.profile.rescue:
                self.mode, self.timer, self.after_delay = "DELAY", delay, ("WORK", 0)
                return "freed"
            return "still_stuck"
        if self.mode in ("RETREAT", "DONE"):
            if u[2] < UNDO_PROB:
                self.work_done, self.done_steps = max(0, self.W - UNDO_STEPS), 0
                self.mode, self.timer, self.after_delay = "DELAY", delay, ("WORK", 0)
                return "undo"
            return "none"
        if self.mode == "HOVER":
            self.mode, self.after_delay, self.timer = "DELAY", ("HOVER", self.timer), delay
            return "delayed_hover"
        if self.mode == "DELAY":
            self.timer = delay
            return "delayed"
        self.mode, self.timer, self.after_delay = "DELAY", delay, ("WORK", 0)
        return "delayed"

    def time_to_done(self):
        """Privileged: steps until the checker is true if the policy is left alone (stalls excluded)."""
        if self.mode == "DONE":
            return 0
        if self.mode == "RETREAT":
            return self.timer
        pending = sum(d for x, kind, d in self.events if kind == "HOVER")
        first = (self.timer if self.mode in ("HOVER", "DELAY") else 0)
        return first + pending + max(0, self.W - self.work_done) + self.lag
