"""Label scene seeds from plain-policy screening runs and freeze the release manifest."""
import json
from datetime import datetime, timezone
from pathlib import Path

from .evaluation import wilson_interval

THRESHOLDS = {"trials": 5, "leave_alone_min": 4, "needs_help_max": 1, "rescue_min": 2, "min_per_group": 2, "max_per_group": 4}
KINDS = {"diagnostic_reference": "reference", "diagnostic_retry": "retry", "diagnostic_sequencer": "sequencer"}


def read_result(path):
    """result.json, or an infrastructure-error stand-in if it is missing, unreadable, truncated or malformed."""
    if not path.exists():
        return {"status": "infrastructure_error", "success": False, "infrastructure_error": "missing result"}
    try:
        result = json.loads(path.read_text())
        if not isinstance(result, dict) or not {"status", "success"} <= result.keys():
            raise ValueError("result.json is not an object with status and success")
        return result
    except (OSError, ValueError) as error:
        return {"status": "infrastructure_error", "success": False, "infrastructure_error": f"unreadable result: {type(error).__name__}: {error}"}


def load_episodes(root):
    """Every (manifest, result) episode under root; a missing or unreadable result.json is an infrastructure error."""
    episodes = []
    for manifest_path in sorted(Path(root).rglob("manifest.json")):
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("artifact_type") != "episode":
            continue
        episodes.append((manifest, read_result(manifest_path.with_name("result.json"))))
    return episodes


def _seed_pair(manifest):
    if ("scene_seed" in manifest) != ("policy_seed" in manifest):
        raise ValueError("manifest must carry both scene_seed and policy_seed, or neither (legacy seed)")
    scene, policy = (manifest["scene_seed"], manifest["policy_seed"]) if "scene_seed" in manifest else (manifest.get("seed"), manifest.get("seed"))
    if scene is None:
        raise ValueError("manifest carries no scene_seed/policy_seed or legacy seed")
    return scene, policy


def native_card_performance(episodes, task, policy_seeds):
    """Native-instruction card performance: usable set-A plain-policy reference episodes pooled over all screened scenes."""
    screening, seen, successes = set(policy_seeds), set(), 0
    for manifest, result in episodes:
        if manifest.get("kind") != "diagnostic_reference" or manifest.get("task") != task or result["status"] == "infrastructure_error":
            continue
        key = _seed_pair(manifest)
        if key[1] not in screening:
            continue
        if key in seen:
            raise ValueError(f"duplicate screening episode: task={task} scene_seed={key[0]} policy_seed={key[1]}")
        seen.add(key)
        successes += bool(result["success"])
    if not seen:
        raise ValueError(f"no usable screening reference episodes for {task}; its card stays untested")
    return {"status": "screened", "trials": len(seen), "successes": successes, "success_rate": successes / len(seen),
            "wilson_95": wilson_interval(successes, len(seen)), "policy_seeds": "screening set A",
            "note": "Plain-policy success on the native instruction over all screened scene seeds; not a per-seed estimate."}


def label_seeds(episodes, policy_seeds, thresholds=None):
    """Seed-groups file from episodes whose policy_seed is in policy_seeds (screening set A)."""
    t = {**THRESHOLDS, **(thresholds or {})}
    screening = set(policy_seeds)
    counted, counts = set(), {}
    for manifest, result in episodes:
        kind = KINDS.get(manifest.get("kind"))
        if kind is None:
            continue
        scene, policy = _seed_pair(manifest)
        if policy not in screening:
            continue
        key = (manifest["task"], scene, policy, kind)
        pair = counts.setdefault((manifest["task"], scene), {k: [0, 0] for k in KINDS.values()})[kind]
        if result["status"] == "infrastructure_error":
            continue  # a retried infrastructure error is preserved on disk but never counted
        if key in counted:
            raise ValueError(f"duplicate screening episode: task={key[0]} scene_seed={scene} policy_seed={policy} kind={manifest['kind']}")
        counted.add(key)
        pair[1] += 1
        # Predeclared: a retry rescue counts only if the supervisor actually re-prompted.
        pair[0] += bool(result["success"]) and (kind != "retry" or result.get("prompt_submissions", 0) >= 2)
    tasks = {}
    for (task, scene), pairs in sorted(counts.items()):
        ref, rescued = pairs["reference"], [p for k, p in pairs.items() if k != "reference"]
        if ref[1] < t["trials"]:
            group = "pending"
        elif ref[0] >= t["leave_alone_min"]:
            group = "leave_alone"
        elif ref[0] <= t["needs_help_max"] and any(n >= t["trials"] and s >= t["rescue_min"] for s, n in rescued):
            group = "needs_help"
        else:
            group = "medium"
        tasks.setdefault(task, {})[scene] = {"group": group, **pairs}
    out = {}
    for task, scenes in tasks.items():
        members = {g: sorted(s for s, v in scenes.items() if v["group"] == g) for g in ("leave_alone", "needs_help")}
        qualified = all(len(m) >= t["min_per_group"] for m in members.values())
        out[task] = {"qualified": qualified, "scene_seeds": {str(s): scenes[s] for s in sorted(scenes)},
                     "selected": {g: m[:t["max_per_group"]] if qualified else [] for g, m in members.items()}}
    return {"schema_version": 1, "thresholds": t, "screening_policy_seeds": list(policy_seeds), "tasks": out}


def freeze_release(groups, task_configs, reference_policy_seeds, models, contract_hash, *, allow_fewer=False, max_tasks=10):
    """Release manifest for qualified tasks; reference seeds must be disjoint from the screening seeds.
    Predeclared: if more than max_tasks qualify, keep the top max_tasks by min(selected leave_alone, needs_help)
    descending, then total selected descending, then task name ascending."""
    if "screening_policy_seeds" not in groups:
        raise ValueError("groups must record screening_policy_seeds")
    if not isinstance(reference_policy_seeds, list) or not reference_policy_seeds \
            or any(type(x) is not int for x in reference_policy_seeds) or len(set(reference_policy_seeds)) != len(reference_policy_seeds):
        raise ValueError("reference_policy_seeds must be a nonempty list of unique ints")
    overlap = set(reference_policy_seeds) & set(groups["screening_policy_seeds"])
    if overlap:
        raise ValueError(f"reference policy seeds overlap screening seeds: {sorted(overlap)}")
    qualified = {task: g for task, g in groups["tasks"].items() if g["qualified"]}
    if len(qualified) < 10 and not allow_fewer:
        raise ValueError(f"only {len(qualified)} tasks qualified; need 10 (allow_fewer=True to override)")
    sizes = {task: [len(g["selected"][k]) for k in ("leave_alone", "needs_help")] for task, g in qualified.items()}
    ranked = sorted(qualified, key=lambda task: (-min(sizes[task]), -sum(sizes[task]), task))
    qualified = {task: qualified[task] for task in ranked[:max_tasks]}
    missing = sorted(set(qualified) - set(task_configs))
    if missing:
        raise ValueError(f"missing task configs: {missing}")
    return {"schema_version": 1, "status": "frozen", "created_at": datetime.now(timezone.utc).isoformat(),
            "contract_hash": contract_hash, "models": list(models), "reference_policy_seeds": list(reference_policy_seeds),
            "tasks": {task: {"config": task_configs[task], "leave_alone": g["selected"]["leave_alone"], "needs_help": g["selected"]["needs_help"]}
                      for task, g in qualified.items()}}
