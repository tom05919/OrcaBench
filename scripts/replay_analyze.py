#!/usr/bin/env python3
"""Analyse the replay benchmark (docs/superpowers/specs/2026-10-24-replay-benchmark-design.md).

  python3 scripts/replay_analyze.py [--out results/w1/replay/summary.json]

Part 1 (probe): per model and pass, balanced accuracy (unreadable answers count as wrong) with a 95% bootstrap
interval clustered by recorded run. Part 2 (sessions): per model, cost per look and pass, the value against the
held-out perfect detector, the timer and the oracle on the same recorded runs; the primary measure is the paired
difference with the perfect detector on the leave-alone tasks at c = 2 s, both passes pooled, clustered by
(task, scene). Everything else is descriptive."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from robot_benchmark.replay_bench import FRAME_STEP, load_trajectories  # noqa: E402
from robot_benchmark.time_score import STEPS_PER_SECOND, load_config, score_episode  # noqa: E402

POD_ROOTS = {"podC": ROOT / "runs/addon/podC/always_defer", "podB": ROOT / "runs/final/podB/always_defer"}
OUT = ROOT / "runs" / "replay"


def bootstrap(rows, key, cluster, draws=4000, seed=0):
    """Mean of `key` with a 95% interval, resampling clusters."""
    groups = defaultdict(list)
    for r in rows:
        if r.get(key) is not None:
            groups[cluster(r)].append(r[key])
    if not groups:
        return None
    keys, rng, means = sorted(groups), random.Random(seed), []
    for _ in range(draws):
        sample = [v for k in (rng.choice(keys) for _ in keys) for v in groups[k]]
        means.append(sum(sample) / len(sample))
    means.sort()
    values = [v for vs in groups.values() for v in vs]
    return {"mean": round(sum(values) / len(values), 3), "ci95": [round(means[int(0.025 * draws)], 3),
            round(means[int(0.975 * draws)], 3)], "n": len(values), "clusters": len(keys)}


# ---------------------------------------------------------------------------------------------------------------
# Baselines on one recorded run (same look accounting as a model: every reply is a look)

def declared_value(traj, step, looks, looks_from_trigger, config, cost):
    """Value of declaring at `step` after `looks` looks, scored like a model episode (story limit included)."""
    episode = {"task": traj["task"], "steps": step, "llm": True, "agent": "rule", "calls": looks,
               "success": traj["success_by_step"][min(step, len(traj["success_by_step"]) - 1)],
               "first_true": traj["first_true"], "logged": traj["logged"],
               "decisions": [{"step_before": s} for s in looks_from_trigger]}
    return score_episode(episode, {**config, "call_seconds": {"rule": cost}})["value"]


def detector_value(traj, k, config, cost):
    """Perfect perception, a fixed look every k steps: looks at 0, k, 2k, ... (and the final step); declares at the
    first look where the checker is true."""
    steps = list(range(0, traj["steps"], k)) + [traj["steps"]]
    for i, s in enumerate(steps):
        if traj["success_by_step"][min(s, len(traj["success_by_step"]) - 1)]:
            return declared_value(traj, s, i + 1, steps[:i + 1], config, cost)
    return 0.0


def timer_value(traj, t, config, cost):
    """Declare at step t without looking in between: a look at step 0 and the declaration."""
    s = min(t, traj["steps"])
    return declared_value(traj, s, 2, [0, s], config, cost)


def oracle_value(traj, config, cost):
    if traj["first_success"] is None:
        return 0.0
    s = min(traj["steps"], -(-traj["first_success"] // FRAME_STEP) * FRAME_STEP)
    return declared_value(traj, s, 2, [0, s], config, cost)


def held_out(trajs, target, rule, grid, config, cost):
    """The rule's value on `target` with its parameter chosen on the same policy and task in other scenes."""
    others = [t for t in trajs if (t["backend"], t["task"]) == (target["backend"], target["task"])
              and t["scene"] != target["scene"]]
    if not others:
        return None
    best = max(grid(target), key=lambda p: (sum(rule(t, p, config, cost) for t in others), -p))
    return rule(target, best, config, cost)


def baselines(trajs, config, cost):
    out = {}
    for t in trajs:
        out[t["id"]] = {
            "oracle": oracle_value(t, config, cost),
            "detector": held_out(trajs, t, detector_value, lambda _: range(10, 401, 10), config, cost),
            "timer": held_out(trajs, t, timer_value, lambda x: range(10, x["steps"] + 1, 10), config, cost)}
    return out


# ---------------------------------------------------------------------------------------------------------------

def probe_summary(task_type):
    out = {}
    for path in sorted((OUT / "probe").glob("pass*/*.jsonl")):
        if path.parent.name == "pass0":
            continue  # pilot
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        for r in rows:
            r["correct"] = float(r["answer"] is r["label"])
            r["kind"] = task_type.get(r["traj"].split("/")[2], "other")
            r["band"] = "positive" if r["label"] else "negative"
        pos, neg = [r for r in rows if r["label"]], [r for r in rows if not r["label"]]
        hit, rej = bootstrap(pos, "correct", lambda r: r["traj"]), bootstrap(neg, "correct", lambda r: r["traj"])
        # Balanced accuracy with a clustered interval: resample runs, average the two rates in each draw.
        by_run = defaultdict(list)
        for r in rows:
            by_run[r["traj"]].append(r)
        keys, rng, draws = sorted(by_run), random.Random(0), []
        for _ in range(4000):
            sample = [r for k in (rng.choice(keys) for _ in keys) for r in by_run[k]]
            p = [r["correct"] for r in sample if r["label"]]
            n = [r["correct"] for r in sample if not r["label"]]
            if p and n:
                draws.append((sum(p) / len(p) + sum(n) / len(n)) / 2)
        draws.sort()
        out[f"{path.stem}|{path.parent.name}"] = {
            "probes": len(rows), "unreadable": sum(r["answer"] is None for r in rows),
            "balanced_accuracy": {"mean": round((hit["mean"] + rej["mean"]) / 2, 3),
                                  "ci95": [round(draws[int(0.025 * len(draws))], 3),
                                           round(draws[int(0.975 * len(draws))], 3)]},
            "hit_rate_on_done": hit, "correct_rejection_on_not_done": rej,
            "false_done_by_kind": {k: round(1 - statistics.mean(r["correct"] for r in neg if r["kind"] == k), 3)
                                   for k in sorted({r["kind"] for r in neg})},
            "false_done_2s_before_success": round(1 - statistics.mean(
                [r["correct"] for r in neg if r["step"] >= 0 and r["probe"] in near_probes(rows)] or [1]), 3),
            "dollars": round(sum(r["dollars"] for r in rows), 3)}
    return out


def near_probes(rows):
    """Negative probes taken just outside the ambiguity band (the later of a successful run's two negatives)."""
    latest = {}
    for r in rows:
        if not r["label"]:
            latest.setdefault(r["traj"], []).append(r)
    return {max(rs, key=lambda r: r["step"])["probe"] for rs in latest.values() if len(rs) == 2}


def session_summary(trajs, config, task_type):
    by_id = {t["id"]: t for t in trajs}
    groups = defaultdict(list)
    for path in sorted((OUT / "sessions").glob("c*/pass*/*/*.jsonl")):
        cost_dir, pass_dir, model = path.parts[-4], path.parts[-3], path.parts[-2]
        if pass_dir == "pass0":
            continue  # pilot
        for line in path.read_text().splitlines():
            r = json.loads(line)
            if "outcome" in r:
                r["pass"], r["kind"] = pass_dir, task_type.get(r["task"], "other")
                groups[(model, cost_dir)].append(r)
    cache, out = {}, {}
    for (model, cost_dir), rows in sorted(groups.items()):
        cost = float(cost_dir[1:])
        if cost not in cache:
            cache[cost] = baselines(trajs, config, cost)
        base = cache[cost]
        for r in rows:
            b = base[r["traj"]]
            r.update({f"{k}_value": v for k, v in b.items()})
            r["minus_detector"] = None if b["detector"] is None else r["value"] - b["detector"]
            r["minus_timer"] = None if b["timer"] is None else r["value"] - b["timer"]
            t = by_id[r["traj"]]
            r["lag"] = (r["final_step"] - t["first_success"]) / STEPS_PER_SECOND if r["outcome"] == "success" else None
            r["missed"] = r["outcome"] == "timeout" and t["first_success"] is not None
        summary = {}
        for kind in ("leave-alone", "unseen", "all"):
            sub = [r for r in rows if kind == "all" or r["kind"] == kind]
            if not sub:
                continue
            cluster = lambda r: (r["task"], r["scene"])
            summary[kind] = {
                "episodes": len(sub), "passes": dict(Counter(r["pass"] for r in sub)),
                "outcomes": dict(Counter(r["outcome"] for r in sub)),
                "recorded_runs_that_succeed": sum(by_id[r["traj"]]["first_success"] is not None for r in sub),
                "value": bootstrap(sub, "value", cluster),
                "detector_value": round(statistics.mean(r["detector_value"] for r in sub
                                                        if r["detector_value"] is not None), 3),
                "timer_value": round(statistics.mean(r["timer_value"] for r in sub if r["timer_value"] is not None), 3),
                "oracle_value": round(statistics.mean(r["oracle_value"] for r in sub), 3),
                "minus_detector": bootstrap(sub, "minus_detector", cluster),
                "minus_timer": bootstrap(sub, "minus_timer", cluster),
                "looks_per_episode": round(statistics.mean(r["looks"] for r in sub), 2),
                "median_first_wait": statistics.median([r["first_wait"] for r in sub if r["first_wait"]] or [0]),
                "false_done": sum(r["outcome"] == "false_done" for r in sub),
                "missed_done": sum(r["missed"] for r in sub),
                "median_lag_seconds": statistics.median([r["lag"] for r in sub if r["lag"] is not None] or [None])
                if any(r["lag"] is not None for r in sub) else None,
                "dollars": round(sum(r["dollars"] for r in sub), 3)}
        summary["adaptation_leave_alone"] = adaptation([r for r in rows if r["kind"] == "leave-alone"], trajs)
        out[f"{model}|{cost_dir}"] = summary
    return out, groups


def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    if len(xs) < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 3) if den else None


def adaptation(rows, trajs):
    """Exploratory: does the first wait follow how fast that policy finishes that task (median first success over its
    runs in other scenes)? Spearman over episodes, and the same for the declaration step."""
    xs, waits, declares = [], [], []
    for r in rows:
        others = [t["first_success"] for t in trajs if (t["backend"], t["task"]) == (r["backend"], r["task"])
                  and t["scene"] != r["scene"] and t["first_success"] is not None]
        if others and r["first_wait"]:
            xs.append(statistics.median(others))
            waits.append(r["first_wait"])
            declares.append(r["final_step"])
    return {"episodes": len(xs), "spearman_first_wait": spearman(xs, waits),
            "spearman_declaration_step": spearman(xs, declares)}


def model_differences(groups):
    """Paired by recorded run: model A's value minus model B's at the same cost and pass (descriptive)."""
    out = {}
    keyed = defaultdict(dict)
    for (model, cost_dir), rows in groups.items():
        for r in rows:
            keyed[(cost_dir, r["pass"], r["traj"])][model] = r
    models = sorted({m for (m, _) in groups})
    for i, a in enumerate(models):
        for b in models[i + 1:]:
            for cost_dir in sorted({c for (_, c) in groups}):
                pairs = [{"task": v[a]["task"], "scene": v[a]["scene"], "kind": v[a]["kind"],
                          "diff": v[a]["value"] - v[b]["value"]}
                         for (c, _, _), v in keyed.items() if c == cost_dir and a in v and b in v]
                la = [p for p in pairs if p["kind"] == "leave-alone"]
                if la:
                    out[f"{a} - {b} | {cost_dir} | leave-alone"] = bootstrap(la, "diff", lambda p: (p["task"], p["scene"]))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "w1" / "replay" / "summary.json")
    args = parser.parse_args()
    selection = json.loads((ROOT / "configs/final/selection.json").read_text())
    task_type = {t: "leave-alone" for t in selection["seen_tasks"]} | {t: "unseen" for t in selection["unseen_tasks"]}
    config = load_config(ROOT / "configs" / "time_pressure.json")
    trajs = load_trajectories(POD_ROOTS)
    sessions, groups = session_summary(trajs, config, task_type)
    report = {"recorded_runs": len(trajs), "probe": probe_summary(task_type), "sessions": sessions,
              "model_differences": model_differences(groups),
              "spent_dollars": round(sum(json.loads(l)["dollars"] for l in (OUT / "api_spend.jsonl").read_text()
                                         .splitlines() if l.strip()), 3)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
