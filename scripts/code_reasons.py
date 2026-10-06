"""Code why a model intervened, from its own recorded thinking summaries (model_api_traces.jsonl).

For every decision after the first, a small model reads only the supervising model's thinking summary and its
decision, and labels the stated reason. It never sees the checker, the plain run, or the outcome. The result is a
table of reasons by decision type, to compare with outcomes afterwards. Nothing here is an episode or a score.

  python scripts/code_reasons.py --roots runs/stage3_remote/opus-5-5 --coder claude-sonnet-5-5 \\
      --output runs/stage3_remote/reasons-opus.json
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

from robot_benchmark.adapters.http import request_json

REASONS = {
    "stalled": "the robot looks stuck, idle, hovering or not moving, so the model acts",
    "unclear_progress": "the model cannot tell from the images whether progress or completion has happened",
    "judges_done": "the model believes the task is complete",
    "budget": "the model's main reason is the steps or decisions remaining",
    "better_wording": "the model wants to try different instruction wording",
    "on_track": "the model sees progress and chooses to keep going",
    "other": "none of the above",
}
FORMAT = {"type": "json_schema", "schema": {"type": "object", "properties": {
    "reason": {"type": "string", "enum": list(REASONS)},
    "mentions_budget": {"type": "boolean"},
    "mentions_hover_or_stuck": {"type": "boolean"}},
    "required": ["reason", "mentions_budget", "mentions_hover_or_stuck"], "additionalProperties": False}}
PROMPT = ("A robot-supervising model wrote the note below while deciding what to do next, then made the decision "
          "shown. Label the main reason in the note.\n\nReason labels:\n{labels}\n\nNote: {note}\nDecision: {decision}\n"
          "mentions_budget: the note refers to steps or decisions remaining. mentions_hover_or_stuck: the note says the "
          "robot is hovering, stuck, idle or not moving.")


def decision_type(decision, active):
    if decision["op"] == "complete":
        return "complete"
    prompt = decision.get("prompt")
    if prompt is None:
        return "continue"
    return "restate" if prompt == active else "rewrite"


def episodes(root):
    for manifest_path in sorted(Path(root).glob("**/manifest.json")):
        folder = manifest_path.parent
        if (folder / "model_api_traces.jsonl").exists() and (folder / "decisions.jsonl").exists():
            yield folder, json.loads(manifest_path.read_text())


def thinking_text(response):
    body = response.get("body", response) if isinstance(response, dict) else response
    body = json.loads(body) if isinstance(body, str) else body
    return " ".join(b.get("thinking", "") for b in body.get("content", []) if b.get("type") == "thinking").strip()


def label(coder, note, decision, key):
    labels = "\n".join(f"- {name}: {text}" for name, text in REASONS.items())
    payload = {"model": coder, "max_tokens": 400, "messages": [{"role": "user", "content": PROMPT.format(
        labels=labels, note=note, decision=json.dumps(decision))}], "output_config": {"format": FORMAT}}
    response = request_json("https://api.anthropic.com/v1/messages", payload,
                            {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
    text = "".join(b["text"] for b in response["content"] if b["type"] == "text")
    return json.loads(text), response.get("usage", {})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, nargs="+", required=True)
    parser.add_argument("--coder", default="claude-sonnet-5-5")
    parser.add_argument("--max-calls", type=int, default=400)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return 2
    rows, calls, tokens = [], 0, [0, 0]
    for root in args.roots:
        for folder, manifest in episodes(root):
            result = json.loads((folder / "result.json").read_text())
            traces = {t["decision_index"]: t for t in map(json.loads, (folder / "model_api_traces.jsonl").read_text().splitlines())}
            decisions = [json.loads(line) for line in (folder / "decisions.jsonl").read_text().splitlines() if line.strip()]
            active = None
            for entry in decisions:
                decision = entry["decision"]
                kind = decision_type(decision, active)
                if decision["op"] == "run_policy" and decision.get("prompt") and active is None:
                    active = decision["prompt"]
                    continue  # the first call has no evidence to explain
                note = thinking_text(traces.get(entry["decision_index"], {}).get("response", {}))
                if not note or calls >= args.max_calls:
                    continue
                coded, usage = label(args.coder, note, {k: v for k, v in decision.items() if k != "prompt"} | ({"prompt": "<new text>"} if kind == "rewrite" else {}), key)
                calls += 1
                tokens[0] += usage.get("input_tokens", 0)
                tokens[1] += usage.get("output_tokens", 0)
                rows.append({"task": manifest["task"], "scene": manifest["scene_seed"], "policy": manifest["policy_seed"],
                             "decision_index": entry["decision_index"], "type": kind, "step": entry["step_before"],
                             "outcome": result["status"], **coded})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=1) + "\n")
    table = defaultdict(Counter)
    for r in rows:
        table[r["type"]][r["reason"]] += 1
    print(f"{calls} notes coded, {tokens[0]} input and {tokens[1]} output tokens")
    for kind, counts in sorted(table.items()):
        print(f"{kind:9s}", dict(counts.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
