#!/usr/bin/env python3
"""Descriptive breakdown of LLM sessions by task type (leave-alone vs unseen, `configs/final/selection.json`).

Per model and task type: successes, how many of them scored above 0, mean value, the same-pod always-defer twins'
successes, the held-out fixed rule's mean value on those twins, declaration outcomes, success split by whether
the model rewrote the instruction, for a false "done" whose twin succeeded how many seconds before the twin's
first success it came (or whether the twin had already succeeded by then), and how many steps the model let the
policy run before its first check-in. Descriptive only
(docs/final_experiment.md); the primary result is `scripts/score_time.py`.

  python3 scripts/task_type_breakdown.py runs/final/podA runs/final/podB --scenes 1000 1001 1002 [--config ...]
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from robot_benchmark.time_score import STEPS_PER_SECOND, load_config  # noqa: E402

spec = importlib.util.spec_from_file_location("score_time", ROOT / "scripts" / "score_time.py")
score_time = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score_time)


def breakdown(episodes, config, selection, limits):
    task_type = {t: "leave-alone" for t in selection["seen_tasks"]} | {t: "unseen" for t in selection["unseen_tasks"]}
    _, cells = score_time.score(episodes, config, limits)
    rows = {(agent, r["backend"], r["task"], r["scene"]): r for (agent, _, _), rs in cells.items() for r in rs}
    twins = {(e["root"], e["backend"], e["task"], e["scene_seed"], e["policy_seed"]): e for e in episodes
             if e["kind"] == "baseline_always_defer" and not e["infrastructure_error"]}
    out = {}
    for e in episodes:
        row = rows.get((e["agent"], e["backend"], e["task"], e["scene_seed"]))
        if not e["llm"] or row is None or e["task"] not in task_type:
            continue
        cell = out.setdefault((e["agent"], task_type[e["task"]]), {
            "episodes": 0, "successes": 0, "successes_with_value": 0, "value": 0.0, "twins": 0, "twin_successes": 0,
            "timer_value": [], "declarations": {}, "no_rewrite": [0, 0], "rewrote": [0, 0], "early_seconds": [],
            "twin_done_before_false_declaration": 0, "first_interval": {}})
        cell["episodes"] += 1
        cell["successes"] += row["success"]
        cell["successes_with_value"] += row["value"] > 0
        cell["value"] += row["value"]
        cell["declarations"][row["declaration"]] = cell["declarations"].get(row["declaration"], 0) + 1
        split = cell["rewrote" if row["prompt_changes"] else "no_rewrite"]
        split[0], split[1] = split[0] + row["success"], split[1] + 1
        first = next((d["decision"]["steps"] for d in e["decisions"]
                      if d.get("accepted") and d["decision"].get("op") == "run_policy"), None)
        cell["first_interval"][first] = cell["first_interval"].get(first, 0) + 1
        twin = twins.get((e["root"], e["backend"], e["task"], e["scene_seed"], e["policy_seed"]))
        if twin:
            cell["twins"] += 1
            cell["twin_successes"] += any(twin["success_by_step"])
            twin_first = next((i for i, ok in enumerate(twin["success_by_step"]) if ok), None)
            if row["declaration"] == "false: not reached yet" and twin_first is not None:
                if twin_first > e["steps"]:  # the episode ended at the declaration
                    cell["early_seconds"].append((twin_first - e["steps"]) / STEPS_PER_SECOND)
                else:
                    cell["twin_done_before_false_declaration"] += 1
        if "paired_regret_heldout" in row:
            cell["timer_value"].append(row["paired_regret_heldout"] + row["value"])
    for cell in out.values():
        cell["value"] = round(cell["value"] / cell["episodes"], 3)
        timer = cell.pop("timer_value")
        cell["timer_value"] = round(sum(timer) / len(timer), 3) if timer else None
        early = sorted(cell.pop("early_seconds"))
        cell["early_declarations"] = len(early)
        cell["early_median_seconds"] = early[len(early) // 2] if early else None
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("roots", type=Path, nargs="+")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "time_pressure.json")
    parser.add_argument("--selection", type=Path, default=ROOT / "configs" / "final" / "selection.json")
    parser.add_argument("--scenes", type=int, nargs="+", help="score only these scene seeds")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = breakdown(score_time.load(args.roots, args.scenes), load_config(args.config),
                       json.loads(args.selection.read_text()), score_time.horizons())
    for (model, kind), cell in sorted(result.items()):
        print(f"{model} {kind}: {cell['episodes']} episodes, {cell['successes']} successes "
              f"({cell['successes_with_value']} scored above 0), mean value {cell['value']}; twins "
              f"{cell['twin_successes']}/{cell['twins']} reached success, held-out fixed rule mean value "
              f"{cell['timer_value']}; success without / with a rewrite {cell['no_rewrite'][0]}/{cell['no_rewrite'][1]}"
              f" / {cell['rewrote'][0]}/{cell['rewrote'][1]}; declarations {cell['declarations']}; false \"done\" "
              f"before the twin's first success {cell['early_declarations']} (median "
              f"{cell['early_median_seconds']} s early), after it {cell['twin_done_before_false_declaration']}; "
              f"first check-in after (steps: episodes) {cell['first_interval']}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps([{"model": m, "task_type": k, **c} for (m, k), c in sorted(result.items())],
                                          indent=2) + "\n")


if __name__ == "__main__":
    main()
