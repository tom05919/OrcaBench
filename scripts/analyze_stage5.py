#!/usr/bin/env python3
"""Stage 5 tables (docs/stage5_plan.md): plain-policy success per task and backend on the unseen composite tasks, and
subgoal progress from the evaluator's per-step predicates. Reads episode folders only; nothing here calls a model.

  python3 scripts/analyze_stage5.py --root runs/stage5 [--output runs/stage5/analysis.json]
  python3 scripts/analyze_stage5.py --root runs/stage6_ladder [--backends groot groot_u10 groot_u30]
  python3 scripts/analyze_stage5.py --root runs/stage6_ceiling --ceiling     # plain vs sequencer, paired (stage 6)
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from robot_benchmark.tasks.predicates import SEQUENCES  # noqa: E402

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
           "success": bool(result.get("success")), "first_success": None, "subgoals": {}, "final": {}}
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
            row["final"] = {name: state[name] for name in names}
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


def ceiling(root, backends=BACKENDS):
    """Stage 6 ceiling test (docs/stage6_ceiling.md): per task and backend, the pairs (task, scene, policy seed) where
    both the plain reference and the sequencer are usable, with each arm's successes, rescues and harms, and how many
    sequence steps each failed sequencer episode ever reached. Rule fixed before the results: re-prompting can help
    when the sequencer succeeds in at least 2 more paired episodes than plain."""
    def usable(base):
        rows = {}
        for folder in sorted(base.glob("*/seed-*")):
            if (folder / "result.json").exists():
                row = episode(folder)
                if not row["infrastructure_error"] and row["first_success"] != 0:
                    rows[(folder.parent.name, row["scene"], row["policy_seed"])] = row
        return rows

    report = {}
    for backend in backends:
        if not (root / backend / "sequencer").is_dir():
            continue
        plain, sequencer = usable(root / backend / "reference"), usable(root / backend / "sequencer")
        tasks = {}
        for task in sorted({key[0] for key in sequencer}):
            keys = sorted(key for key in sequencer.keys() & plain.keys() if key[0] == task)
            steps = [name for name, _ in SEQUENCES.get(task, [])]
            plain_wins = sum(plain[k]["success"] for k in keys)
            sequencer_wins = sum(sequencer[k]["success"] for k in keys)
            # Where each failed sequencer episode ended: the leading steps true in its last logged state, which is
            # the step the sequencer was prompting (a step true from step 0, like pan_on_stove, does not count early).
            reached = [next((i for i, name in enumerate(steps) if not sequencer[k]["final"].get(name)), len(steps))
                       for k in keys if not sequencer[k]["success"]]
            tasks[task] = {
                "pairs": len(keys), "plain_successes": plain_wins, "sequencer_successes": sequencer_wins,
                "rescues": sum(sequencer[k]["success"] and not plain[k]["success"] for k in keys),
                "harms": sum(plain[k]["success"] and not sequencer[k]["success"] for k in keys),
                "sequence_steps": len(steps), "steps_done_on_sequencer_failures": sorted(reached),
                "unpaired_sequencer_episodes": sum(key[0] == task for key in sequencer.keys() - plain.keys()),
                "reading": "re-prompting can help" if sequencer_wins - plain_wins >= 2 else "not shown",
                "pair_keys": [list(k) for k in keys],
            }
        report[backend] = tasks
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("runs/stage5"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--backends", nargs="+", default=list(BACKENDS),
                        help="subfolders of --root, one per checkpoint")
    parser.add_argument("--ceiling", action="store_true", help="paired plain vs sequencer table (stage 6)")
    args = parser.parse_args()
    if args.ceiling:
        report = ceiling(args.root, args.backends)
        for backend, tasks in report.items():
            print(f"\n{backend}: task, pairs, plain, sequencer, rescues, harms, steps done when the sequencer failed")
            for task, t in tasks.items():
                print(f"  {task:22s} {t['pairs']}  {t['plain_successes']}/{t['pairs']}  "
                      f"{t['sequencer_successes']}/{t['pairs']}  +{t['rescues']} -{t['harms']}  "
                      f"{t['steps_done_on_sequencer_failures']} of {t['sequence_steps']}  {t['reading']}")
        if args.output:
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        return
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
