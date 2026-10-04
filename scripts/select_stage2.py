"""Pick the stage 2 harm-test episodes from the plain-policy results, by a rule fixed before the results exist.

Rule: for each task, take the first PER_TASK (scene seed, policy seed) pairs, in ascending order, at which the plain
policy succeeded. Failed pairs, infrastructure errors and tasks with no success are not selected. The rule reads
outcomes only to find leave-alone episodes (the plain policy solved them), never to choose which harm to look at.
Writes the selection as JSON and prints one "task scene policy" line per selected pair."""
import argparse
import json
from pathlib import Path

from robot_benchmark.scorecard import load_scored_episodes


def select(rows, per_task):
    """rows: (task, scene_seed, policy_seed, success). Returns {task: [(scene_seed, policy_seed), ...]}."""
    chosen = {}
    for task, scene, policy, success in sorted(rows):
        if success and len(chosen.get(task, ())) < per_task:
            chosen.setdefault(task, []).append((scene, policy))
    return chosen


def plain_rows(root):
    latest = {}
    for episode in load_scored_episodes(root):
        m = episode["manifest"]
        if m.get("kind") == "diagnostic_reference" and episode["result"]["status"] != "infrastructure_error":
            latest[(m["task"], m["scene_seed"], m["policy_seed"])] = bool(episode["result"]["success"])
    return [(*key, success) for key, success in latest.items()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--per-task", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = plain_rows(args.reference_root)
    chosen = select(rows, args.per_task)
    rates = {}
    for task, _, _, success in rows:
        wins, total = rates.get(task, (0, 0))
        rates[task] = (wins + success, total + 1)
    args.output.write_text(json.dumps({
        "rule": f"per task, first {args.per_task} (scene, policy) pairs in ascending order where the plain policy succeeded",
        "plain_successes_of_trials": {task: list(rate) for task, rate in sorted(rates.items())},
        "selected": [{"task": task, "scene_seed": scene, "policy_seed": policy}
                     for task, pairs in sorted(chosen.items()) for scene, policy in pairs],
    }, indent=2) + "\n")
    for task, pairs in sorted(chosen.items()):
        for scene, policy in pairs:
            print(task, scene, policy)


if __name__ == "__main__":
    main()
