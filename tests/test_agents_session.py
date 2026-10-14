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
