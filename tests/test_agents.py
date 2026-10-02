import unittest
from unittest.mock import patch

from robot_benchmark.adapters.agents import DECISION_FORMAT, HTTPAgent, MAX_MODEL_TOKENS
from robot_benchmark.contracts import CAMERAS, PROPRIO, Limits, validate_decision
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
        self.assertEqual(payload["output_config"], {"effort": "medium", "format": DECISION_FORMAT})
        self.assertEqual(agent.identity["output_config"], payload["output_config"])
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


class DecisionTextParsingTests(unittest.TestCase):
    """A reply that narrates before its JSON must not cost a decision; ambiguity still must."""

    LIMITS = Limits(max_steps=100, max_decisions=10, max_interval=100)

    def reply_to(self, text, stop_reason="end_turn"):
        config = {"provider": "anthropic", "model": "claude-sonnet-5-5",
                  "endpoint": "https://api.anthropic.com/v1/messages",
                  "api_key_env": "ANTHROPIC_API_KEY"}
        response = {"id": "msg-test", "stop_reason": stop_reason,
                    "content": [{"type": "thinking", "thinking": "summary", "signature": "sig"},
                                {"type": "text", "text": text}],
                    "usage": {"input_tokens": 1, "output_tokens": 1}}
        observation = {"images": {camera: PNG_URL for camera in CAMERAS}, "goal": "g"}
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "secret-test-key"}), \
             patch("robot_benchmark.adapters.agents.request_json",
                   return_value=(response, {"status": 200, "headers": {}})):
            return HTTPAgent(config).decide(observation)

    def test_clean_json_is_parsed_strictly(self):
        reply = self.reply_to('{"op":"run_policy","steps":5}')
        self.assertEqual(reply.decision, {"op": "run_policy", "steps": 5})
        self.assertEqual(reply.parse, "strict")

    def test_reasoning_before_the_json_object_is_recovered(self):
        text = ('The cabinet door is still ajar in the left view, so I will keep going.\n\n'
                '{"op":"run_policy","prompt":"Close the cabinet.","steps":20}')
        reply = self.reply_to(text)
        self.assertEqual(validate_decision(reply.decision, self.LIMITS),
                         {"op": "run_policy", "prompt": "Close the cabinet.", "steps": 20})
        self.assertEqual(reply.parse, "extracted")
        self.assertEqual(reply.raw_text, text)  # the narration stays on record

    def test_code_fence_and_trailing_text_are_recovered(self):
        reply = self.reply_to('```json\n{"op":"complete"}\n```\nBoth objects look placed.')
        self.assertEqual(reply.decision, {"op": "complete"})
        self.assertEqual(reply.parse, "extracted")

    def test_braces_inside_a_prompt_string_do_not_confuse_extraction(self):
        text = 'Plan: {not json} then\n{"op":"run_policy","prompt":"close {cabinet} door","steps":3}'
        self.assertEqual(self.reply_to(text).decision,
                         {"op": "run_policy", "prompt": "close {cabinet} door", "steps": 3})

    def test_repeating_the_same_decision_is_not_ambiguous(self):
        text = '{"op":"complete"}\nTo repeat: {"op":"complete"}'
        self.assertEqual(self.reply_to(text).decision, {"op": "complete"})

    def test_conflicting_decisions_are_rejected_not_guessed(self):
        # Executing the wrong one could end the episode with a false completion.
        text = ('I could declare {"op":"complete"} but the cabinet is open, so instead '
                '{"op":"run_policy","steps":10}')
        reply = self.reply_to(text)
        self.assertEqual(reply.parse, "unparsed")
        self.assertEqual(reply.decision, text)
        with self.assertRaises(ValueError):
            validate_decision(reply.decision, self.LIMITS)

    def test_prose_without_a_decision_object_is_rejected(self):
        for text in ("I need to look closer before acting.",
                     'Maybe {"steps": 3} would help.',   # an object, but not a decision
                     ""):
            reply = self.reply_to(text)
            self.assertEqual((reply.decision, reply.parse), (text, "unparsed"))
            with self.assertRaises(ValueError):
                validate_decision(reply.decision, self.LIMITS)

    def test_truncated_or_refused_output_is_never_recovered_from_prose(self):
        text = 'Thinking aloud {"op":"complete"} and then I was cut o'
        for stop_reason in ("max_tokens", "refusal"):
            reply = self.reply_to(text, stop_reason)
            self.assertEqual((reply.decision, reply.parse), (text, "unparsed"))

    def test_pathological_nesting_is_a_rejected_reply_not_a_crash(self):
        text = '{"a":' * 5000  # json raises RecursionError, which would abort the episode
        reply = self.reply_to(text)
        self.assertEqual((reply.decision, reply.parse), (text, "unparsed"))

    def test_recovered_fields_still_face_full_validation(self):
        reply = self.reply_to('Going far.\n{"op":"run_policy","steps":9999}')
        self.assertEqual(reply.parse, "extracted")
        with self.assertRaisesRegex(ValueError, "steps"):
            validate_decision(reply.decision, self.LIMITS)

    def test_decision_schema_constrains_shape_but_leaves_range_checks_to_the_harness(self):
        schema = DECISION_FORMAT["schema"]
        self.assertEqual(DECISION_FORMAT["type"], "json_schema")
        self.assertEqual(schema["type"], "object")
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(schema["required"], ["op"])
        self.assertEqual(set(schema["properties"]), {"op", "prompt", "steps"})
        self.assertEqual(schema["properties"]["op"]["enum"], ["run_policy", "complete"])

        def keys(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    yield key
                    yield from keys(value)
            elif isinstance(node, list):
                for value in node:
                    yield from keys(value)

        self.assertFalse({"minimum", "maximum", "minLength", "maxLength", "multipleOf",
                          "anyOf", "oneOf"} & set(keys(schema)))


if __name__ == "__main__":
    unittest.main()
