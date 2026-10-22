#!/usr/bin/env python3
"""Score episode folders with the time-charged value (src/robot_benchmark/time_score.py, docs/time_score.md).

For each (backend, task) and each scripted rule family (no restart; restart every N steps) it finds the best fixed
rule: declare at step T, chosen in hindsight. It then scores every LLM episode:
- **regret**: against the best family's average value (the restart families may come from another machine, so this
  comparison is unpaired);
- **paired**: against the no-restart rule applied to the unsupervised runs of the same scene and policy seed under
  the same root (same machine, so the same start state when the stage checked it), with T chosen in hindsight and,
  for the held-out version, without that scene.

  python3 scripts/score_time.py runs/stage3_remote [more roots] [--call-seconds 0 2.5 5 10] [--output out.json]

`--scenes 1000 1001 1002` drops every episode and session entry of other scenes (twins and baselines included), as
in the final comparison, which excludes scene 1003 for every model (Tom, October 16).
"""
import argparse
import json
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from robot_benchmark.time_score import (best_fixed_rules, best_step, load_config, pooled_rules,  # noqa: E402
                                        read_episode, read_session, rule_runs, rule_source, rule_value,
                                        score_episode, session_summary, supervisor_measures)


def horizons():
    return {p.stem: json.loads(p.read_text())["max_steps"] for p in (ROOT / "configs" / "tasks").glob("*.json")}


def load(roots, scenes=None):
    episodes = []
    for root in roots:
        for result in sorted(Path(root).rglob("result.json")):
            if (result.parent / "manifest.json").exists():
                episode = read_episode(result.parent)
                episode["root"] = str(root)
                if not scenes or episode["scene_seed"] in scenes:
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
        families = [r for (b, t, _), r in rules.items() if (b, t) == (e["backend"], e["task"])]
        best = max(families, key=lambda r: r["value"]) if families else None
        scored, behaviour = score_episode(e, config), supervisor_measures(e)
        row = {"task": e["task"], "scene": e["scene_seed"], "backend": e["backend"],
               "value": scored["value"], "success": scored["success"], "charged_seconds": scored["charged_seconds"],
               "calls": scored["calls"], "declaration": behaviour["declaration"], "lag_seconds": behaviour["lag_seconds"],
               "restarts": behaviour["restarts"], "prompt_changes": behaviour["prompt_changes"],
               "regret": None if best is None else best["value"] - scored["value"]}
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


def clustered_bootstrap(rows, key, draws=5000, seed=0):
    """Mean of `key` and a 95% interval, resampling (task, scene) clusters with replacement."""
    clusters = {}
    for r in rows:
        if r.get(key) is not None:
            clusters.setdefault((r["task"], r["scene"]), []).append(r[key])
    if not clusters:
        return None
    keys, rng, means = sorted(clusters), random.Random(seed), []
    for _ in range(draws):
        sample = [v for k in (rng.choice(keys) for _ in keys) for v in clusters[k]]
        means.append(sum(sample) / len(sample))
    means.sort()
    values = [v for vs in clusters.values() for v in vs]
    return {"mean": round(sum(values) / len(values), 3), "ci95": [round(means[int(0.025 * draws)], 3),
            round(means[int(0.975 * draws)], 3)], "episodes": len(values), "clusters": len(keys)}


def difference(rows_a, rows_b, key, draws=5000, seed=0):
    """Mean of `key` for A minus B, with a 95% interval over (task, scene) clusters present for both."""
    group = lambda rows: {k: [r[key] for r in rows if (r["task"], r["scene"]) == k and r.get(key) is not None]
                          for k in {(r["task"], r["scene"]) for r in rows}}
    a, b = group(rows_a), group(rows_b)
    keys = sorted(k for k in a if a[k] and b.get(k))
    if not keys:
        return None
    rng, diffs = random.Random(seed), []
    for _ in range(draws):
        pick = [rng.choice(keys) for _ in keys]
        sa = [v for k in pick for v in a[k]]
        sb = [v for k in pick for v in b[k]]
        diffs.append(sum(sa) / len(sa) - sum(sb) / len(sb))
    diffs.sort()
    point = (sum(v for k in keys for v in a[k]) / sum(len(a[k]) for k in keys)
             - sum(v for k in keys for v in b[k]) / sum(len(b[k]) for k in keys))
    return {"mean": round(point, 3), "ci95": [round(diffs[int(0.025 * draws)], 3), round(diffs[int(0.975 * draws)], 3)],
            "clusters": len(keys)}


def primary(cells):
    """The pre-declared primary result (docs/final_experiment.md): per model, paired held-out regret with a clustered
    bootstrap interval, and the difference between every pair of models."""
    by_model = {}
    for (agent, _, _), rows in cells.items():
        by_model.setdefault(agent, []).extend(rows)
    out = {"per_model": {m: clustered_bootstrap(rows, "paired_regret_heldout") for m, rows in sorted(by_model.items())},
           "differences": {}}
    models = sorted(by_model)
    for i, a in enumerate(models):
        for b in models[i + 1:]:
            out["differences"][f"{a} - {b}"] = difference(by_model[a], by_model[b], "paired_regret_heldout")
    return out


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
    parser.add_argument("--call-seconds", type=float, nargs="*",
                        help="sensitivity: rescore with this charge for every model")
    parser.add_argument("--scenes", type=int, nargs="+", help="score only these scene seeds")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    config, limits = load_config(args.config), horizons()
    episodes = load(args.roots, args.scenes)
    report = {"roots": [str(r) for r in args.roots], "scenes": args.scenes, "call_seconds": config["call_seconds"],
              "episodes": len(episodes)}
    rules, cells = score(episodes, config, limits)
    report.update(summarize(rules, cells))
    report["primary"] = primary(cells)
    print(f"{len(episodes)} episodes; seconds per call {config['call_seconds']}\n\nBest fixed rule (declare at step T, "
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
    print("\nPrimary (paired held-out regret; positive means the fixed rule did better):")
    for model, result in report["primary"]["per_model"].items():
        print(f"  {model}: {result}")
    for pair, result in report["primary"]["differences"].items():
        print(f"  {pair}: {result}")
    sessions = sorted(path for root in args.roots for path in Path(root).rglob("session.jsonl"))
    if sessions:
        rules = best_fixed_rules(episodes, config, limits)
        _, pooled = pooled_rules(episodes, config, limits)
        report["sessions"], totals = [], {}
        print("\nSessions (per anonymous policy label; learning < 0 means regret fell in the second half):")
        for path in sessions:
            entries = [e for e in read_session(path) if not args.scenes or e["scene_seed"] in args.scenes]
            if not entries:
                continue
            model = next((e["episode"]["agent"] for e in entries if e["episode"] and e["episode"]["llm"]), None)
            summary = session_summary(entries, config, rules, pooled)
            report["sessions"].append({"path": str(path), "model": model, **summary})
            for label, p in summary["policies"].items():
                print(f"  {path.parent.name:14s} {model} {label} ({p['backend']}) n={p['n']} value {p['value']:.3f} "
                      f"regret {p['regret']} pooled-rule value {p['pooled_rule_value']} learning {p['learning']} "
                      f"calls {p['calls']} interval {p['median_interval']} restarts {p['restarts']}")
                totals.setdefault((model, p["backend"]), []).append(p)
            if summary["unfinished"]:
                print(f"  {path.parent.name:14s} {summary['unfinished']} episode(s) never finished (no result.json)")
        report["session_totals"] = []
        print("\nAcross sessions, per model and policy:")
        for (model, backend), rows in sorted(totals.items(), key=lambda item: tuple(map(str, item[0]))):
            weighted = lambda key: mean([p[key] for p in rows for _ in range(p["n"]) if p[key] is not None])
            row = {"model": model, "backend": backend, "episodes": sum(p["n"] for p in rows),
                   "value": weighted("value"), "regret": weighted("regret"),
                   "pooled_rule_value": weighted("pooled_rule_value"), "learning": mean(
                       [p["learning"] for p in rows if p["learning"] is not None])}
            report["session_totals"].append(row)
            print(f"  {model} {backend}: {row}")
    if args.call_seconds:
        report["sensitivity"] = {}
        print("\nSensitivity to the call charge (all LLM episodes pooled):")
        for seconds in args.call_seconds:
            variant = {**config, "call_seconds": {model: seconds for model in config["call_seconds"]}}
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
