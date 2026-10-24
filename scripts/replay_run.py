#!/usr/bin/env python3
"""Run the replay benchmark (docs/superpowers/specs/2026-10-24-replay-benchmark-design.md) on Sail models.

  python3 scripts/replay_run.py probe --models zai-org/GLM-5.3-Flash --pass 1 [--limit 10]
  python3 scripts/replay_run.py sessions --models zai-org/GLM-5.3-Flash --cost-per-look 2 --pass 1 [--limit 1]

Outputs go under runs/replay/ (Git-ignored) and resume where they stopped. Every call is priced into
runs/replay/api_spend.jsonl; nothing is sent once the next call's worst case would pass --cap dollars. The Sail key is
read from SAIL_API_KEY (the Git-ignored .env) and never printed."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from robot_benchmark.replay_bench import (PROBE_SYSTEM, FrameSource, Ledger, SailClient, SpendCapReached,  # noqa: E402
                                          load_trajectories, parse_probe, probe_content, run_session, sample_probes)
from robot_benchmark.time_score import load_config  # noqa: E402

POD_ROOTS = {"podC": ROOT / "runs/addon/podC/always_defer", "podB": ROOT / "runs/final/podB/always_defer"}
OUT = ROOT / "runs" / "replay"


def slug(model):
    return model.replace("/", "__")


def env_key():
    if "SAIL_API_KEY" not in os.environ and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("SAIL_API_KEY="):
                os.environ["SAIL_API_KEY"] = line.split("=", 1)[1].strip().strip("\"'")
    return os.environ["SAIL_API_KEY"]


def run_probe(client, frames, trajectories, model, pass_no, limit, workers):
    out = OUT / "probe" / f"pass{pass_no}" / f"{slug(model)}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["probe"] for l in out.read_text().splitlines() if l.strip()} if out.exists() else set()
    by_id = {t["id"]: t for t in trajectories}
    todo = [p for p in sample_probes(trajectories) if p["probe"] not in done][:limit]

    def one(p):
        reply = client.call(model, PROBE_SYSTEM, probe_content(frames, by_id[p["traj"]], p["step"]),
                            tag=f"probe:{p['probe']}")
        return {**p, "model": model, "answer": parse_probe(reply["text"]), "raw": reply["text"][-300:],
                "usage": reply["usage"], "seconds": reply["seconds"], "dollars": reply["dollars"]}

    with ThreadPoolExecutor(workers) as pool, out.open("a") as f:
        for future in as_completed([pool.submit(one, p) for p in todo]):
            try:
                f.write(json.dumps(future.result()) + "\n")
                f.flush()
            except SpendCapReached as e:
                print("spend cap:", e)
            except Exception:
                traceback.print_exc()
    print(f"probe {model} pass {pass_no}: {len(done) + len(todo)} probes in {out}")


def run_sessions(client, frames, trajectories, model, cost, pass_no, limit, workers, config):
    jobs = []
    for pod in POD_ROOTS:
        trajs = {(t["backend"], t["task"], t["scene"]): t for t in trajectories if t["pod"] == pod}
        for plan_path in sorted((ROOT / "configs/final/plans").glob("scene*.json")):
            plan = json.loads(plan_path.read_text())
            out = OUT / "sessions" / f"c{cost:g}" / f"pass{pass_no}" / slug(model) / f"{pod}-{plan_path.stem}.jsonl"
            out.parent.mkdir(parents=True, exist_ok=True)
            jobs.append((plan[:limit] if limit else plan, trajs, out))

    def one(job):
        plan, trajs, out = job
        return run_session(client, model, frames, plan, trajs, config, cost, out,
                           tag=f"session:{slug(model)}:c{cost:g}:p{pass_no}:{out.stem}")

    with ThreadPoolExecutor(workers) as pool:
        for future in as_completed([pool.submit(one, j) for j in jobs]):
            try:
                print("finished", future.result())
            except SpendCapReached as e:
                print("spend cap:", e)
            except Exception:
                traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("part", choices=("probe", "sessions"))
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--pass", dest="pass_no", type=int, default=1)
    parser.add_argument("--cost-per-look", type=float, default=2.0)
    parser.add_argument("--limit", type=int, help="pilot: at most this many probes, or episodes per session")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--cap", type=float, default=45.0)
    parser.add_argument("--max-tokens", type=int, default=6144)
    parser.add_argument("--timeout", type=int, default=600, help="seconds per model call")
    args = parser.parse_args()
    ledger = Ledger(OUT / "api_spend.jsonl", args.cap)
    client = SailClient(env_key(), ledger, max_tokens=args.max_tokens, timeout=args.timeout)
    trajectories, frames = load_trajectories(POD_ROOTS), FrameSource(keep=4 * args.workers)
    config = load_config(ROOT / "configs" / "time_pressure.json")
    print(f"{len(trajectories)} recorded runs; spent so far ${ledger.spent:.2f} of ${args.cap:.2f}")
    for model in args.models:
        if args.part == "probe":
            run_probe(client, frames, trajectories, model, args.pass_no, args.limit, args.workers)
        else:
            run_sessions(client, frames, trajectories, model, args.cost_per_look, args.pass_no, args.limit,
                         args.workers, config)
    print(f"spent ${ledger.spent:.2f} of ${args.cap:.2f}")


if __name__ == "__main__":
    main()
