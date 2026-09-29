"""Model adapters receive public observations only and expose no filesystem tools."""
import json
import os
from urllib.parse import urlparse

from ..contracts import CAMERAS, ModelReply
from .http import request_json

MAX_MODEL_TOKENS = 4096

SYSTEM_PROMPT = """You supervise a robot controlled by a language-conditioned learned policy.
Interpret the household goal, write natural-language instructions to the policy,
and monitor the resulting motion. You may change or repeat an instruction at any
decision boundary. Reference prompts and performance cards are examples, not an
allowed-command list. The policy may fail or ignore an instruction.
Physics pauses while you reason. You see current RGB views, proprioception,
the active instruction, and decision history. You do not receive task-success
labels. Judge progress from observations.
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


class HTTPAgent:
    def __init__(self, config):
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
        self.config = dict(config)
        self.identity = {key: value for key, value in config.items() if key != "api_key_env"}
        self.identity["prompt_version"] = 2
        if config["provider"] == "anthropic":
            self.identity["thinking"] = {"type": "adaptive", "display": "summarized"}
            self.identity["output_config"] = {"effort": "medium"}
        self.last_trace = None
        key_name = config.get("api_key_env")
        self.key = os.environ.get(key_name) if key_name else None
        if key_name and not self.key:
            raise ValueError(f"missing credential environment variable: {key_name}")

    def decide(self, observation):
        config = self.config
        if config["provider"] == "json_http":
            headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
            payload = {
                "model": config["model"], "system": SYSTEM_PROMPT,
                "max_tokens": MAX_MODEL_TOKENS, "observation": observation,
            }
            response = self._request(payload, headers, {"Content-Type": "application/json"})
            return ModelReply(response.get("decision"), response.get("usage"), response.get("raw_text"))
        content = []
        for camera in CAMERAS:
            content.extend([
                {"type": "text", "text": camera},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                    "data": observation["images"][camera].split(",", 1)[1]}},
            ])
        content.append({"type": "text", "text": json.dumps({k: v for k, v in observation.items() if k != "images"})})
        payload = {
            "model": config["model"], "max_tokens": MAX_MODEL_TOKENS,
            "system": SYSTEM_PROMPT, "messages": [{"role": "user", "content": content}],
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": "medium"},
        }
        response = self._request(payload,
            {"x-api-key": self.key, "anthropic-version": "2023-06-01"},
            {"Content-Type": "application/json", "anthropic-version": "2023-06-01"})
        raw = "".join(block["text"] for block in response["content"] if block["type"] == "text")
        try:
            decision = json.loads(raw)
        except json.JSONDecodeError:
            decision = raw  # charged as malformed output; no free repair request
        usage = response.get("usage")
        return ModelReply(decision, usage, raw)

    def _request(self, payload, headers, safe_headers):
        self.last_trace = {"request": {"url": self.config["endpoint"],
                         "headers": safe_headers, "body": payload}}
        try:
            response, metadata = request_json(self.config["endpoint"], payload, headers,
                self.config.get("timeout_seconds", 120), with_metadata=True)
        except Exception as error:
            self.last_trace["error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        self.last_trace["response"] = {"http": metadata, "body": response}
        return response
