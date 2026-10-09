"""Fit pi*_v and pi_pool on training seeds and print the calibration table on held-out seeds (docs/env_design.md).

  python scripts/sim_calibrate.py --workers 8 --output runs/sim/calibration.json"""
import argparse
import json
from multiprocessing import Pool
from pathlib import Path

from robot_benchmark.sim.evaluate import HELDOUT_SEEDS, TRAIN_SEEDS, evaluate, fit_rules
from robot_benchmark.sim.process import PROFILES
from robot_benchmark.sim.references import baselines, FixedRule


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--train", type=int, default=1000)
    parser.add_argument("--heldout", type=int, default=2000)
    parser.add_argument("--output", type=Path, default=Path("runs/sim/calibration.json"))
    args = parser.parse_args()
    train, held = list(TRAIN_SEEDS)[:args.train], list(HELDOUT_SEEDS)[:args.heldout]
    best, pooled, table = fit_rules(train, args.workers)
    out = {"best": best, "pooled": pooled, "heldout": {}}
    with Pool(args.workers) as pool:
        rows = {"always_defer": dict(t0=900, every=400, tau=None, rule="never_declare")}
        for name, params in [("pi_star", None), ("pi_pool", pooled)]:
            pass
        for profile in PROFILES:
            out["heldout"][profile] = {"pi_star": evaluate(best[profile], profile, held, pool),
                                       "pi_pool": evaluate(pooled, profile, held, pool),
                                       "oracle": evaluate("oracle", profile, held, pool)}
    print("best rule per VLA:", json.dumps(best))
    print("pooled rule:", pooled)
    for profile, rows in out["heldout"].items():
        for name, m in rows.items():
            print(f"{profile:9s} {name:8s} success {m['success']:.2f} utility {m['utility']:.3f} calls {m['calls']:.1f} steps {m['steps']:.0f}")
    for profile in PROFILES:
        print(f"value of adaptation, {profile}: {out['heldout'][profile]['pi_star']['utility'] - out['heldout'][profile]['pi_pool']['utility']:.3f}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
