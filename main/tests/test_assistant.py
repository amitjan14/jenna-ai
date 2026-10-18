import json
import unittest
from unittest.mock import patch
from main.src.agent.assistant_service import plan_request, run_assistant

SERVERS = {'jira': {'label': 'Jira', 'context': {'project_key': 'SPD'}},
           'openai': {'context': {'purpose': 'Official OpenAI documentation'}}}


class Model:
    def __init__(self, plan): self.plan = plan
    def chat(self, **kwargs): return {'message': {'content': json.dumps(self.plan)}}


def planned(question='Give an overview of SPD-2631.', connection='jira', mode='Auto', clarification=''):
    return {'connection': connection, 'mode': mode, 'question': question, 'clarification': clarification,
            'intent':'task', 'memory_key':'', 'memory_value':'',
            'state':{'goal':'','constraints':[],'references':[]}}


class AssistantTests(unittest.TestCase):
    def test_typo_interpretation_preserves_issue_and_numeric_anchors(self):
        plan = plan_request('histroy of SPD-2631', servers=SERVERS,
                            model_client=Model(planned('Show the history of SPD-2631.')))
        self.assertIn('history', plan['question'])
        changed = plan_request('history of SPD-2631', servers=SERVERS,
                               model_client=Model(planned('History of SPD-2632.')))
        self.assertEqual(changed['question'], 'history of SPD-2631')

    def test_interpretation_cannot_invent_a_ticket_identifier(self):
        result = plan_request('look up the ticket', servers=SERVERS,
                              model_client=Model(planned('Look up SPD-999.')))
        self.assertEqual(result['question'], 'look up the ticket')

    def test_clarification_takes_precedence_over_stray_interpreted_question(self):
        result = plan_request('search Jira about a ticket', servers=SERVERS,
            model_client=Model(planned('Search Jira', clarification='Which ticket or topic do you mean?')))
        self.assertEqual(result['question'], '')
        self.assertTrue(result['clarification'])

    def test_nested_metrics_include_interpretation_and_backend(self):
        from main.src.utils.telemetry import instrument_request, record_call
        @instrument_request
        def inner():
            record_call('chat', .02)
            return {'status': 'answered'}
        @instrument_request
        def outer():
            record_call('chat', .01)
            return inner()
        self.assertEqual(outer()['metrics']['llm_calls'], 2)

    def test_unknown_connection_or_invented_plan_shape_rejected(self):
        from jsonschema import ValidationError
        with self.assertRaises(ValidationError):
            plan_request('hello', servers=SERVERS, model_client=Model(planned(connection='unregistered')))

    def test_ambiguous_subject_returns_focused_clarification_without_read(self):
        with patch('main.src.agent.assistant_service.load_servers', return_value=SERVERS), \
             patch('main.src.agent.assistant_service.run_mcp_question') as remote:
            result = run_assistant('look up that ticket', model_client=Model(planned('', clarification='Which ticket do you mean?')))
        self.assertEqual(result['status'], 'needs_clarification')
        remote.assert_not_called()

    def test_automatic_dispatch_uses_jira_without_mode_selection(self):
        with patch('main.src.agent.assistant_service.load_servers', return_value=SERVERS), \
             patch('main.src.agent.assistant_service.run_mcp_question', return_value={'answer': 'Working', 'status': 'answered'}) as remote:
            result = run_assistant('whats up with SPD-2631', model_client=Model(planned()))
        self.assertEqual(result['connection'], 'jira')
        remote.assert_called_once_with('Give an overview of SPD-2631.', 'jira', history=None)

    def test_explicit_documents_and_private_scope_prevent_remote_dispatch(self):
        for kwargs, question in [({'mode': 'Documents'}, 'history of SPD-2631'),
                                 ({}, 'from my PDF what is Jira?'),
                                 ({'filters': {'filename': 'a.pdf'}}, 'ticket overview')]:
            with self.subTest(question=question), \
                 patch('main.src.agent.assistant_service.load_servers', return_value=SERVERS), \
                 patch('main.src.agent.assistant_service.run_mcp_question') as remote, \
                 patch('main.src.agent.assistant_service.run_agent', return_value={'answer': 'Quoted', 'status': 'passages_verified'}) as local:
                result = run_assistant(question, model_client=Model(planned(question)), **kwargs)
            remote.assert_not_called()
            self.assertEqual(result['connection'], 'local')
            self.assertEqual(local.call_args.kwargs['search_mode'], 'Documents')

    def test_explicit_connection_override_and_followup_metadata(self):
        history = [{'role': 'assistant', 'content': 'SPD-2631 is in progress', 'connection': 'jira'}]
        with patch('main.src.agent.assistant_service.load_servers', return_value=SERVERS), \
             patch('main.src.agent.assistant_service.run_mcp_question', return_value={'answer': 'History', 'status': 'answered'}) as remote:
            result = run_assistant('what changed?', connection='jira', history=history,
                                   model_client=Model(planned('Show SPD-2631 history.', connection='local')))
        self.assertEqual(result['connection'], 'jira')
        self.assertEqual(remote.call_args.kwargs['history'], history)

    def test_arithmetic_bypasses_intent_model(self):
        model = Model({})
        with patch('main.src.agent.assistant_service.load_servers', return_value=SERVERS), \
             patch.object(model, 'chat') as chat:
            result = run_assistant('calculate 6 * 7', model_client=model)
        self.assertIn('42', result['answer'])
        chat.assert_not_called()


if __name__ == '__main__': unittest.main()
