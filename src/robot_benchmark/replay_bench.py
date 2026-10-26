"""Replay benchmark: open models supervise recorded uninterrupted robot runs (design:
docs/superpowers/specs/2026-10-24-replay-benchmark-design.md).

Without re-prompting, a supervisor can only let the policy run N more steps or declare "done"; neither changes the
robot's trajectory, so a recorded always-defer run of the plain policy stands in for a live episode. Two parts:
- the probe: one call per sampled moment, "is the task done now?", labelled by the recorded checker (skill 1);
- sessions: the model chooses when to look and when to declare, across anonymous policies (skills 1 and 2).

Analysis and development only: nothing here is in the contract hash, and records are kind `replay_development`,
never mixed with the October 15-16 benchmark scores. Models never see checker values of the current episode."""
import base64
from collections import OrderedDict, defaultdict
import io
import json
from pathlib import Path
import random
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid

from robot_benchmark.time_score import STEPS_PER_SECOND, score_episode

CAMERAS = ("robot0_agentview_left", "robot0_agentview_right", "robot0_eye_in_hand")
FRAME_STEP = 10  # the recorded videos hold steps 0, 10, 20, ... plus the final step
MIN_WAIT, MAX_WAIT = 10, 400
AMBIGUITY_STEPS = 40  # frames this close before the checker's first true step are not probed (checker lag ~20 steps)
MAX_INVALID = 3

PROBE_SYSTEM = """You check whether a robot has finished a task in a simulated kitchen.
Each image shows three camera views side by side: left, right, and the camera on the robot's wrist.
You see the views now, 2 seconds earlier and 5 seconds earlier.
Reply with exactly one JSON object and no other text:
{"done": true} if the task is complete now, or {"done": false} if it is not."""

SESSION_SYSTEM = """You supervise a robot arm controlled by a learned policy in a simulated kitchen.
You cannot move the robot or change its instruction: the policy keeps working on the task by itself.
Your job is to decide when to look at the robot and when to declare the task done.
Several anonymous policies of different ability, named by letters, take turns in separate episodes.
Records of finished episodes in this session come first; use them to learn how each policy behaves.
Each image shows three camera views side by side: left, right, and the camera on the robot's wrist.
At each look you see the views now and, after the first look, at two earlier moments since your last look.
Reply with exactly one JSON object and no other text:
{"op": "wait", "steps": N} lets the robot run N more control steps before your next look
(N from 10 to 400, rounded up to a multiple of 10; 20 steps = 1 second).
{"op": "done"} declares the task complete and ends the episode. It succeeds only if the task is
actually complete at this moment; declaring before it is complete is a failure.
If the step budget runs out before you declare, the episode fails.
Score: a failure scores 0. A success scores max(0, 1 - (robot seconds + looks x C) / deadline),
where C seconds are charged for every look (every reply you make, including the first).
Look often enough to notice completion quickly, but each look costs time."""


# ---------------------------------------------------------------------------------------------------------------
# Trajectories and frames

def load_trajectories(roots):
    """Recorded always-defer runs under `roots` (a pod name -> folder mapping): one dict per usable run. Runs with an
    infrastructure error or with the checker true at step 0 are skipped."""
    out = []
    for pod, root in roots.items():
        for result_path in sorted(Path(root).rglob("result.json")):
            folder = result_path.parent
            manifest = folder / "manifest.json"
            if not manifest.exists() or not (folder / "videos").is_dir():
                continue
            m, r = json.loads(manifest.read_text()), json.loads(result_path.read_text())
            if m.get("kind") != "baseline_always_defer" or r.get("infrastructure_error"):
                continue
            events = [json.loads(line) for line in (folder / "evaluator" / "events.jsonl").read_text().splitlines()
                      if line.strip()]
            success = [bool(e.get("success")) for e in events]
            if success and success[0]:
                continue
            first_true = {}
            for e in events:
                for name, value in e.items():
                    if name != "step" and value is True and name not in first_true:
                        first_true[name] = e["step"]
            out.append({"id": f"{pod}/{m['policy']['backend']}/{m['task']}/{r['scene_seed']}", "pod": pod,
                        "folder": str(folder), "task": m["task"], "backend": m["policy"]["backend"],
                        "scene": r["scene_seed"], "goal": r["goal"], "steps": r["steps"], "success_by_step": success,
                        "first_success": next((i for i, ok in enumerate(success) if ok), None),
                        "first_true": first_true, "logged": set(events[0]) - {"step", "success"} if events else set()})
    return out


def frame_index(step, steps):
    """Index of the recorded frame for `step` (a multiple of 10, or the final step)."""
    if step >= steps:
        return steps // FRAME_STEP + (1 if steps % FRAME_STEP else 0)
    if step % FRAME_STEP:
        raise ValueError(f"step {step} has no recorded frame")
    return step // FRAME_STEP


def decode_frame(path, index):
    """One 256 x 256 RGB frame of a video, by frame number (ffmpeg). Pixel-identical to decoding the whole video and
    taking frame `index` (checked on 71 frames of 6 recorded runs, October 25)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"select=eq(n\\,{index})",
                          "-fps_mode", "passthrough", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         check=True, capture_output=True).stdout
    if len(raw) != 256 * 256 * 3:
        raise ValueError(f"{path}: frame {index} not found")
    return raw


class FrameSource:
    """Tiled PNGs (three cameras side by side) at any recorded step. Each frame is decoded from its video when first
    needed and only finished PNGs are kept (at most `keep`, least recently used dropped first). The earlier version
    kept whole decoded runs in memory (about 240 MB each, up to 32 per process); with 15 processes in parallel that
    exhausted the Mac's memory, the likely cause of the October 24 and 25 shutdowns."""

    def __init__(self, keep=64):
        self.cache, self.keep, self.checked, self.lock = OrderedDict(), keep, set(), threading.Lock()

    def check(self, traj):
        """Each camera video must hold one frame per recorded step (videos/manifest.json, written by the recorder)."""
        if traj["id"] in self.checked:
            return
        manifest = json.loads((Path(traj["folder"]) / "videos" / "manifest.json").read_text())
        expected = frame_index(traj["steps"], traj["steps"]) + 1
        counts = {c: manifest[f"video.{c}"]["frames"] for c in CAMERAS}
        if any(n != expected for n in counts.values()):
            raise ValueError(f"{traj['id']}: expected {expected} frames, got {counts}")
        self.checked.add(traj["id"])

    def png(self, traj, step):
        from PIL import Image
        key = (traj["id"], step)
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
        self.check(traj)
        index = frame_index(step, traj["steps"])
        tiled = Image.new("RGB", (256 * len(CAMERAS), 256))
        for i, camera in enumerate(CAMERAS):
            raw = decode_frame(Path(traj["folder"]) / "videos" / f"{camera}.mp4", index)
            tiled.paste(Image.frombytes("RGB", (256, 256), raw), (256 * i, 0))
        buffer = io.BytesIO()
        tiled.save(buffer, format="PNG")
        with self.lock:
            self.cache[key] = buffer.getvalue()
            while len(self.cache) > self.keep:
                self.cache.popitem(last=False)
        return self.cache.get(key, buffer.getvalue())


def snap(step):
    """The recorded step at or before `step` (frames exist every 10 steps)."""
    return max(0, step - step % FRAME_STEP)


# ---------------------------------------------------------------------------------------------------------------
# Probe sampling (skill 1)

def sample_probes(trajectories, seed=0):
    """Moments to ask "is it done?", labelled by the checker. Per successful run: positives at the first recorded
    frame at or after the first success and 5 s later (if the checker is still true there), negatives 2 s and 10 s
    before the first success (outside the ambiguity band). Per run that never succeeds: negatives at the middle and
    the end. `seed` only orders the probes."""
    probes = []
    for t in trajectories:
        first, last = t["first_success"], t["steps"]
        if first is None:
            candidates = [(snap(last // 2), False), (last, False)]
        else:
            at = first if first % FRAME_STEP == 0 else first + FRAME_STEP - first % FRAME_STEP
            candidates = [(min(at, last), True), (min(at + 100, last), True),
                          (snap(first - AMBIGUITY_STEPS), False), (snap(first - 200), False)]
        seen = set()
        for step, positive in candidates:
            if step in seen or step < 0 or (not positive and first is not None and step > first - AMBIGUITY_STEPS):
                continue
            seen.add(step)
            label = t["success_by_step"][min(step, len(t["success_by_step"]) - 1)]
            if positive and not label:
                continue  # success was lost again by then
            probes.append({"probe": f"{t['id']}@{step}", "traj": t["id"], "step": step, "label": label})
    random.Random(seed).shuffle(probes)
    return probes


def probe_content(frames, traj, step):
    content = [{"type": "text", "text": f"Task: {traj['goal']}"}]
    for label, at in (("Now", step), ("2 seconds earlier", step - 40), ("5 seconds earlier", step - 100)):
        content += [{"type": "text", "text": f"{label}:"}, image_block(frames.png(traj, snap(max(0, at)) if at < step
                                                                                  else step))]
    content.append({"type": "text", "text": "Is the task complete now? Reply with the JSON object only."})
    return content


# ---------------------------------------------------------------------------------------------------------------
# Model calls and spending

def image_block(png_bytes):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                        "data": base64.b64encode(png_bytes).decode()}}


PRICES = {  # dollars per million input / output tokens (Sail's "ASAP" list prices, docs.sailresearch.com/pricing,
    # checked October 25; Kimi K2.6 assumed equal to K3)
    "moonshotai/Kimi-K3": (2.50, 12.50), "moonshotai/Kimi-K2.6": (2.50, 12.50),
    "deepseek-ai/DeepSeek-V4.1-Flash-1017": (0.09, 0.30),
    "zai-org/GLM-5.3-Flash": (0.11, 0.35), "google/gemma-4-31B-it": (0.40, 0.60),
}


class SpendCapReached(RuntimeError):
    pass


def condition_of(tag):
    """(part, reasoning level) of a ledger tag: probe tags read `probe[:level]:<probe id>`, session tags carry
    `@level` when a level was requested."""
    if tag.startswith("probe"):
        fields = tag.split(":")
        return "probe", fields[1] if len(fields) > 2 and fields[1] in EFFORTS else "default"
    return "session", tag.split("@")[1].split("#")[0].split(":")[0] if "@" in tag else "default"


def estimated_dollars(entries):
    """Estimated dollars of each ledger entry, in order. A timed-out call reports no usage, and Sail may still have run
    and billed it, so it is counted at the 99th-percentile cost of that model's replies in the same part and reasoning
    level (at its written worst case while fewer than 20 such replies exist). Written worst cases (up to $0.41 for a
    Kimi call allowed 32,768 output tokens) made the cap stop runs far below real spending on October 25; the ledger
    file keeps the raw values."""
    replies = defaultdict(list)
    for e in entries:
        if not e["tag"].endswith(":timeout") and ":http" not in e["tag"]:
            replies[(e["model"], condition_of(e["tag"]))].append(e["dollars"])
    p99 = {k: sorted(v)[int(0.99 * (len(v) - 1))] for k, v in replies.items() if len(v) >= 20}
    return [min(e["dollars"], p99.get((e["model"], condition_of(e["tag"])), e["dollars"]))
            if e["tag"].endswith(":timeout") else e["dollars"] for e in entries]


class Ledger:
    """Shared dollar ledger: every call reserves a worst case before it is sent and settles from reported usage; a
    call with no usage (a timeout) is written at its worst case. Appends one line per settled call to `path`."""

    def __init__(self, path, cap):
        self.path, self.cap, self.lock = Path(path), cap, threading.Lock()
        self.spent, self.reserved = self._settled(), 0.0

    def _settled(self):
        """Estimated dollars spent (`estimated_dollars`), including calls by other processes sharing the file."""
        if not self.path.exists():
            return 0.0
        return sum(estimated_dollars([json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]))

    @staticmethod
    def cost(model, input_tokens, output_tokens):
        i, o = PRICES[model]
        return (input_tokens * i + output_tokens * o) / 1e6

    def reserve(self, model, input_estimate, max_tokens):
        worst = self.cost(model, input_estimate, max_tokens)
        with self.lock:
            self.spent = self._settled()
            if self.spent + self.reserved + worst > self.cap:
                raise SpendCapReached(f"spent {self.spent:.2f} + reserved {self.reserved:.2f} + {worst:.3f} > cap")
            self.reserved += worst
        return worst

    def settle(self, model, worst, usage, tag):
        dollars = worst if usage is None else self.cost(
            model, usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
            + usage.get("cache_read_input_tokens", 0), usage.get("output_tokens", 0))
        with self.lock:
            self.reserved -= worst
            self.spent += dollars
            with self.path.open("a") as f:
                f.write(json.dumps({"model": model, "tag": tag, "dollars": dollars, "usage": usage,
                                    "time": time.time()}) + "\n")
        return dollars


EFFORTS = {  # requested reasoning level -> request fields (Sail Messages API: `thinking`, `output_config.effort`)
    "default": {},  # nothing sent: the model's own default, which differs by model (the October 24-25 main runs)
    "off": {"thinking": {"type": "disabled"}},
    **{level: {"output_config": {"effort": level}} for level in ("minimal", "low", "medium", "high", "xhigh")},
}


class SailClient:
    """Anthropic-compatible Messages API (Sail Research) with retries and the shared ledger. `effort` selects the
    requested reasoning level (EFFORTS); every reply records why it stopped and whether it returned a thinking block."""

    def __init__(self, key, ledger, endpoint="https://api.sailresearch.com/v1/messages", max_tokens=2048,
                 timeout=180, effort="default"):
        self.key, self.ledger, self.endpoint, self.max_tokens, self.timeout = key, ledger, endpoint, max_tokens, timeout
        self.effort = effort

    def call(self, model, system, content, tag=""):
        images = sum(1 for c in content if c["type"] == "image")
        text = sum(len(c.get("text", "")) for c in content) + len(system)
        body = json.dumps({"model": model, "max_tokens": self.max_tokens, "system": system,
                           "messages": [{"role": "user", "content": content}], **EFFORTS[self.effort]}).encode()
        # One idempotency key per call, reused on every retry: Sail then returns the original reply instead of running
        # (and billing) the request again, and answers 409 while the original is still running.
        key, attempt, waits = str(uuid.uuid4()), 0, 0
        while True:
            worst = self.ledger.reserve(model, 3000 * images + text // 2 + 1000, self.max_tokens)
            started, usage = time.time(), None
            try:
                request = urllib.request.Request(self.endpoint, data=body, headers={
                    "content-type": "application/json", "x-api-key": self.key, "authorization": f"Bearer {self.key}",
                    "anthropic-version": "2023-06-01", "anthropic-idempotency-key": key})
                reply = json.loads(urllib.request.urlopen(request, timeout=self.timeout).read())
                usage = reply.get("usage")
                blocks = reply.get("content", [])
                text_out = "".join(c.get("text", "") for c in blocks if c.get("type") == "text")
                return {"text": text_out, "usage": usage, "seconds": time.time() - started, "attempts": attempt + 1,
                        "stop_reason": reply.get("stop_reason"), "effort": self.effort,
                        "thinking_chars": sum(len(c.get("thinking", "")) for c in blocks if c.get("type") == "thinking"),
                        "dollars": self.ledger.settle(model, worst, usage, tag)}
            except urllib.error.HTTPError as e:
                # Sail has returned transient 400s that succeed when re-sent (October 25), so every status except an
                # authentication or not-found error is retried; the error text is kept in the ledger.
                message = e.read()[:300].decode(errors="replace")
                self.ledger.settle(model, worst, {"input_tokens": 0, "output_tokens": 0},
                                   f"{tag}:http:{e.code}:{message}")
                if e.code == 409 and waits < 40:  # the original request is still running: ask again later, same key
                    waits += 1
                    time.sleep(float(e.headers.get("Retry-After") or 30) if e.headers else 30)
                    continue
                if e.code == 404 and attempt > 0 and "not_found" in message and attempt < 3:
                    # Sail sometimes loses the request behind an idempotency key after a timeout ("response ... not
                    # found", October 25): submit afresh under a new key.
                    key = str(uuid.uuid4())
                elif e.code in (401, 403, 404) or attempt == 3:
                    raise
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                self.ledger.settle(model, worst, None, tag + ":timeout")
                if attempt == 3:
                    raise
            time.sleep((5, 20, 60)[min(attempt, 2)])
            attempt += 1


def parse_json_reply(text):
    """The last JSON object in a reply, or None."""
    for match in reversed(list(re.finditer(r"\{[^{}]*\}", text or ""))):
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
    return None


def parse_probe(text):
    obj = parse_json_reply(text)
    return obj.get("done") if isinstance(obj, dict) and isinstance(obj.get("done"), bool) else None


def parse_decision(text):
    """("done", None), ("wait", N) with N rounded up to a multiple of 10 within [10, 400], or (None, reason)."""
    obj = parse_json_reply(text)
    if not isinstance(obj, dict):
        return None, "no JSON object"
    if obj.get("op") == "done":
        return "done", None
    if obj.get("op") == "wait" and isinstance(obj.get("steps"), (int, float)) and obj["steps"] > 0:
        n = int(-(-obj["steps"] // FRAME_STEP) * FRAME_STEP)
        return "wait", min(MAX_WAIT, max(MIN_WAIT, n))
    return None, f"invalid decision {obj}"


# ---------------------------------------------------------------------------------------------------------------
# Sessions (skills 1 and 2)

def experience_line(index, record):
    head = f"Episode {index + 1}: policy {record['label']}, task \"{record['goal']}\" -"
    seconds = record["final_step"] / STEPS_PER_SECOND
    if record["outcome"] == "success":
        return f"{head} success: declared done at {seconds:.1f} s after {record['looks']} looks."
    if record["outcome"] == "false_done":
        return f"{head} failure: declared done at {seconds:.1f} s after {record['looks']} looks, but the task was not complete."
    return f"{head} failure: did not declare done before the step budget ran out ({record['looks']} looks)."


def task_text(traj, config, cost_per_look):
    spec = config["tasks"][traj["task"]]
    lines = [f"Task: {traj['goal']}",
             f"Step budget: {traj['steps']} steps ({traj['steps'] / STEPS_PER_SECOND:.1f} s). "
             f"Deadline for scoring: {spec['deadline_seconds']:.1f} s. Cost per look C = {cost_per_look:g} s."]
    story = spec.get("story")
    if story and story.get("limit_seconds") is not None:
        lines.append(f"{story['text']} The task fails if more than {story['limit_seconds']:g} s pass from that event "
                     "until you declare done.")
    return "\n".join(lines)


def run_episode(client, model, frames, traj, label, experience, config, cost_per_look, tag="", on_look=None):
    """One supervised replay of a recorded run. Returns the episode record (looks, outcome, value). `on_look` is called
    with every look as soon as the reply arrives, so a run stopped mid-episode keeps the replies it paid for."""
    step, previous, looks, invalid, note = 0, 0, [], 0, ""
    header = [{"type": "text", "text": "Records of finished episodes in this session:\n" +
               ("\n".join(experience) if experience else "(none yet)")},
              {"type": "text", "text": f"Current episode: policy {label}.\n" + task_text(traj, config, cost_per_look)}]
    while True:
        final = step >= traj["steps"]
        content = list(header)
        history = ", ".join(f"step {l['step']}: {l['decision']}" for l in looks) or "none"
        content.append({"type": "text", "text": f"Your earlier looks this episode: {history}.\n"
                                                f"Now: step {step} ({step / STEPS_PER_SECOND:.1f} s), "
                                                f"{max(0, traj['steps'] - step)} steps left, looks so far {len(looks)}."
                                                + (" The step budget is used up: declare done now or the episode fails."
                                                   if final else "") + note})
        content += [{"type": "text", "text": f"Now (step {step}):"}, image_block(frames.png(traj, step))]
        if step > 0:
            for at in sorted({snap(previous + (step - previous) // 2), previous}, reverse=True):
                if at < step:
                    content += [{"type": "text", "text": f"Earlier (step {at}):"}, image_block(frames.png(traj, at))]
        reply = client.call(model, SESSION_SYSTEM, content, tag=tag)
        op, arg = parse_decision(reply["text"])
        looks.append({"step": step, "decision": {"done": "done", "wait": f"wait {arg}"}.get(op, "invalid"), "raw": reply["text"][-500:],
                      "usage": reply["usage"], "seconds": reply["seconds"], "dollars": reply["dollars"],
                      "stop_reason": reply.get("stop_reason"), "thinking_chars": reply.get("thinking_chars"),
                      "attempts": reply.get("attempts")})
        if on_look:
            on_look(looks[-1])
        if op is None:
            invalid += 1
            note = f"\nYour previous reply was invalid ({arg}). Reply with one JSON object."
            if invalid >= MAX_INVALID:
                outcome = "invalid"
                break
            continue
        invalid, note = 0, ""
        if op == "done":
            outcome = "success" if traj["success_by_step"][min(step, len(traj["success_by_step"]) - 1)] else "false_done"
            break
        if final:
            outcome = "timeout"
            break
        previous, step = step, min(step + arg, traj["steps"])
    episode = {"task": traj["task"], "steps": step, "llm": True, "agent": model, "calls": len(looks),
               "success": outcome == "success", "first_true": traj["first_true"], "logged": traj["logged"],
               "decisions": [{"step_before": l["step"]} for l in looks]}
    scored = score_episode(episode, {**config, "call_seconds": {model: cost_per_look}})
    return {"traj": traj["id"], "pod": traj["pod"], "task": traj["task"], "backend": traj["backend"],
            "scene": traj["scene"], "label": label, "goal": traj["goal"], "outcome": outcome, "final_step": step,
            "looks": len(looks), "first_wait": next((int(l["decision"].split()[1]) for l in looks
                                                     if l["decision"].startswith("wait")), None),
            "first_success": traj["first_success"], "scored_success": scored["success"], "value": scored["value"],
            "charged_seconds": scored["charged_seconds"], "story": scored["story"], "cost_per_look": cost_per_look,
            "model": model, "effort": getattr(client, "effort", "default"), "dollars": sum(l["dollars"] for l in looks),
            "decisions": looks}


def run_session(client, model, frames, plan, trajectories, config, cost_per_look, out_path, tag=""):
    """Episodes of one plan in order, appending each record to `out_path` (JSONL); resumes after the last record.
    Every look is also appended to `<out_path stem>.looks.jsonl` when it happens, including looks of an episode that
    a stop interrupts (that episode is replayed from its start on resume; its interrupted attempt stays in the file)."""
    out_path = Path(out_path)
    looks_path = out_path.with_name(out_path.stem + ".looks.jsonl")
    done = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()] if out_path.exists() else []
    experience = [experience_line(i, r) for i, r in enumerate(done)]
    for index, entry in enumerate(plan):
        if index < len(done):
            continue
        traj = trajectories.get((entry["backend"], entry["task"], entry["scene_seed"]))
        if traj is None:
            record = {"index": index, "skipped": "no usable recorded run", **entry}
        else:
            attempt = time.time()

            def save(look, index=index, attempt=attempt):
                with looks_path.open("a") as f:
                    f.write(json.dumps({"index": index, "attempt": attempt, **look}) + "\n")

            record = {"index": index, "attempt": attempt,
                      **run_episode(client, model, frames, traj, entry["policy_label"], experience, config,
                                    cost_per_look, tag=f"{tag}#{index}", on_look=save)}
            experience.append(experience_line(len(experience), record))
        with out_path.open("a") as f:
            f.write(json.dumps(record) + "\n")
    return out_path
