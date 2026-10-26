#!/usr/bin/env python3
"""Count what the replay runs paid for and did not keep, per condition (docs/replay_report.md, "What was lost").

  python3 scripts/replay_losses.py [--out results/w1/replay/losses.json]

From the ledger (`runs/replay/api_spend.jsonl`, one line per settled request) and the records on disk:
- replies: requests that returned with usage (paid); timeouts: attempts the client gave up on (Sail may still have run
  and billed them); http: error responses by status code.
- Sessions: looks saved on arrival (`.looks.jsonl`), looks inside finished episodes (scored), looks of interrupted
  episode attempts (saved, paid, not scored: the episode was replayed from its start; an episode still running when
  this is run also counts here), and paid replies with no saved
  look (a stop between payment and saving; for runs started before per-look saving existed, October 24 14:28, it
  counts every reply, so compare it with the scored looks there).
- Probes: replies against answers on disk. Probe ledger tags carry no pass, so pilot (pass 0) replies are counted
  with the cell and subtracted using the pilot files.
- Requests still in flight when a process stopped are in neither the ledger nor the records; each interrupted episode
  attempt had at most one. Their number for probes cannot be recovered."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from robot_benchmark.replay_bench import condition_of  # noqa: E402

OUT = ROOT / "runs" / "replay"


def session_condition(tag):
    """'c2/effort-low/pass1/<model slug>' (default runs have no effort folder) and the session file stem."""
    _, slug, cost, pass_no, rest = tag.split(":")[:5]
    stem, level = rest.split("#")[0].split("@") if "@" in rest else (rest.split("#")[0], None)
    folder = f"{cost}/effort-{level}/pass{pass_no[1:]}" if level else f"{cost}/pass{pass_no[1:]}"
    return f"{folder}/{slug}", stem


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "w1" / "replay" / "losses.json")
    args = parser.parse_args()
    ledger = defaultdict(lambda: {"replies": 0, "timeouts": 0, "http": Counter()})
    for line in (OUT / "api_spend.jsonl").read_text().splitlines():
        e = json.loads(line)
        tag = e["tag"]
        if tag.startswith("session"):
            key = "sessions/" + session_condition(tag)[0]
        else:
            key = f"probe/{condition_of(tag)[1]}/{e['model']}"
        if ":http:" in tag:
            ledger[key]["http"][tag.split(":http:")[1].split(":")[0]] += 1
        elif tag.endswith(":timeout"):
            ledger[key]["timeouts"] += 1
        else:
            ledger[key]["replies"] += 1
    out = {}
    for folder in sorted((OUT / "sessions").glob("c*/**/pass*/*")):
        if not folder.is_dir():
            continue
        key = "sessions/" + str(folder.relative_to(OUT / "sessions"))
        saved = scored = interrupted_looks = 0
        interrupted_dollars = 0.0
        attempts, finished = set(), set()
        for looks in folder.glob("*.looks.jsonl"):
            for r in map(json.loads, looks.read_text().splitlines()):
                saved += 1
                attempts.add((looks.name, r["index"], r["attempt"]))
        episodes = 0
        for f in folder.glob("*.jsonl"):
            if f.name.endswith(".looks.jsonl"):
                continue
            for r in map(json.loads, f.read_text().splitlines()):
                if "outcome" in r:
                    episodes += 1
                    scored += len(r["decisions"])
                    finished.add((f.stem + ".looks.jsonl", r["index"], r.get("attempt")))
        interrupted = attempts - finished
        for looks in folder.glob("*.looks.jsonl"):
            for r in map(json.loads, looks.read_text().splitlines()):
                if (looks.name, r["index"], r["attempt"]) in interrupted:
                    interrupted_looks += 1
                    interrupted_dollars += r["dollars"]
        led = ledger.pop(key, {"replies": 0, "timeouts": 0, "http": Counter()})
        out[key] = {"episodes": episodes, "paid_replies": led["replies"], "timeouts": led["timeouts"],
                    "http_errors": dict(led["http"]), "looks_saved": saved, "looks_scored": scored,
                    "interrupted_attempts": len(interrupted), "interrupted_looks": interrupted_looks,
                    "interrupted_dollars": round(interrupted_dollars, 3),
                    "paid_replies_not_saved": led["replies"] - saved}
    for path in sorted((OUT / "probe").glob("**/pass1/*.jsonl")):
        level = path.parent.parent.name.replace("effort-", "") if path.parent.parent.name.startswith("effort-") \
            else "default"
        rows = path.read_text().splitlines()
        model = json.loads(rows[0])["model"]
        pilot = path.parent.parent / "pass0" / path.name
        pilot_n = len(pilot.read_text().splitlines()) if pilot.exists() else 0
        led = ledger.pop(f"probe/{level}/{model}", {"replies": 0, "timeouts": 0, "http": Counter()})
        if level == "default":  # pass 2 shares the ledger condition with pass 1
            p2 = path.parent.parent / "pass2" / path.name
            pilot_n += len(p2.read_text().splitlines()) if p2.exists() else 0
        out[f"probe/{level}/{model}"] = {"answers": len(rows), "paid_replies": led["replies"] - pilot_n,
                                         "timeouts_incl_pilot": led["timeouts"], "http_errors": dict(led["http"]),
                                         "paid_replies_not_saved": led["replies"] - pilot_n - len(rows)}
    out["unmatched_ledger"] = {k: {**v, "http": dict(v["http"])} for k, v in ledger.items()}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
