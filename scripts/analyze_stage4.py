"""Stage 4 analysis, as fixed in docs/stage4_plan.md. Reads episode folders only; nothing here is a benchmark score.

  python scripts/analyze_stage4.py --root runs/stage4_remote --output runs/stage4_remote/analysis.json

Per failure pair (failures.tsv): an arm's episode is usable when it is not an infrastructure error and started from
the plain run's step-0 state. The failure is reproducible when always_defer also fails. A rescue is a success of a
reissue arm or of Opus on a reproducible-failure pair; an Opus rescue is attributed with the replays (exact fails:
not reproducible; else native_text succeeds: restart timing; else no_interruption succeeds: intervals or
declaration; else: wording)."""
import argparse
import json
from collections import Counter
from pathlib import Path

from robot_benchmark.scorecard import load_scored_episodes

ARMS = ("always_defer", "reissue_50", "reissue", "reissue_200", "opus-5-5")
REPLAYS = ("replay_exact", "replay_native_text", "replay_no_interruption")
PRICES = {"input": 4e-6, "output": 20e-6}  # Opus 5.5 list prices per token


def start_state(folder):
    try:
        with open(Path(folder) / "evaluator" / "states.jsonl") as stream:
            return json.loads(stream.readline())["state_sha256"]
    except (OSError, ValueError, KeyError):
        return None


def load(root):
    """Latest episode per (task, scene, policy seed) in a root."""
    out = {}
    if not Path(root).is_dir():
        return out
    for e in load_scored_episodes(root):
        m, r = e["manifest"], e["result"]
        key = (m["task"], m["scene_seed"], m["policy_seed"])
        if key not in out or m["created_at"] > out[key]["created_at"]:
            out[key] = {"created_at": m["created_at"], "folder": e["folder"], "result": r,
                        "state": start_state(e["folder"])}
    return out


def outcome(episode, state):
    if episode is None:
        return "missing"
    r = episode["result"]
    if r["status"] == "infrastructure_error" or episode["state"] != state:
        return "invalid"
    if r["success"]:
        return "success"
    if r.get("physical_success_any") and not r.get("physical_success_final"):
        return "lost_success"
    return "declared_early" if r["status"] == "false_completion" and r.get("physical_success_any") is False \
        and r["steps"] < budget(episode) - 15 else "failed"


def budget(episode):
    task = json.loads((Path(episode["folder"]) / "manifest.json").read_text())["task"]
    return json.loads((Path(__file__).resolve().parents[1] / "configs" / "tasks" / f"{task}.json").read_text())["max_steps"]


def attribute(replays):
    if replays["replay_exact"] != "success":
        return "not_reproducible"
    if replays["replay_native_text"] == "success":
        return "restart_timing"
    if replays["replay_no_interruption"] == "success":
        return "intervals_or_declaration"
    return "wording"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plain = load(args.root / "reference")
    arms = {arm: load(args.root / arm) for arm in ARMS + REPLAYS}
    pairs = [line.split() for line in (args.root / "failures.tsv").read_text().splitlines() if line.strip()]
    rows, usage = [], Counter()
    for task, scene, policy, state in pairs:
        key = (task, int(scene), int(policy))
        row = {"task": task, "scene": key[1], "policy_seed": key[2],
               "plain_steps": plain[key]["result"]["steps"] if key in plain else None}
        for arm in ARMS + REPLAYS:
            row[arm] = outcome(arms[arm].get(key), state)
        opus = arms["opus-5-5"].get(key)
        if opus:
            r = opus["result"]
            row.update(opus_calls=r["model_calls"], opus_changes=r.get("prompt_changes", 0),
                       opus_restarts=r.get("prompt_restarts", 0), opus_status=r["status"], opus_steps=r["steps"],
                       opus_rejected=r.get("rejected_decisions", 0))
            for u in r.get("usage") or []:
                usage["input"] += u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) \
                    + u.get("cache_read_input_tokens", 0)
                usage["output"] += u.get("output_tokens", 0)
        row["reproducible_failure"] = row["always_defer"] in ("failed", "declared_early", "lost_success")
        row["restart_rescues"] = [a for a in ("reissue_50", "reissue", "reissue_200") if row[a] == "success"]
        row["opus_rescue"] = row["opus-5-5"] == "success"
        if row["opus_rescue"]:
            row["opus_attribution"] = attribute({r: row[r] for r in REPLAYS})
        rows.append(row)
    usable = [r for r in rows if r["reproducible_failure"]]
    summary = {
        "pairs": len(rows),
        "defer_outcomes": dict(Counter(r["always_defer"] for r in rows)),
        "reproducible_failure_pairs": len(usable),
        "restart_rescues": {a: sum(a in r["restart_rescues"] for r in usable) for a in ("reissue_50", "reissue", "reissue_200")},
        "restart_arm_outcomes": {a: dict(Counter(r[a] for r in usable)) for a in ("reissue_50", "reissue", "reissue_200")},
        "opus_outcomes": dict(Counter(r["opus-5-5"] for r in usable)),
        "opus_rescues": sum(r["opus_rescue"] for r in usable),
        "opus_attribution": dict(Counter(r["opus_attribution"] for r in usable if r["opus_rescue"])),
        "opus_changed_prompt": sum(1 for r in usable if r.get("opus_changes")),
        "opus_restarted_same_prompt": sum(1 for r in usable if r.get("opus_restarts")),
        "opus_tokens": dict(usage),
        "opus_cost_usd_list_price": round(usage["input"] * PRICES["input"] + usage["output"] * PRICES["output"], 2),
        "plain_episodes": len(plain), "plain_successes": sum(e["result"]["success"] for e in plain.values()),
        "plain_infrastructure_errors": sum(e["result"]["status"] == "infrastructure_error" for e in plain.values()),
    }
    args.output.write_text(json.dumps({"summary": summary, "pairs": rows}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    for r in rows:
        print(r["task"], r["scene"], " ".join(f"{a}={r[a]}" for a in ARMS + REPLAYS),
              f"changes={r.get('opus_changes')} restarts={r.get('opus_restarts')}")


if __name__ == "__main__":
    main()
