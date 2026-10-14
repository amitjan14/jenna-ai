"""Regressions for numerical word problems and supplied-code source selection."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from main.src.tools.calculator import calculate, run_calculation
from main.src.agent.agent_utils import is_local_code_request
from main.src.agent.assistant_service import run_assistant
from main.src.utils.enums import Action, ResultStatus

CODE_REQUEST = '''Can you debug this code and give me a fix?
def divide(a, b): return a / b
x = 10 y = 0
try: result = divide(x, y) print("Result:", result) except ZeroDivisionError as e: print("Error:", e)
'''


class CalculationCodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = patch('main.src.memory.memory_service.DB_PATH', Path(self.temp.name)/'memory.sqlite3')
        self.db.start()

    def tearDown(self):
        self.db.stop()
        self.temp.cleanup()

    def model(self, **values):
        model = Mock()
        model.chat.return_value = {'message': {'content': json.dumps(values)}}
        return model

    def test_bmi_formula_converts_centimetres_and_ignores_age(self):
        model = self.model(ready=True, expression='80 / (174 / 100) ** 2',
                          explanation='BMI = kg / metres squared; 174 cm = 1.74 m. Age is not a formula input.', clarification='')
        result = run_calculation('calculate BMI - age 24 - height 174 cm and weight 80kg', 'invalid ^ expression', model)
        self.assertEqual(result['status'], ResultStatus.TOOL_COMPLETED)
        self.assertAlmostEqual(result['calculation']['value'], 26.4235698243)
        self.assertEqual(result['tools_used'], [Action.CALCULATOR])
        self.assertIn('1.74', result['answer'])

    def test_word_problem_missing_inputs_does_not_execute(self):
        model = self.model(ready=False, expression='', explanation='', clarification='What is your weight in kg?')
        with patch('main.src.tools.calculator.calculate') as execute:
            result = run_calculation('calculate BMI height 174 cm', '80 / 1.74 ** 2', model)
        self.assertEqual(result['status'], ResultStatus.NEEDS_CLARIFICATION)
        execute.assert_not_called()
        self.assertEqual(result['tools_used'], [])

    def test_literal_math_ignores_model_expression_without_planning(self):
        model = Mock()
        result = run_calculation('calculate 6 * 7', '999', model)
        self.assertEqual(result['calculation']['value'], 42)
        model.chat.assert_not_called()

    def test_bounded_powers_and_invalid_operations(self):
        self.assertEqual(calculate('2 ** -2'), .25)
        for expression in ('2 ** 100', '10 ** (10 ** 10)', '(-1) ** 0.5', '80 / (0 / 100) ** 2',
                           '__import__("os")', '80 / (1.74 ^ 2)'):
            with self.subTest(expression=expression), self.assertRaises((ValueError, ZeroDivisionError)):
                calculate(expression)

    def test_invalid_generated_code_is_never_executed(self):
        model = self.model(ready=True, expression='print(42)', explanation='Answer', clarification='')
        result = run_calculation('calculate my total for 20 and 22', '', model)
        self.assertEqual(result['status'], ResultStatus.CALCULATION_ERROR)

    def test_literal_zero_division_has_specific_error(self):
        result = run_calculation('calculate 1 / 0', '')
        self.assertEqual(result['status'], ResultStatus.CALCULATION_ERROR)
        self.assertIn('Division by zero', result['answer'])

    def test_inline_debugging_repairs_incorrect_retrieval_plan(self):
        from main.tests.test_assistant import planned
        model = self.model(**planned(CODE_REQUEST, connection='local', mode='Documents'))
        with patch('main.src.agent.assistant_service.load_servers', return_value={}), \
             patch('main.src.agent.assistant_service.general_reply', return_value={'answer':'Fixed code', 'status':'conversation_completed'}) as chat, \
             patch('main.src.agent.assistant_service.run_agent') as retrieval:
            result = run_assistant(CODE_REQUEST, model_client=model)
        self.assertEqual(result['request_intent'], 'chat')
        self.assertEqual(chat.call_args.args[0], CODE_REQUEST.strip())
        retrieval.assert_not_called()

    def test_explicit_document_override_still_retrieves(self):
        from main.tests.test_assistant import planned
        model = self.model(**planned(CODE_REQUEST, connection='local'))
        with patch('main.src.agent.assistant_service.load_servers', return_value={}), \
             patch('main.src.agent.assistant_service.run_agent', return_value={'answer':'Evidence missing', 'status':'no_context'}) as retrieval:
            run_assistant(CODE_REQUEST, mode='Documents', model_client=model)
        self.assertEqual(retrieval.call_args.kwargs['search_mode'], 'Documents')

    def test_source_requests_and_non_debug_calculations_are_not_inline_help(self):
        self.assertTrue(is_local_code_request(CODE_REQUEST))
        self.assertFalse(is_local_code_request('Search official documents to fix this code: def divide(a,b): return a/b'))
        self.assertFalse(is_local_code_request('calculate 10 / 2'))

    def test_local_agent_inline_help_skips_search_and_calculator(self):
        from main.src.agent import agent_service as agent
        with patch.object(agent.client, 'chat', return_value={'message':{'content':'The syntax must be fixed first.'}}), \
             patch.object(agent, 'search_and_answer') as search, \
             patch.object(agent, 'run_calculation') as calculator:
            result = agent.run_agent(CODE_REQUEST)
        self.assertEqual(result['status'], ResultStatus.CONVERSATION_COMPLETED)
        search.assert_not_called()
        calculator.assert_not_called()


if __name__ == '__main__':
    unittest.main()
