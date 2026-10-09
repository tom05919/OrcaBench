"""Part 2: a closed-loop session. 24 episodes (8 per VLA) in 8 blocks of three, seeded order inside each block. The agent
sees the records of all earlier episodes of the session, with outcomes. Resumable: a finished episode is appended to the
output; rerunning continues after it. Regret against pi*_v is computed afterwards on the CPU (`--regret`).

  python scripts/sim_session.py --model claude-opus-5-5 --output runs/sim/session-opus-1.jsonl --limit 4.5
  python scripts/sim_session.py --regret runs/sim/session-opus-1.jsonl"""
import argparse
import json
import random
import sys
from pathlib import Path

from robot_benchmark.sim.agent import BudgetExceeded, SimAgent, Tracker
from robot_benchmark.sim.evaluate import evaluate
from robot_benchmark.sim.harness import Setup, SimEpisode
from robot_benchmark.sim.probes import SESSION_SEED_BASE, advantage_sum
from robot_benchmark.sim.process import PROFILES, _mix
from robot_benchmark.sim.references import FixedRule

LABELS = {"1": {"steady": "K", "hesitant": "R", "brittle": "T"}, "2": {"steady": "T", "hesitant": "K", "brittle": "R"}}


def schedule(per_vla, session_seed, reverse=False):
    rng, names, plan = random.Random(_mix(session_seed)), list(PROFILES), []
    for block in range(per_vla):
        order = names[:]
        rng.shuffle(order)
        plan += [(name, SESSION_SEED_BASE + names.index(name) * 100 + (per_vla - 1 - block if reverse else block)) for name in order]
    return plan


def regret(path, calibration):
    best = json.loads(calibration.read_text())["best"]
    rows = [json.loads(l) for l in path.read_text().splitlines()]
    out = []
    for row in rows:
        params = best[row["profile"]]
        star = SimEpisode(Setup(PROFILES[row["profile"]], row["seed"], row["policy"])).run(FixedRule(**params))
        est = advantage_sum(row["profile"], row["seed"], row["policy"], row["history"], params)
        out.append({"profile": row["profile"], "seed": row["seed"], "index": row["index"], "utility": row["utility"],
                    "star_utility": star["utility"], "paired_regret": star["utility"] - row["utility"], "advantage_sum_regret": est})
        print(row["index"], row["profile"], f"paired {out[-1]['paired_regret']:+.3f} advantage-sum {est:+.3f}", flush=True)
    path.with_suffix(".regret.json").write_text(json.dumps(out, indent=1) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--regret", type=Path)
    parser.add_argument("--calibration", type=Path, default=Path("runs/sim/calibration.json"))
    parser.add_argument("--ledger", default="runs/sim/spend.jsonl")
    parser.add_argument("--limit", type=float, default=4.5)
    parser.add_argument("--per-vla", type=int, default=8)
    parser.add_argument("--labels", choices=list(LABELS), default="1")
    parser.add_argument("--session-seed", type=int, default=1)
    parser.add_argument("--reverse", action="store_true", help="mirror: seeds in reverse order within each VLA")
    parser.add_argument("--max-episodes", type=int, default=100)
    args = parser.parse_args()
    if args.regret:
        return regret(args.regret, args.calibration)
    labels, tracker = LABELS[args.labels], Tracker(args.limit, args.ledger)
    agent = SimAgent(args.model, tracker)
    agent.tag = f"session:{args.model}"
    rows = [json.loads(l) for l in args.output.read_text().splitlines()] if args.output.exists() else []
    experience = [r["record"] for r in rows]
    print(f"resuming after {len(rows)} episodes; spent ${tracker.spent:.2f} of ${args.limit:.2f}", flush=True)
    with args.output.open("a") as out:
        for index, (name, seed) in enumerate(schedule(args.per_vla, args.session_seed, args.reverse)):
            if index < len(rows):
                continue
            if index - len(rows) >= args.max_episodes:
                return
            log = []
            agent.log = log.append
            ep = SimEpisode(Setup(PROFILES[name], seed, labels[name], index + 1, tuple(experience)))
            try:
                result = ep.run(agent)
            except BudgetExceeded as error:
                print(error, file=sys.stderr)
                return
            record = ep.record()
            experience.append(record)
            row = {"index": index, "profile": name, "seed": seed, "policy": labels[name], "utility": result["utility"],
                   "success": result["success"], "status": result["status"], "steps": result["steps"],
                   "calls": result["model_calls"], "restarts": result["restarts"], "prompt_changes": result["prompt_changes"],
                   "latent_final": result["latent_final"], "record": record, "history": ep.history, "model_log": log,
                   "spent": tracker.spent}
            out.write(json.dumps(row) + "\n")
            out.flush()
            print(index, name, result["status"], f"u={result['utility']:+.3f} steps={result['steps']} calls={result['model_calls']}",
                  f"restarts={len(result['restarts'])} ${tracker.spent:.2f}", flush=True)


if __name__ == "__main__":
    main()
