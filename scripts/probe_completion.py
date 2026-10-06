"""Can the model tell, from the cameras alone, that a task is done? An offline probe on stored always-defer episodes.

For each episode the evaluator recorded whether the official checker was true at every step. This script picks a few
steps (before the first success, during it, after it is lost, the last step), cuts the three camera frames at that
step out of the stored MP4s, and asks the model one question: has the task been completed? The model sees only the
public goal text and the frames. The checker result is used only afterwards, to score the answer. Nothing here is an
episode or a benchmark score, and the question is not the supervision loop's, so this measures how legible
completion is, not how the model supervises.

  python scripts/probe_completion.py --roots runs/stage2_remote/always_defer --model claude-opus-5-5 \\
      --per-episode 6 --max-calls 150 --dry-run
"""
import argparse
import base64
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

from robot_benchmark.adapters.http import request_json
from robot_benchmark.contracts import CAMERAS

QUESTION = ('The robot was asked: "{goal}"\nThree camera views of the robot and kitchen at one moment follow. '
            "Has the task been completed at this moment? Judge only from what the images show.")
FORMAT = {"type": "json_schema", "schema": {"type": "object", "properties": {"complete": {"type": "boolean"}},
                                            "required": ["complete"], "additionalProperties": False}}
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0)}  # USD per million input, output tokens


def pick_steps(timeline, per_episode, last_step):
    """Steps (multiples of the recording interval are filtered by the caller) spread over the checker timeline:
    not-yet-complete moments at 50% and 90% of the way to the first success, complete moments just after, in the
    middle of and at the end of the true span, and the final step. Without a success, spread over the run."""
    true = [s for s, ok in timeline if ok]
    picks = []
    if true:
        first, final = true[0], true[-1]
        picks += [("before", first // 2), ("before", int(first * 0.9)), ("during", first + 5),
                  ("during", (first + final) // 2), ("during", final)]
        if final < last_step:
            picks.append(("after_lost", min(last_step, final + 40)))
    else:
        picks += [("never", int(last_step * f)) for f in (0.25, 0.5, 0.75, 1.0)]
    picks.append(("end", last_step))
    seen, out = set(), []
    for label, step in picks:
        if step not in seen and 0 <= step <= last_step:
            seen.add(step)
            out.append((label, step))
    return out[:per_episode]


def window_steps(timeline, low, high, stride, interval):
    """Steps from `low` to `high` around the checker's first success (negative = before), every `stride` steps. Shows
    where the model's answer flips relative to the checker, i.e. how long visual completion precedes it."""
    true = [s for s, ok in timeline if ok]
    if not true:
        return []
    last = (timeline[-1][0] // interval) * interval
    steps = [(true[0] + k) // interval * interval for k in range(low, high + 1, stride)]
    return [("window", s) for s in sorted(set(steps)) if 0 <= s <= last]


def frames(folder, step, interval):
    import cv2
    out = {}
    for camera in CAMERAS:
        name = camera.replace("video.", "")
        capture = cv2.VideoCapture(str(folder / "videos" / f"{name}.mp4"))
        capture.set(cv2.CAP_PROP_POS_FRAMES, step // interval)
        ok, image = capture.read()
        capture.release()
        if not ok:
            return None
        out[camera] = base64.b64encode(cv2.imencode(".png", image)[1].tobytes()).decode()
    return out


def ask_with_retries(model, goal, images, key, attempts=4):
    """The probe can run for an hour; a dropped connection must cost one call, not the run."""
    for attempt in range(attempts):
        try:
            return ask(model, goal, images, key)
        except Exception as error:
            if attempt == attempts - 1:
                print(f"giving up on one call: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
                return None
            time.sleep(10 * (attempt + 1))


def ask(model, goal, images, key):
    content = [{"type": "text", "text": QUESTION.format(goal=goal)}]
    for camera, data in images.items():
        content += [{"type": "text", "text": camera.replace("video.", "")},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}]
    payload = {"model": model, "max_tokens": 2000, "messages": [{"role": "user", "content": content}],
               "thinking": {"type": "adaptive", "display": "summarized"},
               "output_config": {"effort": "medium", "format": FORMAT}}
    response = request_json("https://api.anthropic.com/v1/messages", payload,
                            {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
    text = "".join(b["text"] for b in response["content"] if b["type"] == "text")
    thinking = " ".join(b.get("thinking", "") for b in response["content"] if b["type"] == "thinking")
    return json.loads(text)["complete"], thinking, response.get("usage", {})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, nargs="+", required=True, help="always_defer episode roots")
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--per-episode", type=int, default=6)
    parser.add_argument("--max-calls", type=int, default=200)
    parser.add_argument("--window", type=int, nargs=2, metavar=("LOW", "HIGH"),
                        help="instead of spread-out steps, probe every --stride steps from LOW to HIGH around the first success")
    parser.add_argument("--stride", type=int, default=10)
    parser.add_argument("--policy-seed", type=int, help="with --window: keep only this policy seed, one episode per task and scene")
    parser.add_argument("--output", type=Path, default=Path("runs/probes/completion.json"))
    parser.add_argument("--dry-run", action="store_true", help="print the plan and a cost estimate, no API calls")
    args = parser.parse_args()
    plan = []
    for root in args.roots:
        for manifest_path in sorted(root.glob("**/manifest.json")):
            folder = manifest_path.parent
            manifest = json.loads(manifest_path.read_text())
            try:
                result = json.loads((folder / "result.json").read_text())
                timeline = [(e["step"], bool(e["success"])) for e in map(json.loads, (folder / "evaluator" / "events.jsonl").read_text().splitlines())]
            except (OSError, ValueError):
                continue
            if manifest.get("artifact_type") != "episode" or result["status"] == "infrastructure_error" or not (folder / "videos").is_dir():
                continue
            interval = manifest["video_record_interval"]
            if args.window and args.policy_seed is not None and manifest["policy_seed"] != args.policy_seed:
                continue
            picks = (window_steps(timeline, args.window[0], args.window[1], args.stride, interval) if args.window
                     else pick_steps(timeline, args.per_episode, (timeline[-1][0] // interval) * interval))
            for label, step in picks:
                step = (step // interval) * interval
                truth = dict(timeline).get(step)
                first = next((s for s, ok in timeline if ok), None)
                plan.append({"folder": folder, "task": manifest["task"], "scene": manifest["scene_seed"], "policy": manifest["policy_seed"],
                             "goal": result["goal"], "step": step, "label": label, "interval": interval, "truth": truth,
                             "relative_to_first_success": None if first is None else step - first})
    plan = plan[:args.max_calls]
    rate_in, rate_out = PRICES.get(args.model, (4.0, 20.0))
    print(f"{len(plan)} calls over {len({p['folder'] for p in plan})} episodes; estimated cost about "
          f"${len(plan) * (1500 * rate_in + 400 * rate_out) / 1e6:.2f} (1,500 input and 400 output tokens each)")
    by_label = defaultdict(int)
    for p in plan:
        by_label[(p["label"], p["truth"])] += 1
    print(dict(by_label))
    if args.dry_run:
        return 0
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return 2
    rows = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    stream_path = args.output.with_suffix(".jsonl")  # one line per answer, written as it arrives
    done = {(r["folder"], r["step"]) for r in map(json.loads, stream_path.read_text().splitlines())} if stream_path.exists() else set()
    with stream_path.open("a") as stream:
        for p in plan:
            if (str(p["folder"]), p["step"]) in done:
                continue
            images = frames(p["folder"], p["step"], p["interval"])
            if images is None:
                continue
            asked = ask_with_retries(args.model, p["goal"], images, key)
            if asked is None:
                continue
            answer, thinking, usage = asked
            row = {**{k: (str(v) if k == "folder" else v) for k, v in p.items()}, "answer": answer, "thinking": thinking, "usage": usage}
            stream.write(json.dumps(row) + "\n")
            stream.flush()
            print(p["task"], p["scene"], p["step"], p["label"], "truth", p["truth"], "answer", answer, flush=True)
    rows = [json.loads(line) for line in stream_path.read_text().splitlines()]
    args.output.write_text(json.dumps(rows, indent=1) + "\n")
    stats = defaultdict(lambda: [0, 0])
    for r in rows:
        stats[r["task"]][0] += r["answer"] == r["truth"]
        stats[r["task"]][1] += 1
    for task, (right, total) in sorted(stats.items()):
        print(f"{task:26s} {right}/{total} correct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
