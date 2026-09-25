import unittest

from robot_benchmark.adapters.agents import HTTPAgent, MAX_MODEL_TOKENS


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


if __name__ == "__main__":
    unittest.main()
