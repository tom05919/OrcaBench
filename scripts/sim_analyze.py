"""Analysis of Part 1 (probes) and Part 2 (sessions), with the criteria fixed in docs/env_design.md before any model call.

  python scripts/sim_analyze.py --probes runs/sim/probes-opus.jsonl [--session runs/sim/session-opus-1.jsonl ...]"""
import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

PROFILES = ("steady", "hesitant", "brittle")


def load(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def mean(xs):
    return statistics.mean(xs) if xs else float("nan")


def probes(rows):
    by = defaultdict(list)
    for r in rows:
        by[(r["level"], r["cls"], r["profile"])].append(r)
    print("valid answers: %d of %d" % (sum(r["valid"] for r in rows), len(rows)))
    print("\nmean advantage vs the best candidate (0 is best), by class and experience level")
    for cls in ("S1", "S2", "S3"):
        print(f"  {cls}: " + "  ".join(f"level {lv}: " + " ".join(f"{p[:3]} {mean([r['advantage'] for r in by[(lv, cls, p)]]):+.3f}" for p in PROFILES)
                                      for lv in (0, 3, 8)))
    print("\nS1 first interval chosen (median over answers)")
    for lv in (0, 3, 8):
        print(f"  level {lv}: " + "  ".join(f"{p[:3]} {statistics.median([r['decision'].get('steps', 0) for r in by[(lv, 'S1', p)]]):.0f}" for p in PROFILES if by[(lv, 'S1', p)]))
    print("\nS2 apparent stall: share of answers that restart (supply a prompt); latent state in brackets")
    for lv in (0, 3, 8):
        cells = []
        for p in PROFILES:
            rs = by[(lv, "S2", p)]
            if rs:
                cells.append(f"{p[:3]} {mean([float('prompt' in r['decision']) for r in rs]):.2f} {sorted({r['latent'] for r in rs})}")
        print(f"  level {lv}: " + "  ".join(cells))
    print("\nS3 first sight of 'looks complete': share of answers that wait (do not declare now)")
    for lv in (0, 3, 8):
        print(f"  level {lv}: " + "  ".join(f"{p[:3]} {mean([float(r['decision'].get('op') != 'complete') for r in by[(lv, 'S3', p)]]):.2f}" for p in PROFILES if by[(lv, 'S3', p)]))
    # pre-declared criteria
    s2 = lambda lv, p: [float("prompt" in r["decision"]) for r in by[(lv, "S2", p)]]
    learned_q1 = (mean(s2(8, "brittle")) >= 0.75 and mean(s2(8, "hesitant")) <= 0.25
                  and abs(mean(s2(0, "brittle")) - mean(s2(0, "hesitant"))) < 0.5)
    paired = []
    for r in rows:
        if r["cls"] == "S1" and r["level"] == 8 and r["profile"] == "brittle":
            other = next((o for o in rows if o["level"] == 8 and o["cls"] == "S1" and o["profile"] == "steady"
                          and o["log_set"] == r["log_set"] and o["instance"] == r["instance"]), None)
            if other:
                paired.append(r["decision"].get("steps", 0) < other["decision"].get("steps", 0))
    s1 = lambda lv: mean([r["advantage"] for r in rows if r["cls"] == "S1" and r["level"] == lv])
    learned_q2 = sum(paired) >= 3 and s1(8) > s1(0)
    wait = lambda lv: mean([float(r["decision"].get("op") != "complete") for r in rows if r["cls"] == "S3" and r["level"] == lv])
    print(f"\nQ1 learned when to interrupt (restart brittle stalls >=0.75, continue hesitant <=0.25, no separation at level 0): {learned_q1}")
    print(f"Q2 learned how often to observe (brittle's first interval shorter than steady's in >=3 of 4 pairs {sum(paired)}/{len(paired)}, S1 advantage up from level 0 to 8): {learned_q2}")
    print(f"S3 wait rate level 0 -> 8: {wait(0):.2f} -> {wait(8):.2f}")
    print("tokens per call: output %.0f, thinking %.0f; spend $%.2f over %d calls" % (
        mean([r["usage"].get("output_tokens", 0) for r in rows]), mean([r["usage"].get("output_tokens_details", {}).get("thinking_tokens", 0) for r in rows]),
        rows[-1]["spent"], len(rows)))


def session(path, calibration):
    rows = load(path)
    print(f"\nsession {Path(path).name}: {len(rows)} episodes")
    for p in PROFILES:
        ps = [r for r in rows if r["profile"] == p]
        half = len(ps) // 2
        print(f"  {p:9s} success {mean([float(r['success']) for r in ps]):.2f}  utility {mean([r['utility'] for r in ps]):+.3f}  calls {mean([r['calls'] for r in ps]):.1f}  steps {mean([r['steps'] for r in ps]):.0f}"
              f"  restarts {mean([len(r['restarts']) for r in ps]):.1f}  | first half {mean([r['utility'] for r in ps[:half]]):+.3f} second half {mean([r['utility'] for r in ps[half:]]):+.3f}")
    regret = Path(path).with_suffix(".regret.json")
    if regret.exists():
        rg = json.loads(regret.read_text())
        cal = json.loads(Path(calibration).read_text())["heldout"]
        for p in PROFILES:
            rs = [r for r in rg if r["profile"] == p]
            half = len(rs) // 2
            print(f"  {p:9s} regret vs pi*: paired {mean([r['paired_regret'] for r in rs]):+.3f} advantage-sum {mean([r['advantage_sum_regret'] for r in rs]):+.3f}"
                  f" (first half {mean([r['advantage_sum_regret'] for r in rs[:half]]):+.3f}, second {mean([r['advantage_sum_regret'] for r in rs[half:]]):+.3f})"
                  f" | pi_pool regret {cal[p]['pi_star']['utility'] - cal[p]['pi_pool']['utility']:+.3f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probes", nargs="*", default=[])
    parser.add_argument("--session", nargs="*", default=[])
    parser.add_argument("--calibration", default="runs/sim/calibration.json")
    args = parser.parse_args()
    for path in args.probes:
        print(f"==== {path}")
        global rows
        rows = load(path)
        probes(rows)
    for path in args.session:
        session(path, args.calibration)


if __name__ == "__main__":
    main()
