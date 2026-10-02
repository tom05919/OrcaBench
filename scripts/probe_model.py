"""Probe the live model API with the exact adapter request before renting a GPU.

Sends real model calls through HTTPAgent, the same code a run uses, and reports
for each call whether the API accepted the request, how the reply parsed,
whether the decision validates, latency, and token usage including thinking.
No simulator or policy is involved, and nothing here is an episode or a score.

Observations come from a recorded episode (`--episode`, replaying the stored
frames and fields exactly as that run sent them) or, without one, from two
synthetic observations: a first call and a mid-episode call carrying the full
15-image payload. `--efforts` compares effort levels, which runs keep fixed.

The adapter reads the key named by the agent config (`ANTHROPIC_API_KEY`). Every
call is billed. Exit status: 0 if every request succeeded and every reply parsed
strictly, 1 if a request failed, 2 if a reply needed recovery or was unparsable.
"""
import argparse
import base64
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
import struct
from time import perf_counter
import zlib

from robot_benchmark.adapters.agents import DECISION_FORMAT, HTTPAgent
from robot_benchmark.contracts import CAMERAS, PROPRIO, Limits, validate_decision

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_GOAL = "Close the fridge door."
EFFORTS = ("low", "medium", "high", "xhigh", "max")


def png_data_url(size=256, shade=0):
    """A small gradient PNG built with the standard library (no imaging dependency)."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\x00" + bytes((x + shade) % 256 for x in range(size) for _ in range(3)) for _ in range(size))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode()


def synthetic_observations():
    proprio = {name: [0.0] * dim for name, dim in PROPRIO.items()}
    proprio["state.gripper_qpos"] = [0.0206, -0.0206]
    card = {"id": "native_instruction", "prompt": SYNTHETIC_GOAL,
            "description": "Card for the task's native RoboCasa instruction (the goal text)",
            "performance": {"status": "untested", "trials": 0, "success_rate": None, "conditions": []}}
    first = {"schema_version": 4, "goal": SYNTHETIC_GOAL,
             "images": {camera: png_data_url(shade=i * 40) for i, camera in enumerate(CAMERAS)},
             "proprio": proprio, "interval_frames": [], "reference_prompts": [card],
             "active_instruction": None, "step": 0, "remaining_steps": 900, "remaining_decisions": 100,
             "max_interval": 400, "history": [], "last_error": None}
    mid = copy.deepcopy(first)
    mid.update({"active_instruction": SYNTHETIC_GOAL, "step": 200, "remaining_steps": 700, "remaining_decisions": 99,
                "interval_frames": [{"step": step, "images": {camera: png_data_url(shade=step % 256) for camera in CAMERAS},
                                     "proprio": proprio} for step in (40, 80, 120, 160)],
                "history": [{"decision_index": 1, "step_before": 0, "accepted": True, "step_after": 200,
                             "decision": {"op": "run_policy", "prompt": SYNTHETIC_GOAL, "steps": 200}}]})
    return [("synthetic-first-call", first), ("synthetic-mid-episode", mid)]


def replayed_observations(episode, indices=None):
    """Rebuild the observations an episode sent, with images restored from its frame files."""
    episode = Path(episode)
    lines = [line for line in (episode / "observations.jsonl").read_text().splitlines() if line.strip()]
    chosen = range(len(lines)) if indices is None else indices
    result = []
    for index in chosen:
        if not 0 <= index < len(lines):
            raise ValueError(f"observation index {index} is outside 0..{len(lines) - 1}")
        stored = json.loads(lines[index])

        def load(relative):
            return "data:image/png;base64," + base64.b64encode((episode / relative).read_bytes()).decode()
        observation = dict(stored)
        observation["images"] = {camera: load(path) for camera, path in stored["images"].items()}
        observation["interval_frames"] = [{**frame, "images": {camera: load(path) for camera, path in frame["images"].items()}}
                                          for frame in stored.get("interval_frames", [])]
        result.append((f"{episode.name}#{index}", observation))
    return result


def check_decision(decision, observation):
    """The runner's validation: schema, range, then state (prompt needed, steps within budget)."""
    limits = Limits(max_steps=observation["step"] + observation["remaining_steps"],
                    max_interval=observation["max_interval"])
    decision = validate_decision(decision, limits)
    if decision["op"] == "run_policy" and "prompt" not in decision and observation["active_instruction"] is None:
        raise ValueError("run_policy requires a prompt when no instruction is active")
    if decision.get("steps", 0) > observation["remaining_steps"]:
        raise ValueError("requested interval exceeds remaining steps")
    return decision


def without_image_data(trace):
    """Keep the trace auditable without storing every base64 image again."""
    trace = copy.deepcopy(trace)
    for message in (trace.get("request", {}).get("body", {}).get("messages") or []):
        for block in message.get("content", []):
            if block.get("type") == "image":
                block["source"]["data"] = f"<{len(block['source']['data'])} base64 characters omitted>"
    return trace


def probe_call(agent, label, observation):
    start = perf_counter()
    row = {"observation": label, "model": agent.config["model"], "effort": agent.identity["output_config"]["effort"]}
    try:
        reply = agent.decide(copy.deepcopy(observation))
    except Exception as error:
        row.update({"ok": False, "error": f"{type(error).__name__}: {error}"})
    else:
        body = (agent.last_trace or {}).get("response", {}).get("body", {})
        row.update({"ok": True, "stop_reason": body.get("stop_reason"), "parse": reply.parse,
                    "raw_text": reply.raw_text, "decision": reply.decision, "usage": reply.usage,
                    "thinking_summary_chars": sum(len(block.get("thinking") or "") for block in body.get("content", [])
                                                  if block.get("type") == "thinking")})
        try:
            check_decision(reply.decision, observation)
            row["valid"], row["validation_error"] = True, None
        except ValueError as error:
            row["valid"], row["validation_error"] = False, str(error)
    row["seconds"] = round(perf_counter() - start, 2)
    row["retries"] = (agent.last_trace or {}).get("retries", [])
    row["trace"] = without_image_data(agent.last_trace or {})
    return row


def summarize(rows):
    groups = {}
    for row in rows:
        groups.setdefault((row["model"], row["effort"]), []).append(row)
    summary = []
    for (model, effort), group in groups.items():
        ok = [row for row in group if row["ok"]]
        output = [row["usage"].get("output_tokens", 0) for row in ok if isinstance(row.get("usage"), dict)]
        summary.append({
            "model": model, "effort": effort, "calls": len(group), "request_errors": len(group) - len(ok),
            "parse": {mode: sum(row.get("parse") == mode for row in ok) for mode in ("strict", "extracted", "unparsed")},
            "valid_decisions": sum(row.get("valid", False) for row in ok),
            "stop_reasons": sorted({str(row.get("stop_reason")) for row in ok}),
            "mean_output_tokens": round(sum(output) / len(output), 1) if output else None,
            "max_output_tokens": max(output) if output else None,
            "input_tokens": sum(row["usage"].get("input_tokens", 0) for row in ok if isinstance(row.get("usage"), dict)),
            "mean_seconds": round(sum(row["seconds"] for row in group) / len(group), 2),
            "retries": sum(len(row["retries"]) for row in group),
        })
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--agent-configs", type=Path, nargs="+", required=True)
    parser.add_argument("--efforts", nargs="+", choices=EFFORTS, default=["medium"])
    parser.add_argument("--episode", type=Path, help="recorded episode folder to replay observations from")
    parser.add_argument("--observation-indices", type=int, nargs="+", help="which recorded observations (default all)")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-calls", type=int, default=40, help="refuse to start a probe larger than this")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    observations = (replayed_observations(args.episode, args.observation_indices) if args.episode
                    else synthetic_observations())
    planned = len(args.agent_configs) * len(args.efforts) * len(observations) * args.repeats
    if args.repeats < 1 or planned > args.max_calls:
        parser.error(f"{planned} calls planned; raise --max-calls deliberately if that is intended")
    rows = []
    for path in args.agent_configs:
        config = json.loads(path.read_text())
        for effort in args.efforts:
            agent = HTTPAgent(config)
            # Probe-only override; runs keep the effort fixed in HTTPAgent._output_config.
            agent._output_config = lambda effort=effort: {"effort": effort, "format": copy.deepcopy(DECISION_FORMAT)}
            agent.identity["output_config"] = agent._output_config()
            for _ in range(args.repeats):
                for label, observation in observations:
                    rows.append(probe_call(agent, label, observation))
                    row = rows[-1]
                    print(json.dumps({key: row.get(key) for key in
                                      ("model", "effort", "observation", "ok", "error", "stop_reason", "parse",
                                       "valid", "seconds")}), flush=True)
    summary = summarize(rows)
    output = args.output or (PROJECT_ROOT / "runs" / "probes" /
                             f"probe-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(), "summary": summary,
                                  "calls": rows}, indent=2) + "\n")
    print(json.dumps({"output": str(output), "summary": summary}, indent=2))
    if any(not row["ok"] for row in rows):
        return 1
    return 0 if all(row["parse"] == "strict" for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
