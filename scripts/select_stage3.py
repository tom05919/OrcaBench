"""Choose the stage 3 episodes by rules fixed before the results exist. Prints one TSV line per chosen item.

  candidates  plain-policy successes to confirm: per task, the first N pairs, ordered by policy seed then scene seed.
  confirmed   candidates whose always-defer replay also succeeded AND started from the identical simulator state as
              the plain run (same step-0 state hash): per task, the first N. Only these pairs get LLM episodes.
  repeats     confirmed pairs whose first LLM episode failed or changed the prompt: they get another LLM episode.
  dose        confirmed pairs of tasks where an LLM or reissue-100 episode failed: they get the interruption sweep.
  rescue      scenes where the plain policy failed every time (two or more episodes): the LLM runs there to see
              whether it ever succeeds where the plain policy does not.
  replays     LLM episodes to replay with no model: every failure, plus up to N successes that changed the prompt.

Outcomes are read only to find leave-alone pairs and to aim the follow-up arms; they never choose which result to
report. Every pair that was dropped is listed in the --table JSON with its reason."""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from robot_benchmark.scorecard import load_scored_episodes


def start_state(folder):
    """(step-0 state hash, layout id) of an episode, or (None, None)."""
    try:
        with open(Path(folder) / "evaluator" / "states.jsonl") as stream:
            row = json.loads(stream.readline())
        return row["state_sha256"], (row.get("episode_metadata") or {}).get("layout_id")
    except (OSError, ValueError, KeyError):
        return None, None


def collect(roots):
    """Latest usable episode per (task, scene, policy seed) across roots, as plain dicts."""
    latest = {}
    for root in roots:
        for e in load_scored_episodes(root):
            m, r = e["manifest"], e["result"]
            if r["status"] == "infrastructure_error":
                continue
            key = (m["task"], m["scene_seed"], m["policy_seed"])
            if key not in latest or m["created_at"] > latest[key]["created_at"]:
                state, layout = start_state(e["folder"])
                latest[key] = {"key": key, "created_at": m["created_at"], "folder": e["folder"], "status": r["status"],
                               "success": bool(r["success"]), "state": state, "layout": layout,
                               "changes": r.get("prompt_changes", 0), "restarts": r.get("prompt_restarts", 0)}
    return latest


def first_per_task(keys, cap):
    """Per task, the first `cap` pairs ordered by policy seed then scene seed, so scenes vary before seeds repeat."""
    chosen, counts = [], defaultdict(int)
    for key in sorted(keys, key=lambda k: (k[0], k[2], k[1])):
        if counts[key[0]] < cap:
            counts[key[0]] += 1
            chosen.append(key)
    return chosen


def candidates(plain, cap):
    return first_per_task([k for k, e in plain.items() if e["success"]], cap)


def confirmed(plain, defer, cap):
    """(chosen keys, {key: reason}) for the candidate pairs the defer replay did not confirm."""
    ok, dropped = [], {}
    for key, e in plain.items():
        d = defer.get(key)
        if not e["success"] or d is None:
            continue
        if not d["success"]:
            dropped[key] = "defer_failed"
        elif d["state"] is None or d["state"] != e["state"]:
            dropped[key] = "different_layout" if d["layout"] != e["layout"] else "initial_state_differs"
        else:
            ok.append(key)
    return first_per_task(ok, cap), dropped


def repeats(llm):
    return sorted(k for k, e in llm.items() if not e["success"] or e["changes"] or e["restarts"])


def dose(confirmed_keys, *arms, max_pairs=12):
    """Pairs of the tasks where any arm failed on a confirmed pair, ascending, at most max_pairs."""
    pairs = set(confirmed_keys)
    tasks = {k[0] for arm in arms for k, e in arm.items() if k in pairs and not e["success"]}
    return sorted(k for k in confirmed_keys if k[0] in tasks)[:max_pairs]


def replays(llm_episodes, max_successes):
    """Episodes to replay: every failure, plus up to max_successes that changed the prompt (earliest first)."""
    failures = [e for e in llm_episodes if not e["success"]]
    rewrites = sorted((e for e in llm_episodes if e["success"] and e["changes"]), key=lambda e: e["key"])
    return failures + rewrites[:max_successes]


def rescue(plain, cap):
    """Pairs the plain policy fails repeatedly: (task, scene) where every plain episode failed (at least two of them),
    taken at that scene's lowest policy seed; per task the first `cap` by scene. The LLM runs there to see whether it
    ever succeeds where the plain policy does not."""
    scenes = defaultdict(list)
    for key, e in plain.items():
        scenes[(key[0], key[1])].append(e)
    keys = [min(e["key"] for e in episodes) for episodes in scenes.values()
            if len(episodes) >= 2 and not any(e["success"] for e in episodes)]
    return first_per_task(keys, cap)


def tsv(keys, plain=None):
    """One line per pair; with the plain table, a fourth column carries the plain run's step-0 state hash, which
    the arms pass as --expect-state so that a different scene ends the episode before any model call."""
    for key in keys:
        print(*key, *([plain[key]["state"]] if plain and plain[key]["state"] else []))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("candidates", "confirmed", "repeats", "dose", "replays", "rescue"):
        p = sub.add_parser(name)
        p.add_argument("--table", type=Path, help="write the dropped pairs and reasons here")
        if name in ("candidates", "confirmed", "rescue"):
            p.add_argument("--plain-roots", type=Path, nargs="+", required=True)
            p.add_argument("--cap", type=int, default={"candidates": 6, "confirmed": 4, "rescue": 1}[name])
        if name == "confirmed":
            p.add_argument("--defer-roots", type=Path, nargs="+", required=True)
        if name in ("repeats", "replays"):
            p.add_argument("--llm-roots", type=Path, nargs="+", required=True)
        if name == "replays":
            p.add_argument("--max-successes", type=int, default=8)
        if name == "dose":
            p.add_argument("--confirmed-tsv", type=Path, required=True)
            p.add_argument("--arm-roots", type=Path, nargs="+", required=True, help="LLM and reissue-100 roots")
            p.add_argument("--max-pairs", type=int, default=12)
    args = parser.parse_args()
    dropped = {}
    if args.command == "candidates":
        plain = collect(args.plain_roots)
        tsv(candidates(plain, args.cap), plain)
    elif args.command == "confirmed":
        plain = collect(args.plain_roots)
        keys, dropped = confirmed(plain, collect(args.defer_roots), args.cap)
        tsv(keys, plain)
    elif args.command == "rescue":
        plain = collect(args.plain_roots)
        tsv(rescue(plain, args.cap), plain)
    elif args.command == "repeats":
        tsv(repeats(collect(args.llm_roots)))
    elif args.command == "dose":
        keys = [(f[0], int(f[1]), int(f[2])) for f in (line.split() for line in args.confirmed_tsv.read_text().splitlines() if line.strip())]
        tsv(dose(keys, *(collect([root]) for root in args.arm_roots), max_pairs=args.max_pairs))
    elif args.command == "replays":
        llm = {}
        for root in args.llm_roots:
            for e in load_scored_episodes(root):
                if e["result"]["status"] == "infrastructure_error":
                    continue
                m, r = e["manifest"], e["result"]
                llm[e["folder"]] = {"key": (m["task"], m["scene_seed"], m["policy_seed"]), "folder": e["folder"],
                                    "success": bool(r["success"]), "changes": r.get("prompt_changes", 0)}
        for e in replays(list(llm.values()), args.max_successes):
            print(*e["key"], e["folder"])
    if getattr(args, "table", None):
        args.table.write_text(json.dumps({"dropped": {"|".join(map(str, k)): v for k, v in dropped.items()}}, indent=2) + "\n")


if __name__ == "__main__":
    main()
