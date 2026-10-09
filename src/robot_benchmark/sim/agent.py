"""The LLM supervisor for the abstract environment (B7, B8): same JSON decisions, reply schema, parsing and retries as the
real adapter, with a text observation, a raw experience record in every call, and the score stated in dollars.

Every call is billed; `Tracker` stops the study at a hard dollar limit. Sampling parameters are not available on these
models, so sampling noise is handled by repeats."""
import json
import os
import sys
import time

from ..adapters.agents import DECISION_FORMAT, RETRY_DELAYS_SECONDS, is_transient, parse_decision_text
from ..adapters.http import request_json
from ..contracts import ModelReply

SYSTEM_PROMPT = """You supervise a robot controlled by a learned policy, in a text simulation. Several policies, named
K, R and T, take turns in separate episodes of the same task. They differ in ability and reliability; you are not told
how. The records of earlier episodes come first. Learn from them what each policy tends to do, and use that when you
decide.
In each episode you may let the policy run for a number of steps, restart it with an instruction, or declare the task
complete. Physics pauses while you reason. At each decision you see one reading of how far along the task looks: "not
started", "early", "midway", "late" or "looks complete". Readings come from an imperfect perception system and can be
wrong in either direction. After a run you also see four readings sampled evenly from inside the interval just
executed, labeled by step. During an episode you do not receive task-success labels; after it ends, its record in the
history shows what happened.
Reply with exactly one JSON object and no other text, using one of:
{"op":"run_policy","prompt":"<your instruction>","steps":N}
{"op":"run_policy","steps":N}
{"op":"complete"}
N is a positive integer at most max_interval and remaining_steps. A prompt is required for the first run and may contain
at most 512 characters. Supplying a prompt, even the same text as before, restarts the policy: it discards its
unexecuted actions and requests new actions from the current physical state. Omitting the prompt continues the active
instruction and preserves unexecuted actions. Neither choice resets the physical world. Choose N to decide when to
observe again. Each response consumes one decision, including invalid responses. Budget exhaustion ends the episode.
Reserve a decision and step budget to declare completion. Complete ends the episode immediately and succeeds only if
the task is actually done. No new readings arrive between decisions.
Score: each episode earns +$1.00 if you declare completion correctly. Every response costs $0.02, invalid ones
included. Every second of robot time costs $0.002 (20 steps = 1 second). Maximize your total score over all episodes."""

PRICES = {  # USD per million tokens: input, output, cache write, cache read
    "claude-opus-5-5": (4.0, 20.0, 5.0, 0.20), "claude-sonnet-5-5": (2.0, 10.0, 2.5, 0.20)}


class BudgetExceeded(RuntimeError):
    pass


class Tracker:
    """Cumulative API spend from `usage`, with a hard stop checked before every call."""

    def __init__(self, limit, ledger=None):
        """`ledger` is a JSONL file of every call's cost, shared by all scripts, so the limit covers the whole study."""
        self.limit, self.calls, self.ledger = limit, 0, ledger
        self.spent = 0.0
        if ledger and os.path.exists(ledger):
            with open(ledger) as stream:
                self.spent = sum(json.loads(line)["usd"] for line in stream)

    def check(self):
        if self.spent >= self.limit:
            raise BudgetExceeded(f"API spend ${self.spent:.2f} reached the ${self.limit:.2f} limit")

    def add(self, model, usage, tag=""):
        i, o, w, r = PRICES[model]
        usd = (usage.get("input_tokens", 0) * i + usage.get("output_tokens", 0) * o
               + usage.get("cache_creation_input_tokens", 0) * w + usage.get("cache_read_input_tokens", 0) * r) / 1e6
        self.spent += usd
        self.calls += 1
        if self.ledger:
            with open(self.ledger, "a") as stream:
                stream.write(json.dumps({"model": model, "usd": usd, "tag": tag}) + "\n")


def compact(value):
    return json.dumps(value, separators=(",", ":"))


def current_block(obs):
    """The current episode as compact JSON: public fields only, no latent state and no experience."""
    history = [{k: e[k] for k in ("decision_index", "step_before", "decision", "accepted", "step_after", "reading", "error") if k in e}
               for e in obs["history"]]
    shown = {k: obs[k] for k in ("policy", "episode", "goal", "step", "remaining_steps", "remaining_decisions", "max_interval",
                                 "active_instruction", "reading", "interval_frames", "last_error")}
    shown["history"] = history
    return "Current episode:\n" + compact(shown)


def build_content(obs):
    blocks = []
    experience = obs.get("experience") or []
    if experience:
        blocks.append({"type": "text", "text": "Records of earlier episodes, oldest first:"})
        blocks += [{"type": "text", "text": compact(record)} for record in experience]
        blocks[-1]["cache_control"] = {"type": "ephemeral"}   # earlier episodes become cache reads
    blocks.append({"type": "text", "text": current_block(obs)})
    return blocks


class SimAgent:
    """Reads the observation produced by `sim.harness.SimEpisode.observation` and returns a decision."""

    def __init__(self, model, tracker, effort="medium", log=None):
        if model not in PRICES:
            raise ValueError(f"no price for {model}")
        self.model, self.tracker, self.effort, self.log = model, tracker, effort, log
        self.identity = {"kind": "model", "model": model, "effort": effort}
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self.last_trace, self.tag = None, ""

    def decide(self, obs):
        self.tracker.check()
        payload = {"model": self.model, "max_tokens": 4096, "system": [{"type": "text", "text": SYSTEM_PROMPT}],
                   "messages": [{"role": "user", "content": build_content(obs)}],
                   "thinking": {"type": "adaptive", "display": "summarized"},
                   "output_config": {"effort": self.effort, "format": DECISION_FORMAT}}
        headers = {"x-api-key": self.key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        response = None
        for attempt in range(len(RETRY_DELAYS_SECONDS) + 1):
            try:
                response = request_json("https://api.anthropic.com/v1/messages", payload, headers, timeout=180)
                break
            except Exception as error:
                if attempt == len(RETRY_DELAYS_SECONDS) or not is_transient(error):
                    raise
                print(f"transient API error, retrying: {type(error).__name__}", file=sys.stderr, flush=True)
                time.sleep(RETRY_DELAYS_SECONDS[attempt])
        usage = response.get("usage", {})
        self.tracker.add(self.model, usage, self.tag)
        text = "".join(b["text"] for b in response["content"] if b["type"] == "text")
        thinking = " ".join(b.get("thinking", "") for b in response["content"] if b["type"] == "thinking")
        decision, parse = parse_decision_text(text, response.get("stop_reason"))
        self.last_trace = {"thinking": thinking, "text": text, "stop_reason": response.get("stop_reason"), "usage": usage}
        if self.log is not None:
            self.log({"model": self.model, "step": obs["step"], "policy": obs["policy"], "episode": obs["episode"],
                      "text": text, "thinking": thinking, "usage": usage, "parse": parse})
        return ModelReply(decision, usage, text, parse)
