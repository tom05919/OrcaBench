"""Stage 3 analysis, as fixed in docs/stage3_plan.md. Reads episode folders only; nothing here is a benchmark score.

  python scripts/analyze_stage3.py --plain runs/stage2_reference runs/stage3_remote/reference \\
      --confirmed runs/stage3_remote/confirmed.tsv \\
      --arm defer=runs/stage3_remote/always_defer defer2=runs/stage3_remote/always_defer-r2 \\
            opus=runs/stage3_remote/opus-5-5 opus2=runs/stage3_remote/opus-5-5-r2 sonnet=runs/stage3_remote/sonnet-5-5 \\
            reissue=runs/stage3_remote/reissue \\
      --replay exact=runs/stage3_remote/replay_exact native_text=runs/stage3_remote/replay_native_text \\
               no_interruption=runs/stage3_remote/replay_no_interruption \\
      --output runs/stage3_remote/analysis.json

Outcome taxonomy (from the logs alone): success; never_achieved (the checker never became true: includes ending by
budget or declaring with 15 or fewer steps left, which is giving up); declared_early (complete with more than 15
steps left while the checker was false); lost_success (the checker was true at some step and false at the end);
invalid (infrastructure error, listed and excluded)."""
import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

from robot_benchmark.scorecard import load_scored_episodes

ROOT = Path(__file__).resolve().parents[1]
GIVE_UP_STEPS = 15


def budgets():
    return {p.stem: json.loads(p.read_text())["max_steps"] for p in (ROOT / "configs" / "tasks").glob("*.json")}


def load(root):
    """Latest episode per (task, scene, policy seed) in a root, with the fields the analysis needs."""
    out = {}
    for e in load_scored_episodes(root):
        m, r = e["manifest"], e["result"]
        key = (m["task"], m["scene_seed"], m["policy_seed"])
        if key not in out or m["created_at"] > out[key]["created_at"]:
            out[key] = {"key": key, "created_at": m["created_at"], "folder": Path(e["folder"]), "result": r,
                        "agent": (m.get("agent") or {}), "first_success": (e["success_steps"] or [None])[0]}
    return out


def taxonomy(episode, budget):
    r = episode["result"]
    if r["status"] == "infrastructure_error":
        return "invalid"
    if r["success"]:
        return "success"
    if r.get("physical_success_any") and not r.get("physical_success_final"):
        return "lost_success"
    if r["status"] == "false_completion" and budget - r["steps"] > GIVE_UP_STEPS and not r.get("physical_success_any"):
        return "declared_early"
    return "never_achieved"


def exposure(episode, t_star):
    """Decisions made before the success step the no-intervention run reached, and the first change of the prompt."""
    folder = episode["folder"]
    try:
        steps = [json.loads(line)["step"] for line in (folder / "observations.jsonl").read_text().splitlines() if line.strip()]
        entries = [json.loads(line) for line in (folder / "decisions.jsonl").read_text().splitlines() if line.strip()]
    except OSError:
        return {}
    active, first_change, first_restart = None, None, None
    for i, entry in enumerate(entries):
        d = entry["decision"]
        if d.get("op") == "run_policy" and d.get("prompt"):
            if active is None:
                active = d["prompt"]
            elif first_restart is None:
                first_restart = steps[i]
            if d["prompt"] != active and first_change is None:
                first_change = steps[i]
    before = sum(1 for s in steps[1:] if t_star is not None and s < t_star)
    return {"decisions_before_success": before, "first_restart_step": first_restart, "first_change_step": first_change,
            "lead_of_first_restart": None if first_restart is None or t_star is None else t_star - first_restart}


def rate(n, d):
    return None if not d else round(n / d, 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plain", type=Path, nargs="+", required=True)
    parser.add_argument("--confirmed", type=Path, required=True, help="confirmed.tsv: task scene policy [state]")
    parser.add_argument("--arm", nargs="+", default=[], help="NAME=ROOT for always-defer, LLM and reissue arms")
    parser.add_argument("--replay", nargs="*", default=[], help="ABLATION=ROOT")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    budget = budgets()
    pairs = [tuple(f[:1]) + (int(f[1]), int(f[2])) for f in (l.split() for l in args.confirmed.read_text().splitlines() if l.strip())]
    plain = {}
    for root in args.plain:
        plain.update(load(root))
    arms = {name: load(Path(root)) for name, root in (a.split("=", 1) for a in args.arm)}
    report = {"pairs": len(pairs), "arms": {}, "tasks": {}, "episodes": []}

    for name, rows in arms.items():
        counts = defaultdict(int)
        for key in pairs:
            if key in rows:
                counts[taxonomy(rows[key], budget[key[0]])] += 1
        used = sum(counts.values()) - counts["invalid"]
        report["arms"][name] = {"episodes": sum(counts.values()), "outcomes": dict(counts),
                                "failure_rate": rate(used - counts["success"], used)}

    by_task = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for name, rows in arms.items():
        for key in pairs:
            if key in rows and taxonomy(rows[key], budget[key[0]]) != "invalid":
                cell = by_task[key[0]][name]
                cell[1] += 1
                cell[0] += taxonomy(rows[key], budget[key[0]]) != "success"
    report["tasks"] = {task: {name: {"failed": f, "of": n} for name, (f, n) in cells.items()} for task, cells in sorted(by_task.items())}

    for key in pairs:
        t_star = (arms.get("defer2") or arms.get("defer") or {}).get(key, {}).get("first_success") or plain.get(key, {}).get("first_success")
        for name in ("opus", "opus2", "sonnet"):
            e = arms.get(name, {}).get(key)
            if e:
                report["episodes"].append({"arm": name, "pair": list(key), "outcome": taxonomy(e, budget[key[0]]),
                                           "prompt_changes": e["result"]["prompt_changes"], "restarts": e["result"]["prompt_restarts"],
                                           "calls": e["result"]["model_calls"], "steps": e["result"]["steps"], "t_star": t_star,
                                           **exposure(e, t_star)})
    llm = [e for e in report["episodes"] if e["arm"] in ("opus", "opus2") and e["outcome"] != "invalid"]
    intervened = [e for e in llm if e["restarts"] or e["prompt_changes"]]
    report["opus_exposure"] = {
        "episodes": len(llm), "intervened": len(intervened),
        "p_fail_given_intervened": rate(sum(e["outcome"] != "success" for e in intervened), len(intervened)),
        "p_fail_given_left_alone": rate(sum(e["outcome"] != "success" for e in llm if not (e["restarts"] or e["prompt_changes"])),
                                        len(llm) - len(intervened))}

    # Mechanism: every Opus failure that the exact replay reproduces.
    replays = {name: load(Path(root)) for name, root in (a.split("=", 1) for a in args.replay)}
    by_source = defaultdict(dict)
    for ablation, rows in replays.items():
        for key, e in rows.items():
            by_source[(key, e["agent"].get("source_episode"))][ablation] = taxonomy(e, budget[key[0]])
    mech = []
    for (key, source), outcomes in sorted(by_source.items(), key=str):
        exact = outcomes.get("exact")
        if exact == "invalid" or exact is None:
            verdict = "no_exact_replay"
        elif exact == "success":
            verdict = "not_reproduced"
        elif outcomes.get("native_text") == "success":
            verdict = "wording"
        elif outcomes.get("no_interruption") == "success":
            verdict = "restart"
        else:
            verdict = "declaration_or_unattributed"
        mech.append({"pair": list(key), "source": source, "replays": outcomes, "mechanism": verdict})
    report["mechanism"] = mech

    text = json.dumps(report, indent=1)
    if args.output:
        args.output.write_text(text + "\n")
    print("pairs:", report["pairs"])
    for name, a in report["arms"].items():
        print(f"{name:10s} episodes={a['episodes']:3d} failure_rate={a['failure_rate']} {a['outcomes']}")
    print("opus exposure:", report["opus_exposure"])
    for task, cells in report["tasks"].items():
        print(f"{task:26s}", "  ".join(f"{n}:{c['failed']}/{c['of']}" for n, c in cells.items()))
    if mech:
        print("mechanisms:", dict(sorted({m: sum(1 for x in mech if x['mechanism'] == m) for m in {x['mechanism'] for x in mech}}.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
