#!/usr/bin/env python3
"""Write the final session plans (docs/final_experiment.md), the input of W3's `session` command.

- **One session per scene seed.** Each covers every (policy, task) cell once, so a supervisor meets every policy on
  every task in one context.
- **Blocks:** each block is one task, run once with each policy in a shuffled order, so the supervisor sees the
  policies side by side on the same task. The block order is shuffled too.
- **Labels:** each session maps the policies to anonymous labels with a fresh random permutation.

Everything is fixed by `--seed`, and the same plans serve every model. A plan file is a JSON list of
`{task, scene_seed, policy_seed, policy_label, backend}` in order. W3 adds `expect_state` per entry from the
always-defer run of the same cell on the same pod. `plans/manifest.json` records the inputs.

  python3 scripts/make_session_plans.py --policies groot groot_u10 groot_u30 --tasks A B C \\
      --scenes 1000 1001 1002 1003 --output runs/final/plans
"""
import argparse
import json
from pathlib import Path
import random

LABELS = ("K", "R", "T", "V", "W", "Z")


def make_plans(policies, tasks, scenes, policy_seed, seed):
    if len(policies) > len(LABELS) or len(set(policies)) != len(policies) or len(set(tasks)) != len(tasks):
        raise ValueError("policies and tasks must be distinct, with at most six policies")
    rng = random.Random(seed)
    plans = {}
    for scene in scenes:
        labels = dict(zip(policies, rng.sample(LABELS[:len(policies)], len(policies))))
        order = []
        for task in rng.sample(list(tasks), len(tasks)):
            for backend in rng.sample(list(policies), len(policies)):
                order.append({"task": task, "scene_seed": scene, "policy_seed": policy_seed,
                              "policy_label": labels[backend], "backend": backend})
        plans[f"scene{scene}"] = order
    return plans


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--policies", nargs="+", required=True)
    parser.add_argument("--tasks", nargs="+", required=True)
    parser.add_argument("--scenes", type=int, nargs="+", required=True)
    parser.add_argument("--policy-seed", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20261014)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plans = make_plans(args.policies, args.tasks, args.scenes, args.policy_seed, args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, entries in plans.items():
        (args.output / f"{name}.json").write_text(json.dumps(entries, indent=1) + "\n")
    (args.output / "manifest.json").write_text(json.dumps({k: v for k, v in vars(args).items() if k != "output"}
                                                          | {"sessions": sorted(plans)}, indent=2) + "\n")
    print(f"{len(plans)} sessions of {len(next(iter(plans.values())))} episodes in {args.output}")


if __name__ == "__main__":
    main()
