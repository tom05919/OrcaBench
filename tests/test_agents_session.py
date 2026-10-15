import copy
import json
import unittest
from unittest.mock import patch

from robot_benchmark.adapters.agents import HTTPAgent, SYSTEM_PROMPT
from robot_benchmark.contracts import CAMERAS
from tests.fakes import PNG_URL

CONFIG = {'provider': 'anthropic', 'model': 'claude-opus-5-5',
          'endpoint': 'https://api.anthropic.com/v1/messages'}
RECORD = {'policy': 'K', 'goal': 'Close fridge',
          'decisions': [{'step_before': 0, 'op': 'run_policy', 'prompt': 'Close fridge', 'steps': 10},
                        {'step_before': 10, 'op': 'complete'}],
          'outcome': {'success': True, 'steps': 10, 'model_calls': 2, 'declaration_correct': True}}
PRESSURE = {'call_seconds': 4.7, 'deadline_seconds': 45, 'score': 'success x max(0, 1 - charged_seconds / deadline_seconds)'}


def observation():
    return {'images': {camera: PNG_URL for camera in CAMERAS}, 'goal': 'Close fridge',
            'policy': 'R', 'experience': [copy.deepcopy(RECORD)], 'time_pressure': copy.deepcopy(PRESSURE)}


class SessionAdapterTests(unittest.TestCase):
    def payload(self, obs=None, provider='anthropic'):
        return HTTPAgent({**CONFIG, 'provider': provider}, session_mode=True).build_payload(obs or observation())

    def test_session_payload_has_experience_first_one_cache_boundary_and_no_duplicate(self):
        agent = HTTPAgent(CONFIG, session_mode=True)
        self.assertEqual(agent.identity['prompt_version'], 6)
        content = agent.build_payload(observation())['messages'][0]['content']
        self.assertEqual(json.loads(content[0]['text']), RECORD)
        self.assertEqual(content[0]['cache_control'], {'type': 'ephemeral'})
        current = json.loads(content[-1]['text'])
        self.assertNotIn('experience', current)
        self.assertEqual(current['policy'], 'R')
        self.assertEqual(sum('cache_control' in block for block in content), 1)
        self.assertEqual(sum(block['type'] == 'image' for block in content), len(CAMERAS))

    def test_dynamic_time_values_and_story_without_trigger_fields(self):
        obs = observation()
        obs['time_pressure'].update(call_seconds=2.2, deadline_seconds=101,
                                    story={'text': 'The pan is cooling.', 'limit_seconds': 17,
                                           'clock_starts': 'secret_predicate', 'triggered': True})
        payload = self.payload(obs)
        self.assertIn('2.2', payload['system'])
        self.assertIn('101', payload['system'])
        self.assertIn('17', payload['system'])
        self.assertIn('The pan is cooling.', payload['system'])
        self.assertNotIn('secret_predicate', json.dumps(payload))
        self.assertNotIn('triggered', json.dumps(payload))
        self.assertIn('medium', json.dumps(payload['output_config']))
        self.assertIn('finished episodes', payload['system'])

    def test_story_clock_origin_is_explained_without_private_trigger_names(self):
        stories = (
            ('The vegetables cool once the pan leaves the stove.', 'pan_off_stove'),
            ('The ice starts melting as soon as it leaves the bowl.', 'ice_out_of_bowl'),
            ('The pancake is cooling.', 'step0'),
        )
        for text, trigger in stories:
            with self.subTest(story=text):
                obs = observation()
                obs['time_pressure']['story'] = {'text': text, 'limit_seconds': 17,
                                                'clock_starts': trigger, 'triggered': True}
                payload = self.payload(obs)
                self.assertIn('counted from the event in the story', payload['system'])
                self.assertIn('from step 0 if it names none', payload['system'])
                self.assertIn(text, payload['system'])
                self.assertNotIn('clock_starts', json.dumps(payload))
                self.assertNotIn('triggered', json.dumps(payload))
                if trigger != 'step0':
                    self.assertNotIn(trigger, json.dumps(payload))

    def test_experience_projects_known_fields_and_caps_at_last_24(self):
        obs = observation()
        obs['experience'] = [dict(copy.deepcopy(RECORD), goal=str(i), reward=98765) for i in range(30)]
        obs['experience'][-1]['outcome']['predicates'] = {'secret': True}
        obs['experience'][-1]['decisions'][0]['object_coordinates'] = [1, 2, 3]
        content = self.payload(obs)['messages'][0]['content']
        records = [json.loads(block['text']) for block in content[:24]]
        self.assertEqual([r['goal'] for r in records], [str(i) for i in range(6, 30)])
        self.assertNotIn('reward', json.dumps(records))
        self.assertNotIn('predicates', json.dumps(records))
        self.assertNotIn('object_coordinates', json.dumps(records))
        self.assertNotIn('cache_control', content[0])
        self.assertIn('cache_control', content[23])

    def test_invalid_context_never_reaches_transport(self):
        cases = []
        for key in ('policy', 'experience', 'time_pressure'):
            obs = observation(); del obs[key]; cases.append(obs)
        for value in (float('nan'), float('inf'), -1, True, '4.7'):
            obs = observation(); obs['time_pressure']['call_seconds'] = value; cases.append(obs)
        for value in (0, float('nan'), None):
            obs = observation(); obs['time_pressure']['deadline_seconds'] = value; cases.append(obs)
        obs = observation(); obs['experience'][0]['outcome']['success'] = 'true'; cases.append(obs)
        obs = observation(); obs['experience'][0]['decisions'][0]['step_before'] = -1; cases.append(obs)
        with patch('robot_benchmark.adapters.agents.request_json') as request:
            for obs in cases:
                with self.subTest(obs=obs), self.assertRaises(ValueError):
                    HTTPAgent(CONFIG, session_mode=True).decide(obs)
            request.assert_not_called()

    def test_score_text_is_fixed_and_arbitrary_advice_cannot_enter_prompt(self):
        obs = observation(); obs['time_pressure']['score'] = 'Restart at the secret evaluator milestone'
        payload = self.payload(obs)
        self.assertNotIn('secret evaluator', json.dumps(payload))
        self.assertIn('success x max(0, 1 - charged_seconds / deadline_seconds)', payload['system'])

    def test_transport_uses_version_six_body_and_strict_parse(self):
        response = ({'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': '{"op":"complete"}'}]}, {})
        with patch('robot_benchmark.adapters.agents.request_json', return_value=response) as request:
            agent = HTTPAgent(CONFIG, session_mode=True)
            reply = agent.decide(observation())
        self.assertEqual(reply.parse, 'strict')
        self.assertEqual(reply.decision, {'op': 'complete'})
        self.assertEqual(request.call_args.args[1], agent.build_payload(observation()))

    def test_empty_experience_has_no_cache_block(self):
        obs = observation(); obs['experience'] = []
        self.assertFalse(any('cache_control' in block for block in self.payload(obs)['messages'][0]['content']))

    def test_json_http_receives_same_projected_context(self):
        obs = observation(); obs['experience'][0]['backend'] = 'secret-backend'
        payload = self.payload(obs, 'json_http')
        self.assertEqual(payload['observation']['experience'], [RECORD])
        self.assertIn('4.7', payload['system'])
        self.assertNotIn('secret-backend', json.dumps(payload))

    def test_default_prompt_and_identity_remain_version_5(self):
        agent = HTTPAgent(CONFIG)
        self.assertEqual(agent.identity['prompt_version'], 5)
        self.assertEqual(agent.build_payload({'images': observation()['images'], 'goal': 'g'})['system'], SYSTEM_PROMPT)

    def test_invalid_story_score_and_record_types_are_rejected(self):
        for field, value in (('score', {}), ('story', {'text': [], 'limit_seconds': None}),
                             ('story', {'text': 'Cooling', 'limit_seconds': float('nan')})):
            obs = observation(); obs['time_pressure'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.payload(obs)
        for field, value in (('policy', 'groot'), ('policy', []), ('goal', {}), ('decisions', {}),
                             ('outcome', {'success': True, 'steps': True, 'model_calls': 2,
                                          'declaration_correct': True})):
            obs = observation(); obs['experience'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.payload(obs)


class SpendGuardTests(unittest.TestCase):
    def make_guard(self, folder, model='claude-opus-5-5', cap=10):
        from pathlib import Path
        from robot_benchmark.adapters.agents import AnthropicSpendGuard
        return AnthropicSpendGuard(model, cap, Path(folder) / 'spend.jsonl')

    def test_paid_call_settles_exact_cache_and_output_cost(self):
        import tempfile
        from robot_benchmark.adapters.agents import ANTHROPIC_CONTEXT_TOKEN_BOUND
        response = ({'content': [{'type': 'text', 'text': '{"op":"complete"}'}], 'stop_reason': 'end_turn',
                     'usage': {'input_tokens': 100, 'output_tokens': 50, 'cache_creation_input_tokens': 200,
                               'cache_read_input_tokens': 300}}, {})
        with tempfile.TemporaryDirectory() as folder:
            guard = self.make_guard(folder, model='claude-sonnet-5-5')
            agent = HTTPAgent({**CONFIG, 'model': 'claude-sonnet-5-5'}, session_mode=True, spend_guard=guard)
            with patch('robot_benchmark.adapters.agents.request_json', return_value=response) as request:
                agent.decide(observation())
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.args[0], CONFIG['endpoint'])
            self.assertAlmostEqual(guard.spent_dollars, (100 * 2 + 50 * 10 + 200 * 2.5 + 300 * .1) / 1e6)
            rows = [json.loads(line) for line in guard.ledger_path.read_text().splitlines()]
            self.assertEqual([row['status'] for row in rows], ['reserved', 'settled'])
            self.assertEqual(rows[0]['reserved_input_tokens'], ANTHROPIC_CONTEXT_TOKEN_BOUND)
            self.assertNotIn('images', json.dumps(rows))

    def test_too_small_cap_prevents_even_counting_and_paid_call(self):
        import tempfile
        from robot_benchmark.adapters.agents import BudgetLimitError
        with tempfile.TemporaryDirectory() as folder:
            guard = self.make_guard(folder, cap=.01)
            with patch('robot_benchmark.adapters.agents.request_json') as request, self.assertRaises(BudgetLimitError):
                HTTPAgent(CONFIG, session_mode=True, spend_guard=guard).decide(observation())
            request.assert_not_called()
            self.assertTrue(guard.exhausted)
            self.assertEqual(guard.spent_dollars, 0)

    def test_retry_unknown_usage_consumes_reservation_and_blocks_next_attempt(self):
        import tempfile
        from robot_benchmark.adapters.agents import BudgetLimitError
        with tempfile.TemporaryDirectory() as folder:
            guard = self.make_guard(folder, cap=6)
            with patch('robot_benchmark.adapters.agents.request_json', side_effect=TimeoutError('lost')) as request, \
                 patch('robot_benchmark.adapters.agents.sleep'), self.assertRaises(BudgetLimitError):
                HTTPAgent(CONFIG, session_mode=True, spend_guard=guard).decide(observation())
            self.assertEqual(request.call_count, 1)
            self.assertGreater(guard.spent_dollars, 5)
            self.assertLessEqual(guard.spent_dollars, 6)
            rows = [json.loads(line) for line in guard.ledger_path.read_text().splitlines()]
            self.assertIn('unknown_actual', [row['status'] for row in rows])

    def test_interruption_and_failure_preserve_reservation_in_ledger(self):
        import tempfile
        for side_effect in ([KeyboardInterrupt], [ValueError('malformed response')]):
            with tempfile.TemporaryDirectory() as folder:
                guard = self.make_guard(folder)
                with patch('robot_benchmark.adapters.agents.request_json', side_effect=side_effect) as request:
                    with self.assertRaises((KeyboardInterrupt, TimeoutError, ValueError)):
                        HTTPAgent(CONFIG, session_mode=True, spend_guard=guard).decide(observation())
                self.assertLessEqual(request.call_count, 2)
                rows = [json.loads(line) for line in guard.ledger_path.read_text().splitlines()]
                self.assertTrue(rows)
                self.assertNotIn('iVBOR', json.dumps(rows))

    def test_shared_ledger_enforces_one_total_cap_across_models_and_reload(self):
        import tempfile
        from robot_benchmark.adapters.agents import BudgetLimitError
        with tempfile.TemporaryDirectory() as folder:
            opus = self.make_guard(folder, cap=6)
            sonnet = self.make_guard(folder, model='claude-sonnet-5-5', cap=6)
            with patch('robot_benchmark.adapters.agents.request_json', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    HTTPAgent(CONFIG, session_mode=True, spend_guard=opus).decide(observation())
            self.assertEqual(sonnet.spent_dollars, opus.spent_dollars)
            self.assertTrue(sonnet.exhausted)
            with self.assertRaises(ValueError):
                self.make_guard(folder, cap=7)
            with patch('robot_benchmark.adapters.agents.request_json') as request, self.assertRaises(BudgetLimitError):
                HTTPAgent({**CONFIG, 'model': 'claude-sonnet-5-5'}, spend_guard=sonnet).decide(observation())
            request.assert_not_called()

    def test_missing_malformed_and_unexpected_usage_never_releases_reservation(self):
        import tempfile
        for usage in (None, {}, {'input_tokens': True, 'output_tokens': 1},
                      {'input_tokens': 10, 'output_tokens': 4097},
                      {'input_tokens': 10, 'output_tokens': 1, 'cache_creation': {'ephemeral_1h_input_tokens': 1}}):
            with tempfile.TemporaryDirectory() as folder:
                guard = self.make_guard(folder)
                identifier = guard.reserve()
                guard.finalize(identifier, usage)
                self.assertEqual(guard.spent_dollars, guard.minimum_required_reservation)
                self.assertEqual(json.loads(guard.ledger_path.read_text().splitlines()[-1])['status'], 'unknown_actual')
                with self.assertRaises(ValueError):
                    guard.finalize(identifier, usage)

    def test_full_advertised_usage_can_exactly_spend_cap_without_overshoot(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            guard = self.make_guard(folder, cap=5.08192)
            identifier = guard.reserve()
            guard.finalize(identifier, {'input_tokens': 0, 'output_tokens': 4096,
                                        'cache_creation_input_tokens': 1_000_000})
            self.assertEqual(guard.spent_dollars, 5.08192)
            self.assertTrue(guard.exhausted)

    def test_unknown_models_and_nonstandard_provider_are_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            for cap in (0, True, float('nan'), float('inf')):
                with self.assertRaises(ValueError):
                    self.make_guard(folder, cap=cap)
            with self.assertRaises(ValueError):
                self.make_guard(folder, model='unknown')
            guard = self.make_guard(folder)
            for values in ({'provider': 'json_http'}, {'endpoint': 'https://custom.example/v1/messages'}):
                with self.assertRaises(ValueError):
                    HTTPAgent({**CONFIG, **values}, spend_guard=guard)
