#!/usr/bin/env python3
"""Pick the final policies and tasks from W2's results, by the rules fixed on October 13 before those results existed
(docs/final_experiment.md).

Inputs:
- the ladder table, `runs/stage6_ladder/analysis.json`, from `scripts/analyze_stage5.py`: per backend, per task,
  `successes` and `usable`;
- the ceiling table, `runs/stage6_ceiling/ceiling.json` from `scripts/analyze_stage5.py --ceiling` (W2):
  `{backend: {task: {"pairs", "plain_successes", "sequencer_successes", ...}}}` over the same paired episodes. The
  form `{"plain": [successes, n], "sequencer": [successes, n]}` is also accepted.

Rules:
1. **Helpable unseen tasks:** an unseen candidate task is helpable if, for at least one candidate policy, the
   sequencer beat plain by at least `HELP_MARGIN` successes. Keep up to four, story tasks first, then by the largest
   margin. If fewer than two are helpable, the **fallback** applies: fill to four with the unseen candidates that have
   the most pooled plain successes (at least one), and record it. The benchmark then measures monitoring and
   declaring rather than rescue.
2. **Policies:** among the candidate backends (`groot_pretrain` excluded), choose three whose pooled plain success on
   the chosen unseen tasks spreads most: maximize the smallest pairwise gap, then the total success. `--policies`
   replaces this rule with an explicit, logged decision. Tom chose `groot`, `groot_u30` and `pi05` on October 13,
   because the measured ladder had no three distinct levels. Rules 1 and 3 still apply.
3. **Leave-alone tasks:** three seen candidates with the highest minimum plain success across the chosen policies.

  python3 scripts/select_final.py [--ladder ...] [--ceiling ...] [--output runs/final/selection.json]
"""
import argparse
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNSEEN = ("MakeIceLemonade", "SeparateFreezerRack", "PanTransfer", "PortionHotDogs", "GarnishPancake",
          "HeatKebabSandwich", "WaffleReheat", "ArrangeTea")
STORY = set(UNSEEN[:5])
SEEN = ("OpenCabinet", "PickPlaceCounterToCabinet", "PickPlaceCounterToStove", "OpenDrawer", "CloseFridge")
EXCLUDED_POLICIES = {"groot_pretrain"}
HELP_MARGIN = 2


def rate(table, backend, task):
    cell = table.get(backend, {}).get("tasks", {}).get(task)
    return None if not cell or not cell["usable"] else cell["successes"] / cell["usable"]


def counts(cell):
    """(plain successes, sequencer successes) of a ceiling cell, in either accepted form."""
    if "plain_successes" in cell:
        return cell["plain_successes"], cell["sequencer_successes"]
    return cell["plain"][0], cell["sequencer"][0]


def select(ladder, ceiling, policies=None):
    candidates = sorted(b for b in ladder if b not in EXCLUDED_POLICIES)
    margins = {}
    for backend, tasks in ceiling.items():
        if backend in EXCLUDED_POLICIES:
            continue
        for task, cell in tasks.items():
            if task in UNSEEN:
                plain, sequencer = counts(cell)
                margins[task] = max(margins.get(task, -99), sequencer - plain)
    helpable = sorted((t for t, m in margins.items() if m >= HELP_MARGIN), key=lambda t: (t not in STORY, -margins[t], t))
    unseen, fallback = helpable[:4], len(helpable) < 2
    if fallback:
        pooled = {t: sum(ladder[b]["tasks"].get(t, {}).get("successes", 0) for b in candidates) for t in UNSEEN}
        for task in sorted(pooled, key=lambda t: (-pooled[t], t)):
            if len(unseen) == 4 or pooled[task] == 0:
                break
            if task not in unseen:
                unseen.append(task)

    def pooled_rate(backend):
        cells = [ladder[backend]["tasks"].get(t) for t in unseen]
        n = sum(c["usable"] for c in cells if c)
        return sum(c["successes"] for c in cells if c) / n if n else 0.0

    rates = {b: pooled_rate(b) for b in candidates}
    if policies:  # an explicit decision; a policy without ladder cells is reported as untested (null), never as zero
        rates = {b: (pooled_rate(b) if b in ladder else None) for b in policies}
        seen = sorted(SEEN, key=lambda t: (-min((rate(ladder, b, t) or 0.0) for b in policies if b in ladder), t))[:3]
        return {"policies": list(policies), "policy_unseen_success": rates, "unseen_tasks": unseen,
                "helpable_margins": margins, "fallback_monitoring": fallback, "seen_tasks": seen,
                "story_tasks": [t for t in unseen if t in STORY],
                "untested_policies": [b for b in policies if b not in ladder]}
    policies = list(candidates)
    if len(candidates) > 3:
        def spread(trio):
            values = sorted(rates[b] for b in trio)
            return (min(values[1] - values[0], values[2] - values[1]), sum(values))
        policies = list(max(itertools.combinations(candidates, 3), key=spread))
    seen = sorted(SEEN, key=lambda t: (-min((rate(ladder, b, t) or 0.0) for b in policies), t))[:3]
    return {"policies": policies, "policy_unseen_success": {b: rates[b] for b in policies}, "unseen_tasks": unseen,
            "helpable_margins": margins, "fallback_monitoring": fallback, "seen_tasks": seen,
            "story_tasks": [t for t in unseen if t in STORY]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ladder", type=Path, default=ROOT / "runs" / "stage6_ladder" / "analysis.json")
    parser.add_argument("--ceiling", type=Path, default=ROOT / "runs" / "stage6_ceiling" / "ceiling.json")
    parser.add_argument("--policies", nargs="+", help="an explicit, logged policy decision (replaces rule 2)")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    choice = select(json.loads(args.ladder.read_text()), json.loads(args.ceiling.read_text()), args.policies)
    print(json.dumps(choice, indent=2))
    tasks = " ".join(choice["unseen_tasks"] + choice["seen_tasks"])
    print(f"\nnext: python3 scripts/make_session_plans.py --policies {' '.join(choice['policies'])} --tasks {tasks} "
          "--scenes 1000 1001 1002 1003 --output runs/final/plans")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(choice, indent=2) + "\n")


if __name__ == "__main__":
    main()
