"""Does (task, scene seed) fix the starting scene? Resets each pair in fresh processes and reports the kitchen layout,
style and step-0 simulator state hash of every attempt. No policy, no model, no API cost.

Stage 2 found pairs whose arms started from different kitchens. This probe measures how often that happens, in
fresh processes (as `run` and `baseline` start) and in repeated resets inside one process (as `screen` runs a grid),
with and without a fixed PYTHONHASHSEED. Run it on the worker after `source scripts/project_env.sh`.

  python scripts/probe_scene_repro.py --pairs WashLettuce:1002 RinseSinkBasin:1002 CloseFridge:1000 \\
      --repeats 3 --hashseed unset 0 --output runs/probes/scene_repro.json
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def child(task, scene, resets):
    """Reset (task, scene) `resets` times in this process; print one JSON line with every attempt."""
    from robot_benchmark.adapters.robocasa import RoboCasaEnvironment
    env = RoboCasaEnvironment(task, "pretrain", 256)
    attempts = []
    try:
        for _ in range(resets):
            if os.environ.get("PROBE_SEED_GLOBALS"):  # test: do unseeded global draws explain the instability?
                import random
                import numpy
                random.seed(scene)
                numpy.random.seed(scene)
            env.reset(scene)
            snapshot = env.snapshot()
            meta = snapshot["episode_metadata"]
            attempts.append({"layout": meta.get("layout_id"), "style": meta.get("style_id"),
                             "state": snapshot["state_sha256"][:16],
                             "xml": hashlib.sha256(env.initial_xml.encode()).hexdigest()[:16]})
    finally:
        env.close()
    print(json.dumps({"attempts": attempts, "pythonhashseed": os.environ.get("PYTHONHASHSEED")}))


def spawn(task, scene, resets, hashseed):
    env = dict(os.environ)
    env.pop("PYTHONHASHSEED", None)
    if hashseed != "unset":
        env["PYTHONHASHSEED"] = hashseed
    done = subprocess.run([sys.executable, __file__, "--child", task, str(scene), str(resets)], env=env,
                          capture_output=True, text=True)
    lines = [line for line in done.stdout.splitlines() if line.startswith("{")]
    if done.returncode or not lines:
        return {"error": (done.stderr or done.stdout)[-400:]}
    return json.loads(lines[-1])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--child", nargs=3, metavar=("TASK", "SCENE", "RESETS"))
    parser.add_argument("--pairs", nargs="+", help="TASK:SCENE ...")
    parser.add_argument("--repeats", type=int, default=3, help="fresh processes per pair and hash-seed setting")
    parser.add_argument("--in-process-resets", type=int, default=3, help="resets inside one process (0 to skip)")
    parser.add_argument("--hashseed", nargs="+", default=["unset", "0"], help="PYTHONHASHSEED settings: 'unset' or a value")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.child:
        child(args.child[0], int(args.child[1]), int(args.child[2]))
        return 0
    pairs = [(p.split(":")[0], int(p.split(":")[1])) for p in args.pairs]
    jobs = [(task, scene, mode, hashseed, 1 if mode == "fresh" else args.in_process_resets)
            for task, scene in pairs for hashseed in args.hashseed
            for mode in (["fresh"] * args.repeats + (["in_process"] if args.in_process_resets else []))]
    with ThreadPoolExecutor(args.workers) as pool:
        outcomes = list(pool.map(lambda j: spawn(j[0], j[1], j[4], j[3]), jobs))
    seen = defaultdict(list)
    for (task, scene, mode, hashseed, _), outcome in zip(jobs, outcomes):
        seen[(task, scene, hashseed)].append((mode, outcome))
    report = []
    for (task, scene, hashseed), runs in seen.items():
        fresh = [a for mode, o in runs if mode == "fresh" and "attempts" in o for a in o["attempts"]]
        every = [a for _, o in runs if "attempts" in o for a in o["attempts"]]
        row = {"task": task, "scene": scene, "pythonhashseed": hashseed, "attempts": len(every),
               "errors": sum("error" in o for _, o in runs),
               "distinct_layouts_fresh": len({(a["layout"], a["style"]) for a in fresh}),
               "distinct_state_hashes_fresh": len({a["state"] for a in fresh}),
               "distinct_state_hashes_all": len({a["state"] for a in every}),
               "layouts": sorted({(a["layout"], a["style"]) for a in every}, key=str)}
        report.append(row)
        print(f"{task:22s} s{scene} hashseed={hashseed:5s} attempts={row['attempts']:2d} errors={row['errors']} "
              f"layouts(fresh)={row['distinct_layouts_fresh']} states(fresh)={row['distinct_state_hashes_fresh']} "
              f"states(all)={row['distinct_state_hashes_all']} {row['layouts']}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"report": report, "raw": [
            {"task": j[0], "scene": j[1], "mode": j[2], "pythonhashseed": j[3], **o} for j, o in zip(jobs, outcomes)]}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
