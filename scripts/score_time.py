#!/usr/bin/env python3
"""Score episode folders with the time-charged value (src/robot_benchmark/time_score.py, docs/time_score.md).

For each (backend, task) it finds the best fixed rule: declare at step T, chosen in hindsight over the unsupervised
runs found under the roots. It then scores every LLM episode against it twice:
- against the rule's average value over all those runs;
- **paired**: against the rule applied to the unsupervised runs of the same scene and policy seed under the same
  root (same machine, so the same start state when the stage checked it).

  python3 scripts/score_time.py runs/stage3_remote [more roots] [--call-seconds 0 2.5 5 10] [--output out.json]
"""
import argparse
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from robot_benchmark.time_score import (best_fixed_rules, best_step, load_config, read_episode, rule_runs,  # noqa: E402
                                        rule_source, rule_value, score_episode, supervisor_measures)


def horizons():
    return {p.stem: json.loads(p.read_text())["max_steps"] for p in (ROOT / "configs" / "tasks").glob("*.json")}


def load(roots):
    episodes = []
    for root in roots:
        for result in sorted(Path(root).rglob("result.json")):
            if (result.parent / "manifest.json").exists():
                episode = read_episode(result.parent)
                episode["root"] = str(root)
                episodes.append(episode)
    return episodes


def mean(values):
    return round(statistics.mean(values), 3) if values else None


def score(episodes, config, limits):
    rules, sources = best_fixed_rules(episodes, config, limits), rule_runs(episodes, config)
    unsupervised = {}
    for e in episodes:
        if rule_source(e) == "no_restart" and not e["infrastructure_error"]:
            unsupervised.setdefault((e["root"], e["backend"], e["task"], e["scene_seed"], e["policy_seed"]), []).append(e)
    cells = {}
    for e in episodes:
        if not e["llm"] or e["infrastructure_error"] or e["task"] not in config["tasks"]:
            continue
        rule = rules.get((e["backend"], e["task"], "no_restart"))
        scored, behaviour = score_episode(e, config), supervisor_measures(e)
        row = {"value": scored["value"], "success": scored["success"], "charged_seconds": scored["charged_seconds"],
               "calls": scored["calls"], "declaration": behaviour["declaration"], "lag_seconds": behaviour["lag_seconds"],
               "restarts": behaviour["restarts"], "prompt_changes": behaviour["prompt_changes"],
               "regret": None if rule is None else rule["value"] - scored["value"]}
        twins = unsupervised.get((e["root"], e["backend"], e["task"], e["scene_seed"], e["policy_seed"]), [])
        if rule and twins:
            paired = rule_value(twins, config, e["task"], rule["step"])
            row["paired_rule_value"], row["paired_regret"] = paired, paired - scored["value"]
            # The same comparison with the step chosen without this scene: no hindsight on the paired scene.
            others = [r for r in sources[(e["backend"], e["task"], "no_restart")]
                      if (r["scene_seed"], r["policy_seed"]) != (e["scene_seed"], e["policy_seed"])]
            if others:
                step = best_step(others, config, e["task"], limits[e["task"]])
                row["paired_regret_heldout"] = rule_value(twins, config, e["task"], step) - scored["value"]
        cells.setdefault((e["agent"], e["backend"], e["task"]), []).append(row)
    return rules, cells


def summarize(rules, cells):
    out = {"fixed_rules": [{"backend": b, "task": t, "source": s, **r} for (b, t, s), r in rules.items()],
           "supervisors": []}
    for (agent, backend, task), rows in sorted(cells.items(), key=lambda item: tuple(map(str, item[0]))):
        declarations = {}
        for r in rows:
            declarations[r["declaration"]] = declarations.get(r["declaration"], 0) + 1
        paired = [r["paired_regret"] for r in rows if "paired_regret" in r]
        heldout = [r["paired_regret_heldout"] for r in rows if "paired_regret_heldout" in r]
        out["supervisors"].append({
            "agent": agent, "backend": backend, "task": task, "n": len(rows),
            "success": mean([float(r["success"]) for r in rows]), "value": mean([r["value"] for r in rows]),
            "regret": mean([r["regret"] for r in rows if r["regret"] is not None]),
            "paired_regret": mean(paired), "paired_regret_heldout": mean(heldout), "paired_n": len(paired),
            "charged_seconds": mean([r["charged_seconds"] for r in rows]), "calls": mean([r["calls"] for r in rows]),
            "restarts": mean([r["restarts"] for r in rows]), "prompt_changes": mean([r["prompt_changes"] for r in rows]),
            "declarations": declarations,
            "lag_seconds": mean([r["lag_seconds"] for r in rows if r["lag_seconds"] is not None])})
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("roots", type=Path, nargs="+")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "time_pressure.json")
    parser.add_argument("--call-seconds", type=float, nargs="*", help="sensitivity: rescore with these charges")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    config, limits = load_config(args.config), horizons()
    episodes = load(args.roots)
    report = {"roots": [str(r) for r in args.roots], "call_seconds": config["call_seconds"], "episodes": len(episodes)}
    report.update(summarize(*score(episodes, config, limits)))
    print(f"{len(episodes)} episodes; call charge {config['call_seconds']} s\n\nBest fixed rule (declare at step T, "
          "in hindsight) per backend and task:")
    for r in report["fixed_rules"]:
        print(f"  {r['backend']:15s} {r['task']:26s} {r['source']:22s} n={r['n']:3d}  T={str(r['step']):>5s}  "
              f"value {r['value']:.3f}  held-out {r['loo_value'] if r['loo_value'] is None else round(r['loo_value'], 3)}  "
              f"oracle {r['oracle']:.3f}  reached success {r['reached']:.2f}")
    print("\nLLM supervisors (regret = best fixed rule's value minus the supervisor's; positive is worse):")
    for s in report["supervisors"]:
        print(f"  {s['agent']:18s} {s['backend']:8s} {s['task']:26s} n={s['n']:2d} success {s['success']:.2f} "
              f"value {s['value']:.3f} regret {s['regret']} paired {s['paired_regret']} held-out "
              f"{s['paired_regret_heldout']} (n={s['paired_n']}) "
              f"calls {s['calls']} rewrites {s['prompt_changes']} restarts {s['restarts']} {s['declarations']}")
    if args.call_seconds:
        report["sensitivity"] = {}
        print("\nSensitivity to the call charge (all LLM episodes pooled):")
        for seconds in args.call_seconds:
            variant = {**config, "call_seconds": seconds}
            pooled = [row for rows in score(episodes, variant, limits)[1].values() for row in rows]
            report["sensitivity"][str(seconds)] = {
                "value": mean([r["value"] for r in pooled]),
                "regret": mean([r["regret"] for r in pooled if r["regret"] is not None]),
                "paired_regret": mean([r["paired_regret"] for r in pooled if "paired_regret" in r]),
                "paired_regret_heldout": mean([r["paired_regret_heldout"] for r in pooled
                                               if "paired_regret_heldout" in r])}
            print(f"  {seconds:5.1f} s per call: {report['sensitivity'][str(seconds)]}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
