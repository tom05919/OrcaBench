"""Part 1: log probes. The agent reads raw records of 0, 3 or 8 earlier episodes per VLA and answers three standard
situations (S1 the first interval, S2 an apparent stall, S3 the first sight of 'looks complete'). Answers are scored by
Monte Carlo action values. Resumable: each answer is appended to the output as it arrives.

  python scripts/sim_probes.py --model claude-opus-5-5 --output runs/sim/probes-opus.jsonl --limit 4.5"""
import argparse
import json
import sys
from pathlib import Path

from robot_benchmark.contracts import validate_decision
from robot_benchmark.sim.agent import BudgetExceeded, SimAgent, Tracker
from robot_benchmark.sim.harness import LIMITS
from robot_benchmark.sim.probes import CLASSES, Scorer, candidates, make_log, probe_observation, situations
from robot_benchmark.sim.process import PROFILES

LOG_SETS = {"A": ({"steady": "K", "hesitant": "R", "brittle": "T"}, 1), "B": ({"steady": "T", "hesitant": "K", "brittle": "R"}, 2)}


def valid_answer(decision, ep):
    try:
        d = validate_decision(decision, LIMITS)
        ep._validate_state(d)
        return d
    except (ValueError, KeyError, TypeError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, default=Path("runs/sim/calibration.json"))
    parser.add_argument("--ledger", default="runs/sim/spend.jsonl")
    parser.add_argument("--limit", type=float, default=4.5)
    parser.add_argument("--levels", type=int, nargs="+", default=[8, 3, 0])
    parser.add_argument("--instances", type=int, default=2)
    parser.add_argument("--level0-repeats", type=int, default=2)
    parser.add_argument("--max-calls", type=int, default=200)
    parser.add_argument("--k", type=int, default=300, help="Monte Carlo continuations per action value")
    args = parser.parse_args()
    best = json.loads(args.calibration.read_text())["best"]
    scorer = Scorer(best, args.k)
    tracker = Tracker(args.limit, args.ledger)
    agent = SimAgent(args.model, tracker)
    agent.tag = f"probes:{args.model}"
    done = {tuple(json.loads(l)["key"]) for l in args.output.read_text().splitlines()} if args.output.exists() else set()
    calls = 0
    print(f"spent so far ${tracker.spent:.2f} of ${args.limit:.2f}", flush=True)
    with args.output.open("a") as out:
        for level in args.levels:
            for set_name, (labels, log_seed) in LOG_SETS.items():
                repeats = range(args.level0_repeats) if level == 0 else [0]
                if level == 0 and set_name == "B" and args.level0_repeats < 2:
                    continue
                log = make_log(labels, 8, log_seed)[: 3 * level]
                for cls in CLASSES:
                    for profile in PROFILES:
                        label = labels[profile]
                        for instance, (seed, ep) in enumerate(situations(profile, cls, args.instances, label)):
                            key = (level, set_name, cls, profile, instance)
                            if key in done:
                                continue
                            if calls >= args.max_calls:
                                return
                            try:
                                reply = agent.decide(probe_observation(ep, log))
                            except BudgetExceeded as error:
                                print(error, file=sys.stderr)
                                return
                            calls += 1
                            decision = valid_answer(reply.decision, ep)
                            if decision is None:
                                value = min(scorer.value(profile, cls, ep, c) for c in candidates(cls))
                            else:
                                value = scorer.value(profile, cls, ep, decision)
                            best_value = scorer.best_value(profile, cls, ep)
                            row = {"key": list(key), "level": level, "log_set": set_name, "cls": cls, "profile": profile,
                                   "label": label, "instance": instance, "seed": seed, "decision": reply.decision,
                                   "valid": decision is not None, "value": value, "best_value": best_value,
                                   "advantage": value - best_value, "thinking": agent.last_trace["thinking"],
                                   "usage": agent.last_trace["usage"], "spent": tracker.spent, "reading": ep.reading, "latent": ep.world.mode}
                            out.write(json.dumps(row) + "\n")
                            out.flush()
                            print(level, set_name, cls, profile, instance, json.dumps(reply.decision), f"adv {row['advantage']:+.3f}", f"${tracker.spent:.2f}", flush=True)


if __name__ == "__main__":
    main()
