#!/usr/bin/env python3
"""Analyse the replay benchmark (docs/superpowers/specs/2026-10-24-replay-benchmark-design.md).

  python3 scripts/replay_analyze.py [--out results/w1/replay/summary.json]

Conditions are (model, reasoning level, cost per look, pass); the main runs have level `default` (nothing sent).
- Probe: balanced accuracy (unreadable answers count as wrong) with a 95% bootstrap clustered by recorded run; paired
  differences between conditions on identical probes.
- Sessions: value against the held-out perfect detector, the timer and the oracle on the same recorded runs; the
  primary measure is the paired difference with the perfect detector on the leave-alone tasks at c = 2 s, passes pooled,
  clustered by (task, scene). Adaptation (exploratory) compares policies within a task block.
- Reliability: timeouts, cut-off replies and unreadable replies per condition; reasoning length (manipulation check).
Pilot files (pass 0) are never analysed."""
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
MAIN_MAX_TOKENS = 6144  # the reply limit of the default-condition runs (they did not record stop_reason)
DRAWS = 4000


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def bootstrap(rows, key, cluster, draws=DRAWS, seed=0):
    """Mean of `key` with a 95% interval, resampling clusters."""
    groups = defaultdict(list)
    for r in rows:
        if r.get(key) is not None:
            groups[cluster(r)].append(r[key])
    if not groups:
        return None
    keys, rng, means = sorted(groups, key=str), random.Random(seed), []
    for _ in range(draws):
        sample = [v for k in (rng.choice(keys) for _ in keys) for v in groups[k]]
        means.append(sum(sample) / len(sample))
    means.sort()
    values = [v for vs in groups.values() for v in vs]
    return {"mean": round(sum(values) / len(values), 3), "ci95": [round(means[int(0.025 * draws)], 3),
            round(means[int(0.975 * draws)], 3)], "n": len(values), "clusters": len(keys)}


# ---------------------------------------------------------------------------------------------------------------
# Loading

def probe_rows():
    """Every scored probe answer, tagged with model, level and pass."""
    rows = []
    for path in sorted((OUT / "probe").rglob("pass*/*.jsonl")):
        if path.parent.name == "pass0":
            continue
        effort = path.parent.parent.name.replace("effort-", "") if path.parent.parent.name.startswith("effort-") \
            else "default"
        for r in map(json.loads, path.read_text().splitlines()):
            r.update(effort=effort, pass_no=path.parent.name, model=r["model"])
            rows.append(r)
    return rows


def session_rows():
    """Every finished session episode, tagged with model, level, cost per look, pass and session."""
    rows = []
    for path in sorted((OUT / "sessions").rglob("*.jsonl")):
        if path.name.endswith(".looks.jsonl") or "pass0" in path.parts:
            continue
        rel = path.relative_to(OUT / "sessions").parts  # c2/[effort-x/]pass1/model/pod-sceneN.jsonl
        cost, effort = float(rel[0][1:]), rel[1].replace("effort-", "") if rel[1].startswith("effort-") else "default"
        pass_no = rel[-3]
        for r in map(json.loads, path.read_text().splitlines()):
            if "outcome" in r:
                r.update(effort=effort, cost=cost, pass_no=pass_no, session=f"{pass_no}/{path.stem}")
                rows.append(r)
    return rows


def cut_off(usage, stop_reason, effort):
    """A reply stopped by the reply limit (recorded directly for level runs; inferred for the main runs)."""
    if stop_reason is not None:
        return stop_reason == "max_tokens"
    return effort == "default" and bool(usage) and usage.get("output_tokens", 0) >= MAIN_MAX_TOKENS


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
    return {t["id"]: {"oracle": oracle_value(t, config, cost),
                      "detector": held_out(trajs, t, detector_value, lambda _: range(10, 401, 10), config, cost),
                      "timer": held_out(trajs, t, timer_value, lambda x: range(10, x["steps"] + 1, 10), config, cost)}
            for t in trajs}


# ---------------------------------------------------------------------------------------------------------------
# Probe

def negative_kind(probe, traj, task_type):
    if task_type.get(traj["task"]) != "leave-alone":
        return "unseen task"
    if traj["first_success"] is None:
        return "run never succeeds"
    return "2 s before success" if traj["first_success"] - probe["step"] <= 60 else "10 s before success"


def balanced_accuracy(rows):
    pos = [r["correct"] for r in rows if r["label"]]
    neg = [r["correct"] for r in rows if not r["label"]]
    return (mean(pos) + mean(neg)) / 2 if pos and neg else None


def clustered_ba(rows, draws=DRAWS, seed=0):
    by_run = defaultdict(list)
    for r in rows:
        by_run[r["traj"]].append(r)
    keys, rng, values = sorted(by_run), random.Random(seed), []
    for _ in range(draws):
        sample = [r for k in (rng.choice(keys) for _ in keys) for r in by_run[k]]
        ba = balanced_accuracy(sample)
        if ba is not None:
            values.append(ba)
    values.sort()
    return {"mean": round(balanced_accuracy(rows), 3), "ci95": [round(values[int(0.025 * len(values))], 3),
                                                                 round(values[int(0.975 * len(values))], 3)]}


def paired_ba_difference(rows_a, rows_b, draws=DRAWS, seed=0):
    """Balanced accuracy of A minus B on the probes both answered, resampling recorded runs."""
    a = {r["probe"]: r for r in rows_a}
    b = {r["probe"]: r for r in rows_b}
    shared = sorted(set(a) & set(b))
    by_run = defaultdict(list)
    for p in shared:
        by_run[a[p]["traj"]].append(p)
    keys, rng, diffs = sorted(by_run), random.Random(seed), []
    point = balanced_accuracy([a[p] for p in shared]) - balanced_accuracy([b[p] for p in shared])
    for _ in range(draws):
        sample = [p for k in (rng.choice(keys) for _ in keys) for p in by_run[k]]
        ba_a, ba_b = balanced_accuracy([a[p] for p in sample]), balanced_accuracy([b[p] for p in sample])
        if ba_a is not None and ba_b is not None:
            diffs.append(ba_a - ba_b)
    diffs.sort()
    return {"mean": round(point, 3), "ci95": [round(diffs[int(0.025 * len(diffs))], 3),
                                              round(diffs[int(0.975 * len(diffs))], 3)], "probes": len(shared)}


def probe_summary(rows, trajs, task_type):
    by_id = {t["id"]: t for t in trajs}
    for r in rows:
        r["correct"] = float(r["answer"] is r["label"])
        r["cut_off"] = cut_off(r["usage"], r.get("stop_reason"), r["effort"])
    groups = defaultdict(list)
    for r in rows:
        groups[(r["model"], r["effort"], r["pass_no"])].append(r)
    out = {}
    for (model, effort, pass_no), rs in sorted(groups.items()):
        pos, neg = [r for r in rs if r["label"]], [r for r in rs if not r["label"]]
        kinds = defaultdict(list)
        for r in neg:
            kinds[negative_kind(r, by_id[r["traj"]], task_type)].append(r["answer"] is True)
        thinking = [r["thinking_chars"] for r in rs if r.get("thinking_chars") is not None]
        out[f"{model}|{effort}|{pass_no}"] = {
            "model": model, "effort": effort, "pass": pass_no, "probes": len(rs),
            "unreadable": sum(r["answer"] is None for r in rs), "cut_off": sum(r["cut_off"] for r in rs),
            "balanced_accuracy": clustered_ba(rs),
            "hit_rate_on_done": round(mean(r["correct"] for r in pos), 3),
            "correct_rejection_on_not_done": round(mean(r["correct"] for r in neg), 3),
            "said_done_by_negative_kind": {k: {"said_done": sum(v), "n": len(v)} for k, v in sorted(kinds.items())},
            "median_output_tokens": statistics.median(r["usage"]["output_tokens"] for r in rs if r["usage"]),
            "median_thinking_chars": statistics.median(thinking) if thinking else None,
            "median_seconds": round(statistics.median(r["seconds"] for r in rs), 1),
            "dollars": round(sum(r["dollars"] for r in rs), 3)}
    return out, groups


def probe_contrasts(groups):
    """Within each model: every explicit level against the model's lowest level (pass 1), and the two default passes
    against each other (the noise reference)."""
    out = {}
    lowest = {"off": 0, "minimal": 0, "low": 1, "medium": 2, "high": 3}
    by_model = defaultdict(dict)
    for (model, effort, pass_no), rs in groups.items():
        by_model[model][(effort, pass_no)] = rs
    for model, conds in sorted(by_model.items()):
        levels = sorted((e for e, p in conds if p == "pass1" and e in lowest), key=lowest.get)
        if levels:
            base = levels[0]
            for e in levels[1:] + ["default"]:
                if (e, "pass1") in conds:
                    out[f"{model}|{e} - {base}"] = paired_ba_difference(conds[(e, "pass1")], conds[(base, "pass1")])
        if ("default", "pass1") in conds and ("default", "pass2") in conds:
            out[f"{model}|default pass2 - pass1"] = paired_ba_difference(conds[("default", "pass2")],
                                                                        conds[("default", "pass1")])
    return out


# ---------------------------------------------------------------------------------------------------------------
# Sessions

def typical_first_success(trajs, backend, task, scene):
    """Median first success of a policy on a task over its recorded runs in other scenes (None if none succeed)."""
    xs = [t["first_success"] for t in trajs if (t["backend"], t["task"]) == (backend, task) and t["scene"] != scene
          and t["first_success"] is not None]
    return statistics.median(xs) if xs else None


def block_concordance(rows, trajs, key="first_wait"):
    """Exploratory adaptation check within task blocks: for every pair of policies supervised on the same task in the
    same session, is the one that usually finishes later also given the longer `key`? Returns concordant, discordant
    and tied pairs, the share of blocks where all policies got the same `key`, and the concordant share among untied
    pairs with a 95% interval resampling sessions."""
    blocks = defaultdict(list)
    for r in rows:
        if r.get(key) is not None:
            blocks[(r["session"], r["task"])].append(r)
    per_session, identical, n_blocks = defaultdict(lambda: [0, 0, 0]), 0, 0
    for (session, task), rs in blocks.items():
        typical = {r["backend"]: typical_first_success(trajs, r["backend"], task, r["scene"]) for r in rs}
        if len(rs) < 2:
            continue
        n_blocks += 1
        identical += len({r[key] for r in rs}) == 1
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                if typical[a["backend"]] is None or typical[b["backend"]] is None:
                    continue
                dt, dk = typical[a["backend"]] - typical[b["backend"]], a[key] - b[key]
                slot = 2 if dt == 0 or dk == 0 else 0 if dt * dk > 0 else 1
                per_session[session][slot] += 1
    c, d, t = (sum(v[i] for v in per_session.values()) for i in range(3))
    sessions, rng, draws = sorted(per_session), random.Random(0), []
    for _ in range(DRAWS):
        pick = [per_session[s] for s in (rng.choice(sessions) for _ in sessions)]
        cc, dd = sum(p[0] for p in pick), sum(p[1] for p in pick)
        if cc + dd:
            draws.append(cc / (cc + dd))
    draws.sort()
    return {"concordant": c, "discordant": d, "tied": t, "blocks": n_blocks,
            "blocks_with_identical_value": identical,
            "concordant_share": round(c / (c + d), 3) if c + d else None,
            "ci95": [round(draws[int(0.025 * len(draws))], 3), round(draws[int(0.975 * len(draws))], 3)]
            if draws else None}


def session_summary(rows, trajs, config, task_type):
    by_id = {t["id"]: t for t in trajs}
    cache = {}
    for r in rows:
        if r["cost"] not in cache:
            cache[r["cost"]] = baselines(trajs, config, r["cost"])
        b, t = cache[r["cost"]][r["traj"]], by_id[r["traj"]]
        r.update({f"{k}_value": v for k, v in b.items()})
        r["kind"] = task_type.get(r["task"], "other")
        r["minus_detector"] = None if b["detector"] is None else r["value"] - b["detector"]
        r["minus_timer"] = None if b["timer"] is None else r["value"] - b["timer"]
        r["lag"] = (r["final_step"] - t["first_success"]) / STEPS_PER_SECOND if r["outcome"] == "success" else None
        r["early"] = ((t["first_success"] - r["final_step"]) / STEPS_PER_SECOND
                      if r["outcome"] == "false_done" and t["first_success"] is not None
                      and t["first_success"] > r["final_step"] else None)
        r["run_succeeds"] = t["first_success"] is not None
        r["missed"] = r["outcome"] == "timeout" and r["run_succeeds"]
    groups = defaultdict(list)
    for r in rows:
        groups[(r["model"], r["effort"], r["cost"])].append(r)
    out = {}
    cluster = lambda r: (r["task"], r["scene"])
    for (model, effort, cost), rs in sorted(groups.items()):
        summary = {"model": model, "effort": effort, "cost": cost,
                   "sessions_complete": sum(1 for s in {r["session"] for r in rs}
                                            if sum(r2["session"] == s for r2 in rs) == 21),
                   "sessions": len({r["session"] for r in rs})}
        for kind in ("leave-alone", "unseen", "all"):
            sub = [r for r in rs if kind == "all" or r["kind"] == kind]
            if not sub:
                continue
            succeeding = [r for r in sub if r["run_succeeds"]]
            summary[kind] = {
                "episodes": len(sub), "passes": dict(Counter(r["pass_no"] for r in sub)),
                "outcomes": dict(Counter(r["outcome"] for r in sub)),
                "runs_that_succeed": len(succeeding),
                "success_on_succeeding_runs": round(mean(r["outcome"] == "success" for r in succeeding), 3)
                if succeeding else None,
                "false_done_on_never_succeeding_runs": sum(r["outcome"] == "false_done" for r in sub
                                                           if not r["run_succeeds"]),
                "value": bootstrap(sub, "value", cluster),
                "detector_value": round(mean(r["detector_value"] for r in sub if r["detector_value"] is not None), 3),
                "timer_value": round(mean(r["timer_value"] for r in sub if r["timer_value"] is not None), 3),
                "oracle_value": round(mean(r["oracle_value"] for r in sub), 3),
                "minus_detector": bootstrap(sub, "minus_detector", cluster),
                "minus_timer": bootstrap(sub, "minus_timer", cluster),
                "looks_per_episode": round(mean(r["looks"] for r in sub), 2),
                "median_first_wait": statistics.median([r["first_wait"] for r in sub if r["first_wait"]] or [0]),
                "false_done": sum(r["outcome"] == "false_done" for r in sub),
                "missed_done": sum(r["missed"] for r in sub),
                "invalid": sum(r["outcome"] == "invalid" for r in sub),
                "median_lag_seconds": statistics.median([r["lag"] for r in sub if r["lag"] is not None])
                if any(r["lag"] is not None for r in sub) else None,
                "median_seconds_early": statistics.median([r["early"] for r in sub if r["early"] is not None])
                if any(r["early"] is not None for r in sub) else None,
                "dollars": round(sum(r["dollars"] for r in sub), 3)}
        la = [r for r in rs if r["kind"] == "leave-alone"]
        summary["adaptation_within_blocks"] = {"first_wait": block_concordance(la, trajs, "first_wait"),
                                               "declaration_step": block_concordance(la, trajs, "final_step")}
        out[f"{model}|{effort}|c{cost:g}"] = summary
    return out, groups


def model_differences(groups):
    """Paired by recorded run and pass: model A's value minus model B's, leave-alone tasks, same level and cost."""
    keyed = defaultdict(dict)
    for (model, effort, cost), rows in groups.items():
        for r in rows:
            keyed[(effort, cost, r["pass_no"], r["traj"])][model] = r
    models = sorted({m for (m, _, _) in groups})
    out = {}
    for i, a in enumerate(models):
        for b in models[i + 1:]:
            for effort, cost in sorted({(e, c) for (_, e, c) in groups}):
                pairs = [{"task": v[a]["task"], "scene": v[a]["scene"], "diff": v[a]["value"] - v[b]["value"]}
                         for (e, c, _, _), v in keyed.items()
                         if (e, c) == (effort, cost) and a in v and b in v and v[a]["kind"] == "leave-alone"]
                if pairs:
                    out[f"{a} - {b}|{effort}|c{cost:g}"] = bootstrap(pairs, "diff", lambda p: (p["task"], p["scene"]))
    return out


# ---------------------------------------------------------------------------------------------------------------
# Reliability

def reliability(probe, sessions):
    """Per (model, level, part): attempts that timed out (from the ledger), cut-off and unreadable replies."""
    out = defaultdict(lambda: {"attempts": 0, "timeouts": 0, "replies": 0, "cut_off": 0, "unreadable": 0})
    for line in (OUT / "api_spend.jsonl").read_text().splitlines():
        r = json.loads(line)
        tag = r["tag"]
        if tag.endswith(":http"):
            continue
        part = "probe" if tag.startswith("probe") else "session"
        if part == "probe":
            fields = tag.split(":")
            effort = fields[1] if len(fields) > 2 and fields[1] in ("off", "minimal", "low", "medium", "high",
                                                                    "xhigh", "default") else "default"
        else:
            effort = tag.split("@")[1].split("#")[0] if "@" in tag else "default"
        if ":p0:" in tag:
            continue
        k = f"{r['model']}|{effort}|{part}"
        out[k]["attempts"] += 1
        out[k]["timeouts"] += tag.endswith(":timeout")
    for r in probe:
        k = f"{r['model']}|{r['effort']}|probe"
        out[k]["replies"] += 1
        out[k]["cut_off"] += r["cut_off"]
        out[k]["unreadable"] += r["answer"] is None
    for r in sessions:
        k = f"{r['model']}|{r['effort']}|session"
        for d in r["decisions"]:
            out[k]["replies"] += 1
            out[k]["cut_off"] += cut_off(d.get("usage"), d.get("stop_reason"), r["effort"])
            out[k]["unreadable"] += d["decision"] == "invalid"
    return dict(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "w1" / "replay" / "summary.json")
    args = parser.parse_args()
    selection = json.loads((ROOT / "configs/final/selection.json").read_text())
    task_type = {t: "leave-alone" for t in selection["seen_tasks"]} | {t: "unseen" for t in selection["unseen_tasks"]}
    config = load_config(ROOT / "configs" / "time_pressure.json")
    trajs = load_trajectories(POD_ROOTS)
    probes, sessions = probe_rows(), session_rows()
    probe, probe_groups = probe_summary(probes, trajs, task_type)
    session, session_groups = session_summary(sessions, trajs, config, task_type)
    report = {"recorded_runs": len(trajs), "recorded_runs_that_succeed": sum(t["first_success"] is not None
                                                                             for t in trajs),
              "probe": probe, "probe_contrasts": probe_contrasts(probe_groups), "sessions": session,
              "model_differences": model_differences(session_groups), "reliability": reliability(probes, sessions),
              "spent_dollars": round(sum(json.loads(l)["dollars"] for l in (OUT / "api_spend.jsonl").read_text()
                                         .splitlines() if l.strip()), 2)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {args.out}: {len(probes)} probe answers, {len(sessions)} session episodes, "
          f"${report['spent_dollars']} spent")


if __name__ == "__main__":
    main()
