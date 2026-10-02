"""Intervention-judgement scorecard: harm, rescue and failure attribution against a privileged reference."""
import json
import math
import random
from pathlib import Path

from .evaluation import _mean, _usage_totals, wilson_interval
from .screening import read_result

GROUPS = ("leave_alone", "needs_help")
BUDGET = ("step_budget_exhausted", "decision_budget_exhausted")
SYSTEM_KINDS = ("llm", "baseline_always_defer", "baseline_reissue")  # llm_development is never scored
LABELS = ("false_completion", "missed_completion", "unnecessary_intervention", "missed_intervention", "executor_or_other")
NOTE = ("The diagnostic reference is privileged and is not a model result. "
        "Scores are conditional on the executor policy and the task set.")


def _jsonl(path):
    """Parse a JSONL log. A truncated final line (interrupted write) is dropped; corruption elsewhere raises."""
    lines = [line for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    rows = [json.loads(line) for line in lines[:-1]]
    if lines:
        try:
            rows.append(json.loads(lines[-1]))
        except json.JSONDecodeError:
            pass
    return rows


def load_scored_episodes(root):
    """Load manifests, results, policy transitions and evaluator success steps; images are never read.
    A missing or unreadable result.json is an infrastructure error; an unreadable manifest raises."""
    episodes = []
    for manifest_path in sorted(Path(root).rglob("manifest.json")):
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("artifact_type") != "episode":
            continue
        folder = manifest_path.parent
        result = read_result(folder / "result.json")
        events = _jsonl(folder / "evaluator" / "events.jsonl")
        episodes.append({"folder": str(folder), "manifest": manifest, "result": result, "transitions": _jsonl(folder / "policy_transitions.jsonl"),
                         "success_steps": [e["step"] for e in events if e.get("success")]})
    return episodes


def attribute_failure(episode, group, paired_reference):
    """Label one failed episode; the first matching rule wins."""
    result = episode["result"]
    if result["status"] == "false_completion":
        return "false_completion"
    if result.get("physical_success_any") and result["status"] in BUDGET:
        return "missed_completion"
    transitions = episode["transitions"]
    steps = [t["step"] for t in transitions[1:2]] + [t["step"] for t in transitions if t["instruction"] != result.get("goal")][:1]
    deviation = min(steps) if steps else None
    if deviation is not None and paired_reference and paired_reference["success_steps"] \
            and deviation < min(paired_reference["success_steps"]):
        return "unnecessary_intervention"
    if group == "needs_help" and deviation is None:
        return "missed_intervention"
    return "executor_or_other"


def _model(manifest):
    return (manifest.get("agent") or {}).get("model") or "setup_pending"


def _usable(episode):
    return episode["result"]["status"] != "infrastructure_error"


def _timing(results):
    """Simulated (physics clock) and real elapsed time per episode. Only episodes that report a field count,
    so a missing field stays unknown. mean_success covers successful episodes only."""
    timing = {}
    for name in ("simulated_seconds", "wall_seconds", "model_seconds", "policy_seconds"):
        values = [r[name] for r in results if name in r]
        won = [r[name] for r in results if name in r and r["success"]]
        timing[name] = {"total": sum(values) if values else None, "mean": _mean(values), "mean_success": _mean(won)}
    return timing


def _stats(episodes):
    usable = [e for e in episodes if _usable(e)]
    rows = [(e["manifest"], e["result"]) for e in usable]
    results = [r for _, r in rows]
    successes = sum(bool(r["success"]) for r in results)
    total = lambda name: sum(r.get(name, 0) for r in results)
    rate = lambda count: count / len(usable) if usable else None
    false_completions = sum(r["status"] == "false_completion" for r in results)
    no_declaration = sum(r["status"] in BUDGET for r in results)
    intervals = [i for r in results for i in r.get("intervals", [])]
    return {"attempted": len(episodes), "infrastructure_errors": len(episodes) - len(usable), "usable": len(usable),
            "successes": successes, "success_rate": successes / len(usable) if usable else None,
            "wilson_95": wilson_interval(successes, len(usable)),
            "false_completions": false_completions, "false_completion_rate": rate(false_completions),
            "no_declaration": no_declaration, "no_declaration_rate": rate(no_declaration),
            "total_model_calls": total("model_calls"), "mean_model_calls": _mean([r.get("model_calls", 0) for r in results]),
            "total_steps": total("steps"), "mean_steps": _mean([r.get("steps", 0) for r in results]),
            "prompt_submissions": total("prompt_submissions"), "prompt_changes": total("prompt_changes"),
            "prompt_restarts": total("prompt_restarts"), "discarded_actions": total("discarded_actions"),
            "interval_histogram": {str(v): intervals.count(v) for v in sorted(set(intervals))},
            "token_usage_totals": _usage_totals(rows), "wall_seconds": total("wall_seconds"),
            "timing": _timing(results)}


def _cell(episodes):
    usable = [e for e in episodes if _usable(e)]
    return [sum(bool(e["result"]["success"]) for e in usable), len(usable)]


def _difference(sign, system, reference, samples, rng_seed):
    """Pooled-rate difference with a seed-clustered percentile bootstrap; sign=+1 is reference - system.
    Only paired clusters (>=1 usable system and >=1 usable reference episode) enter the estimate and the bootstrap."""
    every = system.keys() | reference.keys()
    clusters = sorted(c for c in every if system.get(c, [0, 0])[1] and reference.get(c, [0, 0])[1])
    unpaired = len(every) - len(clusters)
    def estimate(chosen):
        s = [sum(x) for x in zip(*[system.get(c, [0, 0]) for c in chosen])] or [0, 0]
        r = [sum(x) for x in zip(*[reference.get(c, [0, 0]) for c in chosen])] or [0, 0]
        return sign * (r[0] / r[1] - s[0] / s[1]) if s[1] and r[1] else None
    point = estimate(clusters)
    if point is None:
        return {"estimate": None, "ci_95": None, "valid_draws": 0, "unpaired_clusters": unpaired}
    rng = random.Random(rng_seed)
    draws = sorted(d for d in (estimate([rng.choice(clusters) for _ in clusters]) for _ in range(samples)) if d is not None)
    if not draws or len(draws) < samples / 2:
        return {"estimate": point, "ci_95": None, "valid_draws": len(draws), "unpaired_clusters": unpaired}
    # Nearest-rank percentiles on the sorted valid draws: floor for the 2.5% bound, ceil for the 97.5% bound.
    last = len(draws) - 1
    return {"estimate": point, "ci_95": [draws[math.floor(0.025 * last)], draws[math.ceil(0.975 * last)]],
            "valid_draws": len(draws), "unpaired_clusters": unpaired}


def scorecard(episodes, release, bootstrap_samples=2000, rng_seed=0):
    """Score systems by harm (leave_alone) and rescue (needs_help) relative to the paired diagnostic reference."""
    seeds = set(release["reference_policy_seeds"])
    groups = {}
    for task, spec in release["tasks"].items():
        for group in GROUPS:
            for scene in spec[group]:
                if groups.setdefault((task, scene), group) != group:
                    raise ValueError(f"release lists {task} scene seed {scene} in both groups")
    counted, excluded, usable_seen = [], 0, set()
    for e in episodes:
        m = e["manifest"]
        if m.get("contract_hash") != release["contract_hash"]:
            excluded += 1
            continue
        group = groups.get((m["task"], m["scene_seed"]))
        if group and m["policy_seed"] in seeds:
            if _usable(e):
                key = (m["kind"], _model(m), m["task"], m["scene_seed"], m["policy_seed"])
                if key in usable_seen:
                    raise ValueError(f"duplicate episode {key}: only infrastructure-error retries may repeat an episode")
                usable_seen.add(key)
            counted.append((group, e))
    excluded_diagnostic = sum(e["manifest"]["kind"].startswith("diagnostic") and e["manifest"]["kind"] != "diagnostic_reference" for _, e in counted)
    excluded_development = sum(e["manifest"]["kind"] == "llm_development" for _, e in counted)
    reference = {g: [e for grp, e in counted if grp == g and e["manifest"]["kind"] == "diagnostic_reference"] for g in GROUPS}
    pairs = {}
    for _, e in counted:
        m = e["manifest"]
        if m["kind"] == "diagnostic_reference" and _usable(e):
            pairs[(m["task"], m["scene_seed"], m["policy_seed"])] = e
    by_system = {}
    for group, e in counted:
        if e["manifest"]["kind"] in SYSTEM_KINDS:
            by_system.setdefault((e["manifest"]["kind"], _model(e["manifest"])), []).append((group, e))
    def per_cluster(items):
        cells = {}
        for e in items:
            cells.setdefault((e["manifest"]["task"], e["manifest"]["scene_seed"]), []).append(e)
        return {c: _cell(v) for c, v in cells.items()}
    systems = []
    for (kind, model), items in sorted(by_system.items()):
        mine = {g: [e for grp, e in items if grp == g] for g in GROUPS}
        attribution = dict.fromkeys(LABELS, 0)
        for group in GROUPS:
            for e in mine[group]:
                if _usable(e) and not e["result"]["success"]:
                    m = e["manifest"]
                    attribution[attribute_failure(e, group, pairs.get((m["task"], m["scene_seed"], m["policy_seed"])))] += 1
        systems.append({"kind": kind, "model": model, "groups": {g: _stats(mine[g]) for g in GROUPS},
                        "harm": _difference(1, per_cluster(mine["leave_alone"]), per_cluster(reference["leave_alone"]), bootstrap_samples, rng_seed),
                        "rescue": _difference(-1, per_cluster(mine["needs_help"]), per_cluster(reference["needs_help"]), bootstrap_samples, rng_seed),
                        "attribution": attribution})
        if kind == "baseline_always_defer":
            # GPU nondeterminism check: same scene and policy seeds, and always-defer never re-prompts.
            same = [bool(e["result"]["success"]) == bool(pairs[k]["result"]["success"]) for _, e in items if _usable(e)
                    for k in [(e["manifest"]["task"], e["manifest"]["scene_seed"], e["manifest"]["policy_seed"])] if k in pairs]
            systems[-1]["reference_agreement"] = {"paired": len(same), "agreements": sum(same), "rate": sum(same) / len(same) if same else None}
    return {"systems": systems, "reference": {g: _stats(reference[g]) for g in GROUPS},
            "excluded_contract_mismatch": excluded,
            "excluded_diagnostic": excluded_diagnostic, "excluded_development": excluded_development, "note": NOTE}
