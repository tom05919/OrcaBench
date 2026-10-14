#!/usr/bin/env python3
"""Set `story.limit_seconds` for the time-sensitive tasks from plain-policy runs, by the rule fixed on October 13 before
any data existed (docs/time_score.md):

  For each story task and each benchmark policy with at least MIN_SUCCESSES successful no-restart runs that logged the
  trigger, take the median seconds from the trigger to the first success. The limit is the largest of those medians
  plus room for ALLOWANCE_CALLS responses at the slowest calibrated model's latency, rounded up to 5 s. If no policy
  qualifies, the limit stays null and the story is not applied.

The limit depends on the benchmark's policies, never on any supervisor's results. It leaves each policy's typical
success achievable, and it binds on supervision delay after the trigger.

  python3 scripts/set_story_limits.py runs/stage6_ladder --policies groot groot_u10 groot_u30 [--write]
"""
import argparse
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from robot_benchmark.time_score import STEPS_PER_SECOND, load_config, read_episode, rule_source  # noqa: E402

MIN_SUCCESSES = 2
ALLOWANCE_CALLS = 3


def trigger_to_success(episode, clock_starts):
    """Seconds from the trigger to the first success, or None (no success, or the trigger was not logged)."""
    first = next((i for i, ok in enumerate(episode["success_by_step"]) if ok), None)
    if first is None:
        return None
    if clock_starts == "step0":
        return first / STEPS_PER_SECOND
    if clock_starts not in episode["logged"]:
        return None
    trigger = episode["first_true"].get(clock_starts)
    return None if trigger is None or trigger > first else (first - trigger) / STEPS_PER_SECOND


def story_limits(episodes, config, policies):
    allowance = ALLOWANCE_CALLS * max(config["call_seconds"].values())
    out = {}
    for task, spec in sorted(config["tasks"].items()):
        story = spec.get("story")
        if not story:
            continue
        medians, counts = {}, {}
        for backend in policies:
            runs = [e for e in episodes if e["task"] == task and e["backend"] == backend
                    and rule_source(e) == "no_restart" and not e["infrastructure_error"]]
            times = [t for t in (trigger_to_success(e, story["clock_starts"]) for e in runs) if t is not None]
            counts[backend] = (len(times), len(runs))
            if len(times) >= MIN_SUCCESSES:
                medians[backend] = statistics.median(times)
        limit = None if not medians else 5 * math.ceil((max(medians.values()) + allowance) / 5)
        out[task] = {"limit_seconds": limit, "medians": medians, "successes_and_runs": counts,
                     "binds": None if limit is None else limit < spec["deadline_seconds"]}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("roots", type=Path, nargs="+")
    parser.add_argument("--policies", nargs="+", required=True, help="the final benchmark backends")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "time_pressure.json")
    parser.add_argument("--write", action="store_true", help="write the limits into the config")
    args = parser.parse_args()
    config = load_config(args.config)
    episodes = [read_episode(r.parent) for root in args.roots for r in sorted(Path(root).rglob("result.json"))
                if (r.parent / "manifest.json").exists()]
    limits = story_limits(episodes, config, args.policies)
    for task, row in limits.items():
        print(f"{task:22s} limit {row['limit_seconds']} s (deadline {config['tasks'][task]['deadline_seconds']} s, "
              f"binds {row['binds']}); medians {row['medians']}; successes/runs {row['successes_and_runs']}")
    if args.write:
        raw = json.loads(args.config.read_text())
        for task, row in limits.items():
            raw["tasks"][task]["story"]["limit_seconds"] = row["limit_seconds"]
        raw["story_limit_rule"] = (f"max over policies {args.policies} of the median trigger-to-success seconds "
                                   f"(policies with >= {MIN_SUCCESSES} successes) + {ALLOWANCE_CALLS} x the slowest "
                                   f"call_seconds, rounded up to 5 s (scripts/set_story_limits.py)")
        args.config.write_text(json.dumps(raw, indent=2) + "\n")
        print(f"wrote {args.config}")


if __name__ == "__main__":
    main()
