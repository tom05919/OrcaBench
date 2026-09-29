"""Separate diagnostic runs, agent failures, and incomplete infrastructure runs."""
import json
import math
from pathlib import Path


def wilson_interval(successes, trials):
    if not trials:
        return None
    z = 1.959963984540054
    p = successes / trials
    scale = 1 + z*z/trials
    center = (p + z*z/(2*trials)) / scale
    half = z * math.sqrt(p*(1-p)/trials + z*z/(4*trials*trials)) / scale
    return [max(0.0, center-half), min(1.0, center+half)]


def _mean(values):
    return sum(values) / len(values) if values else None


def _usage_totals(rows):
    totals = {}
    for _, result in rows:
        for usage in result.get("usage", []):
            if not isinstance(usage, dict):
                continue
            for name, value in usage.items():
                if type(value) in (int, float) and math.isfinite(value):
                    totals[name] = totals.get(name, 0) + value
    return totals


def summarize(root):
    episodes = []
    for manifest_path in sorted(Path(root).rglob("manifest.json")):
        result_path = manifest_path.with_name("result.json")
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("artifact_type") != "episode":
            continue
        result = json.loads(result_path.read_text()) if result_path.exists() else {"status": "infrastructure_error", "success": False, "infrastructure_error": "missing result"}
        episodes.append((manifest, result))
    groups = {}
    for manifest, result in episodes:
        agent = manifest.get("agent") or {}
        key = (manifest["contract_hash"], agent.get("model", "setup_pending"), manifest["kind"])
        group = groups.setdefault(key, [])
        if any(item[0]["seed"] == manifest["seed"] for item in group):
            raise ValueError("duplicate model/contract/seed: summarize one complete attempt set at a time")
        group.append((manifest, result))
    reports = []
    for (contract, model, kind), rows in sorted(groups.items()):
        usable = [(m, r) for m, r in rows if r["status"] != "infrastructure_error"]
        successes = sum(r["success"] for _, r in usable)
        intervals = [interval for _, result in usable for interval in result.get("intervals", [])]
        interval_histogram = {
            str(value): intervals.count(value) for value in sorted(set(intervals))
        }
        reports.append({
            "contract_hash": contract, "model": model, "kind": kind,
            "attempted": len(rows), "usable": len(usable), "infrastructure_errors": len(rows)-len(usable),
            "successes": successes, "success_rate": successes / len(usable) if usable else None,
            "wilson_95": wilson_interval(successes, len(usable)),
            "physical_success_any_count": sum(r.get("physical_success_any", False) for _, r in usable),
            "physical_success_final_count": sum(bool(r.get("physical_success_final")) for _, r in usable),
            "false_completions": sum(r.get("false_completion", False) for _, r in usable),
            "step_budget_exhaustions": sum(r.get("status") == "step_budget_exhausted" for _, r in usable),
            "decision_budget_exhaustions": sum(r.get("status") == "decision_budget_exhausted" for _, r in usable),
            "total_steps": sum(r.get("steps", 0) for _, r in usable),
            "mean_steps": _mean([r.get("steps", 0) for _, r in usable]),
            "total_model_calls": sum(r.get("model_calls", 0) for _, r in usable),
            "mean_model_calls": _mean([r.get("model_calls", 0) for _, r in usable]),
            "total_policy_calls": sum(r.get("policy_calls", 0) for _, r in usable),
            "prompt_submissions": sum(r.get("prompt_submissions", 0) for _, r in usable),
            "prompt_changes": sum(r.get("prompt_changes", 0) for _, r in usable),
            "prompt_restarts": sum(r.get("prompt_restarts", 0) for _, r in usable),
            "discarded_actions": sum(r.get("discarded_actions", 0) for _, r in usable),
            "interval_count": len(intervals),
            "mean_interval": _mean(intervals),
            "interval_histogram": interval_histogram,
            "model_seconds": sum(r.get("model_seconds", 0.0) for _, r in usable),
            "policy_seconds": sum(r.get("policy_seconds", 0.0) for _, r in usable),
            "wall_seconds": sum(r.get("wall_seconds", 0.0) for _, r in usable),
            "token_usage_totals": _usage_totals(usable),
            "seeds": sorted(m["seed"] for m, _ in rows),
            "usable_seeds": sorted(m["seed"] for m, _ in usable),
        })
    # A paired model comparison is only possible when both model results exist
    # and are usable on the same episodes. Never silently fill missing runs.
    comparisons = []
    model_groups = [(key, rows) for key, rows in groups.items() if key[2] == "llm"]
    for i, (left_key, left_rows) in enumerate(model_groups):
        for right_key, right_rows in model_groups[i+1:]:
            if left_key[0] != right_key[0] or left_key[1] == right_key[1]:
                continue
            left = {m["seed"]: r for m, r in left_rows if r["status"] != "infrastructure_error"}
            right = {m["seed"]: r for m, r in right_rows if r["status"] != "infrastructure_error"}
            paired = sorted(left.keys() & right.keys())
            comparisons.append({"models": [left_key[1], right_key[1]], "contract_hash": left_key[0],
                "paired_seeds": paired, "paired_n": len(paired),
                "left_only_success": sum(left[s]["success"] and not right[s]["success"] for s in paired),
                "right_only_success": sum(right[s]["success"] and not left[s]["success"] for s in paired),
                "both_success": sum(left[s]["success"] and right[s]["success"] for s in paired)})
    return {"groups": reports, "paired_comparisons": comparisons,
            "note": "Diagnostic supervisor and ordinary-policy runs are not LLM benchmark results. Intervals describe rollout sampling, not broad task generalization."}
