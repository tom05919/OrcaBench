"""Model adapters receive public observations only and expose no filesystem tools."""
import json
import os
from urllib.parse import urlparse

from ..contracts import CAMERAS, ModelReply
from .http import request_json

MAX_MODEL_TOKENS = 1024

SYSTEM_PROMPT = """You supervise a robot through a fixed library of learned skills.
Interpret the household goal and choose skills, monitor their execution, interrupt,
switch, or retry as needed. Physics pauses while you reason. The skills may fail.
You see current RGB views, proprioception, and the complete decision history.
You do not receive task-success labels. Judge progress from the observations.
Reply with exactly one JSON object and no other text, using one of:
{"op":"start","skill":"<id>","steps":N}
{"op":"continue","steps":N}
{"op":"interrupt"}
{"op":"switch","skill":"<different id>","steps":N}
{"op":"retry","steps":N}
{"op":"complete"}
N is a positive integer at most max_interval and remaining_steps.
Start requires no active skill; continue, switch, and interrupt require one.
Retry restarts the last selected skill from the CURRENT physical state, including
after interruption. It does not reset the world. Switching or retrying discards
queued actions. Continue preserves queued actions. Select when to observe again
by choosing N. Each response consumes one decision, including invalid responses.
Budget exhaustion ends the episode. Reserve a decision and physical-step budget
to declare completion. Complete ends the episode immediately and succeeds only
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
        self.identity["prompt_version"] = 1
        key_name = config.get("api_key_env")
        self.key = os.environ.get(key_name) if key_name else None
        if key_name and not self.key:
            raise ValueError(f"missing credential environment variable: {key_name}")

    def decide(self, observation):
        config = self.config
        if config["provider"] == "json_http":
            headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
            response = request_json(config["endpoint"], {
                "model": config["model"], "system": SYSTEM_PROMPT,
                "max_tokens": MAX_MODEL_TOKENS, "observation": observation,
            }, headers, config.get("timeout_seconds", 120))
            return ModelReply(response.get("decision"), response.get("usage"), response.get("raw_text"))
        content = []
        for camera in CAMERAS:
            content.extend([
                {"type": "text", "text": camera},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                    "data": observation["images"][camera].split(",", 1)[1]}},
            ])
        content.append({"type": "text", "text": json.dumps({k: v for k, v in observation.items() if k != "images"})})
        response = request_json(config["endpoint"], {
            "model": config["model"], "max_tokens": MAX_MODEL_TOKENS,
            "system": SYSTEM_PROMPT, "messages": [{"role": "user", "content": content}],
        }, {"x-api-key": self.key, "anthropic-version": "2023-06-01"}, config.get("timeout_seconds", 120))
        raw = "".join(block["text"] for block in response["content"] if block["type"] == "text")
        try:
            decision = json.loads(raw)
        except json.JSONDecodeError:
            decision = raw  # charged as malformed output; no free repair request
        usage = response.get("usage")
        return ModelReply(decision, usage, raw)
