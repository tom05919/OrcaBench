"""Compare model (or baseline) episodes with the plain-policy reference on the same task, scene and policy seed.

Development tool for small runs, before a release exists. Per model episode it prints the outcome next to the
reference outcome, the intervention profile, both clocks (simulated and real), tokens, and the scorecard's
failure-attribution label. It is not the benchmark scorecard: it uses no release, groups or bootstrap."""
import argparse
import json
from pathlib import Path

from robot_benchmark.scorecard import attribute_failure, load_scored_episodes


def key(episode):
    m = episode["manifest"]
    return m["task"], m["scene_seed"], m["policy_seed"]


def tokens(result, name):
    return sum(u.get(name, 0) for u in result.get("usage", []) if isinstance(u, dict))


def describe(episode, reference):
    m, r = episode["manifest"], episode["result"]
    decisions = [json.loads(line) for line in (episode["folder"] / "decisions.jsonl").read_text().splitlines() if line.strip()]
    rejected = sum(1 for d in decisions if not d["accepted"])
    reprompts = [t["step"] for t in episode["transitions"][1:]]
    group = "leave_alone" if reference and reference["result"]["success"] else "needs_help"
    label = "success" if r["success"] else attribute_failure(episode, group, reference)
    return {
        "task": m["task"], "scene": m["scene_seed"], "policy": m["policy_seed"], "model": (m.get("agent") or {}).get("model"),
        "reference": None if reference is None else ("success" if reference["result"]["success"] else "fail"),
        "reference_first_success_step": reference["success_steps"][0] if reference and reference["success_steps"] else None,
        "status": r["status"], "label": label, "steps": r["steps"], "calls": r["model_calls"], "rejected_replies": rejected,
        "prompts": r["prompt_submissions"], "restarts": r["prompt_restarts"], "changes": r["prompt_changes"],
        "discarded_actions": r["discarded_actions"], "first_reprompt_step": reprompts[0] if reprompts else None,
        "physical_goal_ever": r.get("physical_success_any"), "intervals": r.get("intervals"),
        "simulated_seconds": round(r.get("simulated_seconds", 0), 1), "wall_seconds": round(r["wall_seconds"], 1),
        "model_seconds": round(r.get("model_seconds", 0), 1), "policy_seconds": round(r.get("policy_seconds", 0), 1),
        "input_tokens": tokens(r, "input_tokens"), "output_tokens": tokens(r, "output_tokens"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path, required=True, help="directory with diagnostic_reference episodes")
    parser.add_argument("--model-root", type=Path, required=True, help="directory with the model or baseline episodes")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    references = {}
    for episode in load_scored_episodes(args.reference_root):
        if episode["manifest"].get("kind") == "diagnostic_reference" and episode["result"]["status"] != "infrastructure_error":
            references[key(episode)] = episode
    rows = []
    for episode in load_scored_episodes(args.model_root):
        episode["folder"] = Path(episode["folder"])
        rows.append(describe(episode, references.get(key(episode))))
    rows.sort(key=lambda row: (row["task"], row["scene"]))
    print(f"{'task':26s} {'scn':>4s} {'plain':>5s} {'model':>22s} {'label':>24s} {'steps':>5s} {'calls':>5s} {'rej':>3s} "
          f"{'prm':>3s} {'rst':>3s} {'1st re-prompt':>13s} {'sim_s':>6s} {'wall_s':>6s} {'model_s':>7s}")
    for r in rows:
        print(f"{r['task']:26s} {r['scene']:>4d} {str(r['reference']):>5s} {r['status']:>22s} {r['label']:>24s} {r['steps']:>5d} "
              f"{r['calls']:>5d} {r['rejected_replies']:>3d} {r['prompts']:>3d} {r['restarts']:>3d} "
              f"{str(r['first_reprompt_step']):>13s} {r['simulated_seconds']:>6.1f} {r['wall_seconds']:>6.1f} {r['model_seconds']:>7.1f}")
    calls = sum(r["calls"] for r in rows)
    print(f"\nepisodes {len(rows)}, rejected replies {sum(r['rejected_replies'] for r in rows)} of {calls} calls, "
          f"input tokens {sum(r['input_tokens'] for r in rows)}, output tokens {sum(r['output_tokens'] for r in rows)}")
    if args.output:
        args.output.write_text(json.dumps(rows, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
