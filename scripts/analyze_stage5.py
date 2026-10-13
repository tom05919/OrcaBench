#!/usr/bin/env python3
"""Stage 5 tables (docs/stage5_plan.md): plain-policy success per task and backend on the unseen composite tasks, and
subgoal progress from the evaluator's per-step predicates. Reads episode folders only; nothing here calls a model.

  python3 scripts/analyze_stage5.py --root runs/stage5 [--output runs/stage5/analysis.json]
  python3 scripts/analyze_stage5.py --root runs/stage6_ladder [--backends groot groot_u10 groot_u30]
"""
import argparse
import json
import math
from pathlib import Path

TRIGGERS = ("ice_out_of_bowl", "pan_off_stove")  # clock triggers in tasks/predicates.py, not task progress
BACKENDS = ("groot", "groot_pretrain", "groot_u10", "groot_u30")  # those without a folder under --root are skipped


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    centre, half = p + z * z / (2 * n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((centre - half) / (1 + z * z / n), 3), round((centre + half) / (1 + z * z / n), 3)]


def episode(folder):
    """One episode: outcome, first success step, and for each predicate that is false at step 0, its first true step."""
    result = json.loads((folder / "result.json").read_text())
    row = {"scene": result["scene_seed"], "policy_seed": result["policy_seed"], "steps": result.get("steps"),
           "status": result["status"], "infrastructure_error": bool(result.get("infrastructure_error")),
           "success": bool(result.get("success")), "first_success": None, "subgoals": {}}
    events = folder / "evaluator" / "events.jsonl"
    if events.exists():
        initial = None
        for line in events.read_text().splitlines():
            if not line.strip():
                continue
            state = json.loads(line)
            names = [k for k, v in state.items() if k not in ("step", "success", *TRIGGERS) and isinstance(v, bool)]
            if initial is None:
                initial = {name: state[name] for name in names}
                row["subgoals"] = {name: None for name in names if not initial[name]}
            if state.get("success") and row["first_success"] is None:
                row["first_success"] = state["step"]
            for name in row["subgoals"]:
                if state.get(name) and row["subgoals"][name] is None:
                    row["subgoals"][name] = state["step"]
    return row


def reading(successes, usable, progress, has_predicates):
    """The pre-declared reading of stage5_plan.md, per task and backend (thresholds stated for 4 episodes:
    3 of 4, at most 1 of 4, 2 of 4; as fractions here)."""
    if usable < 4:
        return f"incomplete ({usable} usable)"
    if successes >= 0.75 * usable:
        return "leave-alone candidate"
    if has_predicates and successes <= 0.25 * usable and any(count >= 0.5 * usable for count in progress.values()):
        return "re-prompting candidate"
    if successes == 0 and not any(progress.values()):
        return "unlikely to be helped by re-prompting" if has_predicates else "no success (no subgoal data)"
    return "mixed"


def analyze(root, backends=BACKENDS):
    report = {}
    for backend in backends:
        base = root / backend / "reference"
        if not base.is_dir():
            continue
        tasks = {}
        for task_dir in sorted(p for p in base.glob("*") if p.is_dir()):
            rows = [episode(f) for f in sorted(task_dir.glob("seed-*")) if (f / "result.json").exists()]
            # A scene whose checker is already true at step 0 measures nothing (RecycleBottlesByType at scene 1000,
            # found by the build check before any episode ran): reported, never counted.
            solved_at_start = [r for r in rows if r["first_success"] == 0]
            usable = [r for r in rows if not r["infrastructure_error"] and r["first_success"] != 0]
            wins = [r for r in usable if r["success"]]
            names = sorted({n for r in usable for n in r["subgoals"]})
            progress = {n: sum(r["subgoals"].get(n) is not None for r in usable) for n in names}
            tasks[task_dir.name] = {
                "attempted": len(rows), "usable": len(usable), "successes": len(wins),
                "solved_at_start": len(solved_at_start),
                "first_success_steps": sorted(r["first_success"] for r in wins if r["first_success"] is not None),
                "subgoal_episodes_reached": progress,
                "subgoal_first_steps": {n: sorted(r["subgoals"][n] for r in usable if r["subgoals"].get(n) is not None)
                                        for n in names},
                "reading": reading(len(wins), len(usable), progress, bool(names)),
                "episodes": rows,
            }
        k = sum(t["successes"] for t in tasks.values())
        n = sum(t["usable"] for t in tasks.values())
        report[backend] = {"tasks": tasks, "successes": k, "usable": n, "wilson_95": wilson(k, n),
                           "solved_at_start": sum(t["solved_at_start"] for t in tasks.values()),
                           "infrastructure_errors": sum(t["attempted"] - t["usable"] - t["solved_at_start"]
                                                        for t in tasks.values())}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("runs/stage5"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--backends", nargs="+", default=list(BACKENDS),
                        help="subfolders of --root, one per checkpoint")
    args = parser.parse_args()
    report = analyze(args.root, args.backends)
    for backend, data in report.items():
        print(f"\n{backend}: {data['successes']}/{data['usable']} solved, 95% {data['wilson_95']}, "
              f"{data['infrastructure_errors']} infrastructure errors, {data['solved_at_start']} solved at start")
        for task, t in data["tasks"].items():
            progress = ", ".join(f"{n} {c}/{t['usable']}" for n, c in t["subgoal_episodes_reached"].items())
            print(f"  {task:22s} {t['successes']}/{t['usable']}  first success {t['first_success_steps']}  "
                  f"{t['reading']}{'  | ' + progress if progress else ''}")
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
