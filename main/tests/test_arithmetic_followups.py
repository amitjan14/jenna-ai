"""Conversation arithmetic must retain calculator context and avoid retrieval."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main.src.agent.assistant_service import run_assistant
from main.src.tools.calculator import resolve_arithmetic_followup, parse_explicit_arithmetic, run_calculation
from main.src.memory import memory_service
from main.src.utils.schemas import Ask


class ArithmeticFollowupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(memory_service, 'DB_PATH', Path(self.temp.name)/'memory.sqlite3'),
                        patch('main.src.agent.assistant_service.load_servers', return_value={}),
                        patch('main.src.tools.llm.Client.chat', side_effect=AssertionError('Unexpected model call')),
                        patch('main.src.agent.agent_service.search_documents', side_effect=AssertionError('Unexpected document search')),
                        patch('main.src.agent.agent_service.run_online_search', side_effect=AssertionError('Unexpected web search'))]
        self.mocks = [item.start() for item in self.patches]

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def previous(self, expression='5 + 8', value=13):
        return {'role':'assistant', 'content':'`5 + 8` = **13**', 'status':'tool_completed',
                'tools_used':['calculator'], 'calculation':{'expression':expression, 'value':value}}

    def test_exact_two_turn_conversation_returns_twenty_without_models_or_search(self):
        first = run_assistant('what is 5 + 8')
        history = [{'role':'user', 'content':'what is 5 + 8'},
                   {'role':'assistant', 'content':first['answer'], **first}]
        second = run_assistant('that plus 7', history=history)
        self.assertEqual(first['calculation']['value'], 13)
        self.assertEqual(second['calculation']['value'], 20)
        self.assertEqual(second['tools_used'], ['calculator'])
        self.assertEqual(second['metrics']['llm_calls'], 0)
        for model_or_search in self.mocks[2:]:
            model_or_search.assert_not_called()

    def test_chained_operations_use_the_latest_result_and_operand_order(self):
        history = [self.previous()]
        for question, expected in [('add 7 to that',20), ('subtract 4 from it',16),
                                   ('multiply that by 2',32), ('divide it by 4',8),
                                   ('that plus -3',5)]:
            with self.subTest(question=question):
                result = run_assistant(question, history=history)
                self.assertEqual(result['calculation']['value'], expected)
                history.append({'role':'assistant', 'content':result['answer'], **result})

    def test_previously_saved_answer_without_structured_metadata_still_works(self):
        previous = self.previous()
        previous.pop('calculation')
        result = run_assistant('that plus 7', history=[previous])
        self.assertEqual(result['calculation']['value'], 20)

    def test_interpreted_numeric_instruction_is_calculation_not_search(self):
        from main.src.agent.agent_service import decide_action
        question = 'Add 7 to the previous result (13).'
        route = decide_action(question)
        self.assertEqual(route['action'], 'calculator')
        self.assertEqual(run_calculation(question, route['expression'])['calculation']['value'], 20)

    def test_unrelated_or_unverified_messages_do_not_supply_arithmetic_values(self):
        for history in [[], [{'role':'assistant', 'content':'There are 13 tasks.', 'status':'answered'}],
                        [self.previous(), {'role':'assistant', 'content':'A new subject.'}]]:
            with self.subTest(history=history):
                self.assertIsNone(resolve_arithmetic_followup('that plus 7', history))
        self.assertIsNone(resolve_arithmetic_followup('from my PDF add 7 to that', [self.previous()]))

    def test_recomputes_safe_expression_instead_of_trusting_value_field(self):
        expression = resolve_arithmetic_followup('that plus 7', [self.previous(value=999)])
        self.assertEqual(run_calculation(expression, expression)['calculation']['value'], 20)
        self.assertIsNone(resolve_arithmetic_followup('that plus 7',
            [self.previous(expression='__import__("os").system("false")')]))

    def test_zero_division_reports_calculation_error_without_retrieval(self):
        result = run_assistant('that divided by 0', history=[self.previous()])
        self.assertEqual(result['status'], 'calculation_error')
        self.assertEqual(result['tools_used'], ['calculator'])

    def test_api_history_preserves_calculation_fields(self):
        payload = Ask.model_validate({'question':'that plus 7', 'history':[self.previous()]})
        result = run_assistant(payload.question, history=payload.model_dump()['history'])
        self.assertEqual(result['calculation']['value'], 20)

    def test_followup_reuses_full_precision_not_the_rounded_display_value(self):
        result = run_assistant('that times 3', history=[self.previous('1 / 3', 1 / 3)])
        self.assertEqual(result['calculation']['value'], 1)
        self.assertIsNone(parse_explicit_arithmetic('Add 7 to 13 from the uploaded PDF'))


if __name__ == '__main__':
    unittest.main()
