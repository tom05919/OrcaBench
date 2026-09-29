import unittest
from unittest.mock import patch

from robot_benchmark.adapters.agents import HTTPAgent, MAX_MODEL_TOKENS
from robot_benchmark.contracts import CAMERAS, PROPRIO
from tests.fakes import PNG_URL


class AgentConfigurationTests(unittest.TestCase):
    def test_output_token_limit_is_fixed_across_models(self):
        base = {
            "provider": "json_http",
            "model": "provider/model-version",
            "endpoint": "http://127.0.0.1:9000/decide",
        }
        self.assertEqual(HTTPAgent(base).config.get("max_tokens", MAX_MODEL_TOKENS), MAX_MODEL_TOKENS)
        with self.assertRaisesRegex(ValueError, "fixed"):
            HTTPAgent({**base, "max_tokens": MAX_MODEL_TOKENS + 1})

    def test_model_identifier_cannot_remain_a_placeholder(self):
        with self.assertRaisesRegex(ValueError, "explicit pinned"):
            HTTPAgent({
                "provider": "json_http",
                "model": "REPLACE_WITH_PINNED_MODEL_ID",
                "endpoint": "http://127.0.0.1:9000/decide",
            })

    def test_unknown_or_unapplied_settings_are_rejected(self):
        base = {
            "provider": "json_http",
            "model": "provider/model-version",
            "endpoint": "http://127.0.0.1:9000/decide",
        }
        with self.assertRaisesRegex(ValueError, "unexpected"):
            HTTPAgent({**base, "temperature": 0})
        with self.assertRaisesRegex(ValueError, "HTTP"):
            HTTPAgent({**base, "endpoint": "file:///tmp/response.json"})

    def test_anthropic_request_records_all_api_visible_blocks_without_key(self):
        config = {"provider": "anthropic", "model": "claude-opus-5-5",
                  "endpoint": "https://api.anthropic.com/v1/messages",
                  "api_key_env": "ANTHROPIC_API_KEY", "max_tokens": MAX_MODEL_TOKENS}
        response = {"id": "msg-test", "model": "claude-opus-5-5", "stop_reason": "end_turn",
                    "content": [{"type": "thinking", "thinking": "Check cabinet progress.",
                                 "signature": "opaque-signature"},
                                {"type": "text", "text": '{"op":"run_policy","steps":5}'}],
                    "usage": {"input_tokens": 100, "output_tokens": 30,
                              "output_tokens_details": {"thinking_tokens": 20}}}
        observation = {"images": {camera: PNG_URL for camera in CAMERAS},
                       "proprio": {key: [0.0] * dim for key, dim in PROPRIO.items()},
                       "goal": "Move the cereal and bowl."}
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "secret-test-key"}), \
             patch("robot_benchmark.adapters.agents.request_json",
                   return_value=(response, {"status": 200, "headers": {"request-id": "req-test"}})) as request:
            agent = HTTPAgent(config)
            reply = agent.decide(observation)
        payload = request.call_args.args[1]
        self.assertEqual(payload["thinking"], {"type": "adaptive", "display": "summarized"})
        self.assertEqual(payload["output_config"], {"effort": "medium"})
        self.assertEqual(payload["max_tokens"], MAX_MODEL_TOKENS)
        self.assertEqual([block["text"] for block in payload["messages"][0]["content"]
                          if block["type"] == "text"][:3], list(CAMERAS))
        self.assertEqual(len([block for block in payload["messages"][0]["content"]
                              if block["type"] == "image"]), 3)
        self.assertEqual(reply.decision, {"op": "run_policy", "steps": 5})
        self.assertEqual(agent.last_trace["response"]["body"], response)
        self.assertNotIn("secret-test-key", repr(agent.last_trace))

    def test_anthropic_transport_error_retains_attempted_request(self):
        config = {"provider": "anthropic", "model": "claude-opus-5-5",
                  "endpoint": "https://api.anthropic.com/v1/messages",
                  "api_key_env": "ANTHROPIC_API_KEY"}
        observation = {"images": {camera: PNG_URL for camera in CAMERAS}, "goal": "Cereal"}
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "secret-test-key"}), \
             patch("robot_benchmark.adapters.agents.request_json", side_effect=TimeoutError("timed out")):
            agent = HTTPAgent(config)
            with self.assertRaises(TimeoutError):
                agent.decide(observation)
        self.assertIn("request", agent.last_trace)
        self.assertEqual(agent.last_trace["error"]["type"], "TimeoutError")
        self.assertNotIn("secret-test-key", repr(agent.last_trace))


if __name__ == "__main__":
    unittest.main()
