"""Model adapters receive public observations only and expose no filesystem tools."""
import copy
import json
import math
import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from time import sleep
from urllib.error import URLError
from urllib.parse import urlparse

from ..contracts import CAMERAS, MAX_POLICY_PROMPT_CHARS, ModelReply
from .http import HTTPStatusError, request_json

MAX_MODEL_TOKENS = 4096

# A model call changes no simulator or policy state (physics is paused), so a
# transient provider failure is retried instead of ending the episode as an
# infrastructure error. Retries are not decisions and are never shown to the model.
RETRY_DELAYS_SECONDS = (5, 20, 60)
MAX_RETRY_AFTER_SECONDS = 120
RETRYABLE_HTTP_STATUS = frozenset({408, 429, 500, 502, 503, 504, 529})


def is_transient(error):
    if isinstance(error, HTTPStatusError):
        return error.status in RETRYABLE_HTTP_STATUS
    return isinstance(error, (TimeoutError, ConnectionError, URLError))

# Constrains the reply text to a single JSON object, so a model cannot narrate
# inside it. Kept flat: the API documents no root-level anyOf and ignores numeric
# and length limits, so validate_decision stays the authority on the per-operation
# fields, ranges, and prompt length.
DECISION_FORMAT = {"type": "json_schema", "schema": {
    "type": "object",
    "properties": {
        "op": {"type": "string", "enum": ["run_policy", "complete"]},
        "prompt": {"type": "string"},
        "steps": {"type": "integer"},
    },
    "required": ["op"],
    "additionalProperties": False,
}}


def parse_decision_text(text, stop_reason):
    """Return (decision, parse_mode) for a model's reply text.

    Whole-text JSON is "strict". Otherwise, if the model finished normally and its
    text holds exactly one distinct decision-shaped object, that object is
    "extracted". Conflicting objects are never resolved by guessing: executing the
    wrong one could end an episode with a false completion. Truncated or refused
    replies never yield an extracted decision. Anything else is handed on as
    "unparsed" text to be rejected and charged.
    """
    try:
        return json.loads(text), "strict"
    except (json.JSONDecodeError, RecursionError):  # degenerate nesting is just unparseable
        pass
    if stop_reason == "end_turn":
        found, decoder, index = [], json.JSONDecoder(), text.find("{")
        while index != -1:
            try:
                value, end = decoder.raw_decode(text, index)
            except (json.JSONDecodeError, RecursionError):
                index = text.find("{", index + 1)
                continue
            if isinstance(value, dict) and isinstance(value.get("op"), str) and value not in found:
                found.append(value)
            index = text.find("{", end)
        if len(found) == 1:
            return found[0], "extracted"
    return text, "unparsed"


SYSTEM_PROMPT = """You supervise a robot controlled by a language-conditioned learned policy.
Interpret the household goal, write natural-language instructions to the policy,
and monitor the resulting motion. You may change or repeat an instruction at any
decision boundary. Reference prompts and performance cards are examples, not an
allowed-command list. The policy may fail or ignore an instruction.
Physics pauses while you reason. You see current RGB views, proprioception,
the active instruction, and decision history. After a run, you also see a few
keyframes sampled evenly from inside the interval just executed, labeled by
step. You do not receive task-success labels. Judge progress from observations.
Proprioception is the robot's own joint-sensor readings as lists of numbers; it
carries no object or world-state information:
state.end_effector_position_relative: end-effector (gripper) position (x, y, z)
in meters, in the robot base frame.
state.end_effector_rotation_relative: end-effector orientation as a quaternion
(x, y, z, w), in the robot base frame.
state.gripper_qpos: the two finger joint positions in meters. Each finger moves
between 0 (closed) and 0.04 (open) and the second finger reports the negative,
so fully open is about [0.04, -0.04] and fully closed is about [0, 0].
state.base_position: mobile-base position (x, y, z) in meters, in the world frame.
state.base_rotation: mobile-base orientation as a quaternion (x, y, z, w), in the
world frame.
A quaternion and its negation describe the same orientation, so signs may flip
between readings. Each keyframe also carries the proprioception recorded at its step.
Reply with exactly one JSON object and no other text, using one of:
{"op":"run_policy","prompt":"<your instruction>","steps":N}
{"op":"run_policy","steps":N}
{"op":"complete"}
N is a positive integer at most max_interval and remaining_steps. A prompt is
required for the first run and may contain at most 512 characters. Supplying a
prompt, even the same text as before, discards unexecuted policy actions and
requests new actions from the current physical state. Omitting the prompt
continues the active instruction and preserves unexecuted actions. Neither
choice resets the physical world. Choose N to decide when to observe again.
Each response consumes one decision, including invalid responses. Budget
exhaustion ends the episode. Reserve a decision and physical-step budget to
declare completion. Complete ends the episode immediately and succeeds only
if the physical goal is satisfied. No new observations arrive between decisions.
"""


SESSION_SCORE = "success x max(0, 1 - charged_seconds / deadline_seconds)"
SESSION_PROMPT_VERSION = 6
MAX_EXPERIENCE_RECORDS = 24
SESSION_POLICY_LABELS = frozenset({"K", "R", "T", "V", "W", "Z"})
SESSION_SYSTEM_PROMPT = """You supervise a robot controlled by a language-conditioned learned policy.
Several anonymous policies of different ability take turns in separate episodes.
Records of finished episodes come first. Learn from them how each policy behaves.
Choose when to monitor, whether to continue or supply an instruction, and when to
declare completion. Instructions may be ignored or fail; supplying an instruction
is not guaranteed to improve the policy. Reference prompts and performance cards
are examples, not an allowed-command list.
Physics pauses while you reason, but every response is charged on the task clock,
including the first response and invalid responses. Robot time is steps / 20 seconds.
You see current RGB views, proprioception, the active instruction, and decision
history. After a run you also see keyframes sampled evenly inside the interval,
labeled by step. You receive no current task-success labels. Only finished episodes
show outcomes. Judge current progress from observations.
""" + SYSTEM_PROMPT[SYSTEM_PROMPT.index("Proprioception is"):]


def _nonnegative_integer(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _finite_seconds(value, name, *, positive=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or (value <= 0 if positive else value < 0)):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return value


def projected_experience(records):
    """Only finished-episode public fields cross the model boundary; keep the latest 24."""
    if not isinstance(records, list):
        raise ValueError("experience must be a list")
    projected = []
    for record in records[-MAX_EXPERIENCE_RECORDS:]:
        if (not isinstance(record, dict) or not isinstance(record.get("policy"), str)
                or record["policy"] not in SESSION_POLICY_LABELS):
            raise ValueError("experience policy must be an anonymous policy label")
        if not isinstance(record.get("goal"), str) or not record["goal"].strip():
            raise ValueError("experience goal must be nonblank text")
        if not isinstance(record.get("decisions"), list):
            raise ValueError("experience decisions must be a list")
        decisions = []
        for decision in record["decisions"]:
            if not isinstance(decision, dict) or decision.get("op") not in ("run_policy", "complete"):
                raise ValueError("experience decision must have a valid operation")
            shown = {"step_before": _nonnegative_integer(decision.get("step_before"), "step_before"),
                     "op": decision["op"]}
            if shown["op"] == "run_policy":
                steps = _nonnegative_integer(decision.get("steps"), "steps")
                if not steps:
                    raise ValueError("run_policy steps must be positive")
                shown["steps"] = steps
                if "prompt" in decision:
                    prompt = decision["prompt"]
                    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_POLICY_PROMPT_CHARS:
                        raise ValueError("experience prompt must be nonblank policy instruction text")
                    shown["prompt"] = prompt
            decisions.append(shown)
        outcome = record.get("outcome")
        if not isinstance(outcome, dict) or type(outcome.get("success")) is not bool:
            raise ValueError("experience outcome success must be boolean")
        correct = outcome.get("declaration_correct")
        if correct is not None and type(correct) is not bool:
            raise ValueError("declaration_correct must be boolean or null")
        projected.append({"policy": record["policy"], "goal": record["goal"], "decisions": decisions,
                          "outcome": {"success": outcome["success"],
                                      "steps": _nonnegative_integer(outcome.get("steps"), "outcome steps"),
                                      "model_calls": _nonnegative_integer(outcome.get("model_calls"), "model_calls"),
                                      "declaration_correct": correct}})
    return projected


def public_time_pressure(value):
    """Validate and project only human-readable clock terms, never trigger state."""
    if not isinstance(value, dict):
        raise ValueError("time_pressure must be an object")
    if not isinstance(value.get("score"), str) or not value["score"].strip():
        raise ValueError("time_pressure score must be nonblank text")
    result = {"call_seconds": _finite_seconds(value.get("call_seconds"), "call_seconds"),
              "deadline_seconds": _finite_seconds(value.get("deadline_seconds"), "deadline_seconds", positive=True),
              "score": SESSION_SCORE}
    if value.get("story") is not None:
        story = value["story"]
        if not isinstance(story, dict) or not isinstance(story.get("text"), str) or not story["text"].strip():
            raise ValueError("story text must be nonblank text")
        limit = story.get("limit_seconds")
        if limit is not None:
            _finite_seconds(limit, "story limit_seconds", positive=True)
        result["story"] = {"text": story["text"], "limit_seconds": limit}
    return result


def session_system_prompt(pressure):
    """Each task and model use the frozen terms supplied by the session runner."""
    text = (SESSION_SYSTEM_PROMPT + f"\nEach response costs {pressure['call_seconds']} task-clock seconds. "
            f"The deadline is {pressure['deadline_seconds']} charged seconds from step 0. "
            f"Score: {pressure['score']}. Failures score zero; speed counts only for successful completion.\n")
    if "story" in pressure:
        story = pressure["story"]
        text += f"Story: {story['text']}\n"
        if story["limit_seconds"] is not None:
            text += (f"The story has a hard limit of {story['limit_seconds']} charged seconds, "
                     "counted from the event in the story, or from step 0 if it names none; "
                     "past it the task fails.\n")
    return text


ANTHROPIC_MESSAGES_ENDPOINT = "https://api.anthropic.com/v1/messages"
# Official model overview: both models have a 1M-token context window. Token
# counting is only an estimate and cannot tighten a strict spending bound.
# Sources: https://platform.claude.com/docs/en/models/overview
# https://platform.claude.com/docs/en/about-claude/pricing
ANTHROPIC_CONTEXT_TOKEN_BOUND = 1_000_000
TOKENS_PER_MILLION = Decimal(1_000_000)
ANTHROPIC_STANDARD_PRICES = {
    "claude-opus-5-5": {"input": Decimal("4"), "output": Decimal("20"),
                        "write_5m": Decimal("5"), "write_1h": Decimal("8"), "read": Decimal("0.20")},
    "claude-sonnet-5-5": {"input": Decimal("2"), "output": Decimal("10"),
                          "write_5m": Decimal("2.5"), "write_1h": Decimal("4"), "read": Decimal("0.10")},
}
# Post-freeze add-on: open models on Sail Research's Anthropic-compatible Messages API (beta), which accepts the same
# request (images, adaptive thinking, output_config effort and json_schema format; cache_control is accepted and
# caching is automatic). Default `asap` window, USD per 1M tokens, October 15, 2026:
# https://docs.sailresearch.com/pricing and https://docs.sailresearch.com/support. Sail never bills cache creation,
# so the write rates are the uncached input rate.
SAIL_MESSAGES_ENDPOINT = "https://api.sailresearch.com/v1/messages"
SAIL_STANDARD_PRICES = {
    model: {"input": Decimal(i), "output": Decimal(o), "write_5m": Decimal(i), "write_1h": Decimal(i), "read": Decimal(r)}
    for model, i, o, r in (("moonshotai/Kimi-K3", "2.50", "12.50", "0.25"),
                           ("google/gemma-4-31B-it", "0.40", "0.60", "0.20"),
                           ("zai-org/GLM-5.3-Flash", "0.11", "0.35", "0.02"))
}
MESSAGES_PRICES = {ANTHROPIC_MESSAGES_ENDPOINT: ANTHROPIC_STANDARD_PRICES, SAIL_MESSAGES_ENDPOINT: SAIL_STANDARD_PRICES}


class BudgetLimitError(RuntimeError):
    """The remaining authorized dollars cannot cover the next worst-case attempt."""


class AnthropicSpendGuard:
    """Strict standard-price reserve, shared by a ledger within one sequential process.

    Reserve the full advertised input context at the most expensive possible
    input rate (5-minute cache creation), plus all 4096 output tokens. Settle
    from usage only. A timeout, interruption or missing/invalid usage retains
    the entire reservation, since the server might have completed the request.
    This trades run length for an auditable cap without guessed tokenizer error
    margins. No estimate-only count_tokens call contaminates latency calibration.
    It assumes the provider honors documented context/output limits and prices.
    """
    def __init__(self, model, dollar_cap, ledger_path, endpoint=ANTHROPIC_MESSAGES_ENDPOINT):
        self.prices = self.prices_for(model, endpoint)
        _finite_seconds(dollar_cap, "API dollar cap", positive=True)
        self.model, self.cap, self.endpoint = model, Decimal(str(dollar_cap)), endpoint
        self.ledger_path = Path(ledger_path)
        self.reservation = self.reservation_for_model(model, endpoint)
        self._read_ledger()

    @staticmethod
    def prices_for(model, endpoint=ANTHROPIC_MESSAGES_ENDPOINT):
        prices = MESSAGES_PRICES.get(endpoint, {})
        if not isinstance(model, str) or model not in prices:
            raise ValueError(f"no verified standard prices for model {model!r} at {endpoint}")
        return prices[model]

    @staticmethod
    def reservation_for_model(model, endpoint=ANTHROPIC_MESSAGES_ENDPOINT):
        prices = AnthropicSpendGuard.prices_for(model, endpoint)
        return (prices["write_5m"] * ANTHROPIC_CONTEXT_TOKEN_BOUND
                + prices["output"] * MAX_MODEL_TOKENS) / TOKENS_PER_MILLION

    def _read_ledger(self):
        if not self.ledger_path.exists():
            return [], Decimal(0)
        rows = [json.loads(line) for line in self.ledger_path.read_text().splitlines() if line.strip()]
        if any(Decimal(str(row["budget_dollars"])) != self.cap for row in rows):
            raise ValueError("spend ledger already uses a different dollar cap")
        return rows, sum((Decimal(row["delta_dollars"]) for row in rows), Decimal(0))

    @property
    def minimum_required_reservation(self):
        return float(self.reservation)

    @property
    def spent_dollars(self):
        return float(self._read_ledger()[1])

    @property
    def exhausted(self):
        return self._read_ledger()[1] + self.reservation > self.cap

    def _append(self, status, *, delta=Decimal(0), **fields):
        _, spent = self._read_ledger()
        row = {"model": self.model, "status": status, "delta_dollars": str(delta),
               "spent_dollars": float(spent + delta), "budget_dollars": float(self.cap),
               "usage": None, "cost_dollars": 0.0, **fields}
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger_path.open("a") as stream:
            stream.write(json.dumps(row) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def check(self):
        if self.exhausted:
            self._append("budget_rejected", minimum_required_reservation=self.minimum_required_reservation)
            raise BudgetLimitError(f"remaining API budget cannot reserve ${self.reservation} for {self.model}; "
                                   f"spent/reserved ${self.spent_dollars:.6f} of ${self.cap}")

    def reserve(self):
        self.check()
        identifier = uuid4().hex
        self._append("reserved", delta=self.reservation, reservation_id=identifier,
                     cost_dollars=float(self.reservation), reserved_input_tokens=ANTHROPIC_CONTEXT_TOKEN_BOUND,
                     reserved_output_tokens=MAX_MODEL_TOKENS)
        return identifier

    def finalize(self, identifier, usage=None, error_type=None):
        rows, _ = self._read_ledger()
        matching = [row for row in rows if row.get("reservation_id") == identifier]
        if len(matching) != 1 or matching[0]["status"] != "reserved" or matching[0]["model"] != self.model:
            raise ValueError("spend reservation is missing or already finalized")
        shown = None
        try:
            if not isinstance(usage, dict) or not {"input_tokens", "output_tokens"} <= set(usage):
                raise ValueError("complete usage is unavailable")
            shown = {key: _nonnegative_integer(usage.get(key, 0), key) for key in
                     ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
            creation = usage.get("cache_creation") or {}
            if not isinstance(creation, dict):
                raise ValueError("invalid cache creation usage")
            one_hour = _nonnegative_integer(creation.get("ephemeral_1h_input_tokens", 0), "1h cache tokens")
            if one_hour or sum(shown[key] for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")) > ANTHROPIC_CONTEXT_TOKEN_BOUND:
                raise ValueError("usage exceeds the guarded standard 5-minute input contract")
            if shown["output_tokens"] > MAX_MODEL_TOKENS:
                raise ValueError("usage exceeds guarded output limit")
            cost = (shown["input_tokens"] * self.prices["input"] + shown["output_tokens"] * self.prices["output"]
                    + shown["cache_creation_input_tokens"] * self.prices["write_5m"]
                    + shown["cache_read_input_tokens"] * self.prices["read"]) / TOKENS_PER_MILLION
        except ValueError:
            self._append("unknown_actual", reservation_id=identifier, usage=None,
                         cost_dollars=float(self.reservation), error_type=error_type or "UnavailableUsage")
        else:
            self._append("settled", delta=cost - self.reservation, reservation_id=identifier, usage=shown,
                         cost_dollars=float(cost))


class HTTPAgent:
    def __init__(self, config, *, session_mode=False, spend_guard=None):
        allowed = {"provider", "model", "endpoint", "api_key_env", "max_tokens", "timeout_seconds"}
        if set(config) - allowed:
            raise ValueError(f"unexpected model configuration fields: {sorted(set(config) - allowed)}")
        if config.get("provider") not in ("anthropic", "json_http"):
            raise ValueError("provider must be anthropic or json_http")
        if not config.get("model") or "REPLACE" in config["model"]:
            raise ValueError("supply an explicit pinned model identifier")
        endpoint = config.get("endpoint")
        if not isinstance(endpoint, str) or urlparse(endpoint).scheme not in ("http", "https"):
            raise ValueError("endpoint must be an HTTP(S) URL")
        if config.get("max_tokens", MAX_MODEL_TOKENS) != MAX_MODEL_TOKENS:
            raise ValueError(f"max_tokens is fixed at {MAX_MODEL_TOKENS} for model comparisons")
        timeout = config.get("timeout_seconds", 120)
        if type(timeout) not in (int, float) or timeout <= 0:
            raise ValueError("timeout_seconds must be positive")
        if config.get("api_key_env") is not None and not isinstance(config["api_key_env"], str):
            raise ValueError("api_key_env must be a string or null")
        if spend_guard is not None and (config["provider"] != "anthropic" or config["endpoint"] not in MESSAGES_PRICES
                or config["endpoint"] != spend_guard.endpoint or spend_guard.model != config["model"]):
            raise ValueError("spend guard requires its matching model at its priced Messages endpoint")
        self.spend_guard = spend_guard
        self.session_mode = session_mode
        self.config = dict(config)
        self.identity = {key: value for key, value in config.items() if key != "api_key_env"}
        self.identity["prompt_version"] = SESSION_PROMPT_VERSION if session_mode else 5
        if config["provider"] == "anthropic":
            self.identity["thinking"] = {"type": "adaptive", "display": "summarized"}
            self.identity["output_config"] = self._output_config()
        self.last_trace = None
        key_name = config.get("api_key_env")
        self.key = os.environ.get(key_name) if key_name else None
        if key_name and not self.key:
            raise ValueError(f"missing credential environment variable: {key_name}")

    def build_payload(self, observation):
        """Build the exact provider body; used by the live adapter and offline probe."""
        config = self.config
        system, experience = SYSTEM_PROMPT, []
        if self.session_mode:
            if not isinstance(observation.get("policy"), str) or observation["policy"] not in SESSION_POLICY_LABELS:
                raise ValueError("session observation requires an anonymous policy label")
            if "experience" not in observation:
                raise ValueError("session observation requires experience")
            experience = projected_experience(observation["experience"])
            pressure = public_time_pressure(observation.get("time_pressure"))
            system = session_system_prompt(pressure)
            observation = {**observation, "experience": experience, "time_pressure": pressure}
        if config["provider"] == "json_http":
            return {"model": config["model"], "system": system, "max_tokens": MAX_MODEL_TOKENS,
                    "observation": observation}
        content = [{"type": "text", "text": json.dumps(record)} for record in experience]
        if content:
            content[-1]["cache_control"] = {"type": "ephemeral"}
        for camera in CAMERAS:
            content.extend([
                {"type": "text", "text": camera},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                    "data": observation["images"][camera].split(",", 1)[1]}},
            ])
        for frame in observation.get("interval_frames", []):
            if frame.get("proprio"):
                content.append({"type": "text", "text":
                                f"interval keyframe step {frame['step']} proprioception: {json.dumps(frame['proprio'])}"})
            for camera in CAMERAS:
                content.extend([
                    {"type": "text", "text": f"interval keyframe step {frame['step']}: {camera}"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                        "data": frame["images"][camera].split(",", 1)[1]}},
                ])
        content.append({"type": "text", "text": json.dumps(
            {k: v for k, v in observation.items() if k not in ("images", "interval_frames", "experience")})})
        return {
            "model": config["model"], "max_tokens": MAX_MODEL_TOKENS,
            "system": system, "messages": [{"role": "user", "content": content}],
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": self._output_config(),
        }

    def decide(self, observation):
        config = self.config
        payload = self.build_payload(observation)
        if config["provider"] == "json_http":
            headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
            response = self._request(payload, headers, {"Content-Type": "application/json"})
            return ModelReply(response.get("decision"), response.get("usage"), response.get("raw_text"))
        response = self._request(payload,
            {"x-api-key": self.key, "anthropic-version": "2023-06-01"},
            {"Content-Type": "application/json", "anthropic-version": "2023-06-01"})
        raw = "".join(block["text"] for block in response["content"] if block["type"] == "text")
        # Unrecoverable text is charged as malformed output; no free repair request.
        decision, parse = parse_decision_text(raw, response.get("stop_reason"))
        return ModelReply(decision, response.get("usage"), raw, parse)

    @staticmethod
    def _output_config():
        return {"effort": "medium", "format": copy.deepcopy(DECISION_FORMAT)}

    def _request(self, payload, headers, safe_headers):
        self.last_trace = {"request": {"url": self.config["endpoint"],
                         "headers": safe_headers, "body": payload}}
        for attempt, delay in enumerate((*RETRY_DELAYS_SECONDS, None), start=1):
            reservation = None
            try:
                if self.spend_guard is not None:
                    reservation = self.spend_guard.reserve()
                response, metadata = request_json(self.config["endpoint"], payload, headers,
                    self.config.get("timeout_seconds", 120), with_metadata=True)
                if reservation is not None:
                    self.spend_guard.finalize(reservation, response.get("usage"))
                    reservation = None
                break
            except BaseException as error:
                if reservation is not None:
                    self.spend_guard.finalize(reservation, error_type=type(error).__name__)
                failure = {"type": type(error).__name__, "message": str(error)}
                if delay is None or not is_transient(error):
                    self.last_trace["error"] = failure
                    raise
                try:
                    delay = min(max(delay, float(error.retry_after)), MAX_RETRY_AFTER_SECONDS)
                except (AttributeError, TypeError, ValueError):
                    pass
                self.last_trace.setdefault("retries", []).append({"attempt": attempt, **failure, "waited_seconds": delay})
                sleep(delay)
        self.last_trace["response"] = {"http": metadata, "body": response}
        return response
