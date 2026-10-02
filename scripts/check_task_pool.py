"""Build every candidate pool task once in the real simulator and record what the benchmark relies on.

Needs the simulator environment (.venv-sim). For each configs/tasks/*.json it checks that the task builds, the
upstream horizon equals max_steps, the native instruction is nonblank text, the official checker and the
privileged subgoal predicates evaluate, and records the initial proprioception. Nothing is stepped or scored."""
import argparse
import json
from pathlib import Path
import time

from robot_benchmark.adapters.robocasa import RoboCasaEnvironment
from robot_benchmark.cli import PROJECT_ROOT, task_parts, write_json
from robot_benchmark.tasks.predicates import SEQUENCES


def check(path, seed):
    config, _, limits = task_parts(path)
    row = {"task": config["task"], "seed": seed}
    started = time.perf_counter()
    env = None
    try:
        env = RoboCasaEnvironment(config["task"], config["split"], config["camera_size"])
        row["horizon_matches"] = env.horizon == limits.max_steps
        env.reset(seed)
        row["native_instruction"] = env.native_instruction()
        truth = env.evaluate()
        row["evaluate"] = truth
        row["predicate_error"] = truth.get("predicate_error")
        row["sequence_predicates_missing"] = [name for name, _ in SEQUENCES.get(config["task"], []) if name not in truth]
        row["initial_proprio"] = env.sensors()["proprio"]
        row["ok"] = (row["horizon_matches"] and not row["predicate_error"] and not row["sequence_predicates_missing"]
                     and not truth.get("success"))
    except Exception as error:
        row["error"] = f"{type(error).__name__}: {error}"
        row["ok"] = False
    finally:
        if env is not None:
            try:
                env.close()
            except Exception as error:
                row["close_error"] = f"{type(error).__name__}: {error}"
    row["seconds"] = round(time.perf_counter() - started, 1)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--tasks", nargs="*", help="task names; default is the whole pool")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "runs" / "task_pool_check.json")
    args = parser.parse_args()
    paths = sorted((PROJECT_ROOT / "configs" / "tasks").glob("*.json"))
    rows = []
    for path in paths:
        if args.tasks and path.stem not in args.tasks:
            continue
        rows.append(check(path, args.seed))
        print(json.dumps({key: rows[-1].get(key) for key in ("task", "ok", "horizon_matches", "predicate_error", "error", "seconds")}),
              flush=True)
    write_json(args.output, {"seed": args.seed, "tasks": rows, "all_ok": all(row["ok"] for row in rows)})
    return 0 if all(row["ok"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
