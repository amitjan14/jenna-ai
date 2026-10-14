"""Development regression: local numerical planning and inline-code assistance.

No external services, personal project documents, or generated-code execution.
Scoring checks routing, numeric results and basic syntax/diagnosis; it does not
prove arbitrary formula correctness or replace human code review.
"""
import ast
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CODE = '''okay can you debug this code and give me a fix for it?
def divide(a, b): return a / b
x = 10 y = 0
try: result = divide(x, y) print("Result:", result) except ZeroDivisionError as e: print("Error:", e) print("Debug: The denominator cannot be zero.")'''
CASES = [
    ('bmi-cm', 'calculate BMI - age 24 - height 174 cm and weight 80kg', 80 / 1.74 ** 2),
    ('bmi-metres', 'What is my BMI? I weigh 80 kg and am 1.74 m tall, age 24.', 80 / 1.74 ** 2),
    ('bmi-imperial', 'Calculate BMI for weight 176 pounds and height 68.5 inches, age 24.',
     (176 * .45359237) / (68.5 * .0254) ** 2),
    ('tip', 'Calculate an 18 percent tip on a bill of 125 dollars.', 22.5),
    ('area', 'Calculate the area of a circle with radius 3 metres, using pi = 3.14159.', 3.14159 * 9),
    ('bmi-missing', 'Calculate BMI for age 24 and height 174 cm.', None),
    ('bmi-zero', 'Calculate BMI for age 24, height 0 cm and weight 80 kg.', None),
    ('inline-debug', CODE, 'code'),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=[case[0] for case in CASES])
    parser.add_argument('--output', type=Path, default=ROOT/'reports/calculation-code-development.json')
    args = parser.parse_args()
    rows = []
    with tempfile.TemporaryDirectory(prefix='jenna-calculation-eval-') as memory:
        os.environ['JENNA_MEMORY_PATH'] = memory
        from main.src.agent.assistant_service import run_assistant
        from main.src.agent import assistant_service
        from main.src.engineering.release import manifest
        snapshot = manifest()
        with patch.object(assistant_service, 'load_servers', return_value={}):
            for ident, question, expected in CASES:
                if args.case and ident != args.case:
                    continue
                started = perf_counter()
                try:
                    result = run_assistant(question)
                    if expected == 'code':
                        answer = result['answer']
                        blocks = re.findall(r'```(?:python|py)?\s*\n(.*?)```', answer, re.S)
                        parsed = []
                        handled_diagnostic = False
                        for block in blocks:
                            try:
                                tree = ast.parse(block)
                                parsed.append(block)
                                handled_diagnostic |= any(isinstance(node, ast.ExceptHandler)
                                    and any(isinstance(child, ast.Constant) and isinstance(child.value, str)
                                            and 'Debug:' in child.value for child in ast.walk(node))
                                    for node in ast.walk(tree))
                            except SyntaxError:
                                pass
                        checks = {'conversation': result.get('request_intent') == 'chat',
                                  'no_tools': not result.get('tools_used'),
                                  'syntax_diagnosed': 'syntax' in answer.casefold() or 'invalid' in answer.casefold(),
                                  'zero_division_explained': 'zero' in answer.casefold(),
                                  'valid_python_fix': bool(parsed),
                                  'error_diagnostic_in_handler': handled_diagnostic,
                                  'no_invalid_assignment_alternative': 'x = 10, y = 0' not in answer,
                                  'no_spaces_only_syntax_fix': not any(phrase in answer.casefold() for phrase in
                                      ('added a space between', 'due to missing whitespace', 'add spaces between the assignments')),
                                  'no_wrong_float_error_for_ints': 'float division by zero' not in answer.casefold()}
                    elif expected is None:
                        checks = {'clarified': result['status'] == 'needs_clarification',
                                  'not_executed': not result.get('tools_used')}
                    else:
                        checks = {'calculator_used': result.get('tools_used') == ['calculator'],
                                  'numeric_result': abs(result.get('calculation', {}).get('value', float('inf')) - expected) < 1e-5}
                    row = {'id':ident, 'question':question, 'passed':all(checks.values()),
                           'checks':checks, 'expected':expected, 'result':result}
                except Exception as error:
                    row = {'id':ident, 'passed':False, 'error':type(error).__name__}
                row['seconds'] = perf_counter() - started
                rows.append(row)
                print(ident, row['passed'], round(row['seconds'], 2), flush=True)
    sources = [*ROOT.glob('main/src/agent/*.py'), ROOT/'main/src/tools/calculator.py',
               *ROOT.glob('main/instructions/*instructions.md'), *ROOT.glob('main/src/utils/*.py'), Path(__file__)]
    report = {'kind':'development_regression', 'cases':len(rows), 'passed':sum(r['passed'] for r in rows),
              'limitations':['Small development set, not held-out accuracy.',
                             'Schema and AST validation do not prove formula semantics.',
                             'Generated code was parsed, never executed; human review is still needed.'],
              'manifest':snapshot, 'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
              'results':rows}
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str)+'\n')
    print(f"Passed {report['passed']}/{report['cases']}: {output}", flush=True)
    if report['passed'] != report['cases']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
