from main.src.utils import instructions
from main.src.utils.enums import Action, PromptName, ResultStatus, Role
from main.src.utils import regex_constants as rx
import json

from main.src.tools.llm import Client
from main.src.rag.rag_service import generate_document_answer
from main.src.utils.common_utils import load_prompt, make_result
from main.src.utils.constants import CANDIDATE_K, CONTEXT_K, CHAT_MODEL
from main.src.utils.diagnostics import debug
import re
import ast
import math
import operator
from jsonschema import validate

from main.src.agent.agent_utils import parse_vector
from main.src.rag.document_store import search_documents
from main.src.utils.schemas import SEARCH_AND_CALC_SCHEMA, CALCULATION_PLAN_SCHEMA

client = Client(timeout=60)


def parse_explicit_arithmetic(question):
    """Handle unambiguous arithmetic syntax without an LLM planning call."""
    text = question.strip().rstrip(".?")
    
    root = re.fullmatch(rx.ARITHMETIC_ROOT, text, re.I)
    percentage = re.fullmatch(rx.ARITHMETIC_PERCENTAGE, text, re.I)
    if root:
        return f"sqrt({root[1]})"
    if percentage:
        return f"{percentage[1]} / 100 * {percentage[2]}"
    expression = re.sub(rx.ARITHMETIC_PREFIX, "", text, flags=re.I)
    if re.fullmatch(rx.ARITHMETIC_EXPRESSION, expression):
        return expression
    return None


def calculate(expression):
    """Evaluate bounded arithmetic without eval() or arbitrary execution."""
    if not isinstance(expression, str):
        raise ValueError("Expression must be text.")

    expression = expression.strip()

    if not expression or len(expression) > 200:
        raise ValueError("Use an expression of 1–200 characters.")

    tree = ast.parse(expression, mode="eval")

    if sum(1 for _ in ast.walk(tree)) > 80:
        raise ValueError("Expression is too complex.")

    binary_operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
    }

    def checked(value):
        if type(value) not in (int, float):
            raise ValueError("Only real numbers are supported.")

        if not math.isfinite(value) or abs(value) > 1e15:
            raise ValueError("Result exceeds the calculator's limits.")

        return value

    def evaluate(node):
        if isinstance(node, ast.Constant):
            return checked(node.value)

        if isinstance(node, ast.UnaryOp):
            value = evaluate(node.operand)

            if isinstance(node.op, ast.UAdd):
                return checked(value)

            if isinstance(node.op, ast.USub):
                return checked(-value)

        if isinstance(node, ast.Call):
            if (isinstance(node.func, ast.Name) and node.func.id == "sqrt"
                    and len(node.args) == 1 and not node.keywords):
                return checked(math.sqrt(evaluate(node.args[0])))
            raise ValueError("Only sqrt(value) is allowed.")

        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Pow):
                base, exponent = evaluate(node.left), evaluate(node.right)
                if abs(exponent) > 12:
                    raise ValueError("Power exponents must be between -12 and 12.")
                return checked(operator.pow(base, exponent))
            operation = binary_operators.get(type(node.op))
            if operation is not None:
                return checked(
                    operation(
                        evaluate(node.left),
                        evaluate(node.right),
                    )
                )

        raise ValueError(
            "Use numbers, parentheses, +, -, *, /, %, bounded **, or sqrt(value)."
        )

    return evaluate(tree.body)


def run_calculation(question, expression, model_client=None):
    """Plan unit-aware word problems; execute only validated bounded arithmetic."""
    explanation = ''
    if parse_explicit_arithmetic(question) is None:
        response = (model_client or client).chat(
            model=CHAT_MODEL, think=False, format=CALCULATION_PLAN_SCHEMA,
            messages=[{'role': Role.SYSTEM, 'content': load_prompt(PromptName.CALCULATION_PLAN)},
                      {'role': Role.USER, 'content': question}],
            options={'temperature': 0, 'num_predict': 1024})
        plan = json.loads(response['message']['content'])
        validate(plan, CALCULATION_PLAN_SCHEMA)
        if not plan['ready']:
            if plan['expression'].strip() or not plan['clarification'].strip():
                raise ValueError('Invalid unready calculation plan.')
            return make_result(plan['clarification'], ResultStatus.NEEDS_CLARIFICATION,
                               Action.CALCULATOR)
        expression = plan['expression'].strip()
        explanation = plan['explanation'].strip()
        if not expression or not explanation or plan['clarification'].strip():
            raise ValueError('Invalid ready calculation plan.')
    else:
        # The original literal arithmetic takes precedence over model output.
        expression = parse_explicit_arithmetic(question)
    try:
        value = calculate(expression)
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError) as error:
        reason = 'Division by zero is undefined.' if isinstance(error, ZeroDivisionError) else (
            'The proposed expression uses unsupported operations or exceeds the calculator limits.')
        return make_result(reason, ResultStatus.CALCULATION_ERROR, Action.CALCULATOR,
                           [Action.CALCULATOR])
    answer = (explanation + '\n\n' if explanation else '') + f'`{expression}` = **{value:.10g}**'
    result = make_result(answer, ResultStatus.TOOL_COMPLETED, Action.CALCULATOR, [Action.CALCULATOR])
    result['calculation'] = {'expression': expression, 'value': value}
    return result

def run_cosine_search_and_calculate(question):
    action = Action.SEARCH_AND_CALCULATE
    tools_used = []

    try:
        a = parse_vector(question, "A")
        b = parse_vector(question, "B")

        if len(a) != len(b):
            raise ValueError("Vectors must have equal dimensions.")

        tools_used.append(Action.SEARCH_DOCUMENTS)
        debug("MULTI-TOOL STEP 1: search_documents")

        results = search_documents(
            "What is the cosine similarity formula?",
            n_results=40,
            max_chunks=8,
            hybrid=True,
            multi_query=False,
        )

        # Recognize the standard notation found in your current notes.
        formula_pattern = re.compile(
            rx.COSINE_FORMULA,
            flags=re.IGNORECASE,
        )
        prose_pattern = re.compile(
            rx.COSINE_FORMULA_PROSE, re.I)

        support = []

        for source_id, source in enumerate(results):
            match = formula_pattern.search(source["text"]) or prose_pattern.search(source["text"])

            if match:
                support = [{
                    "source_id": source_id,
                    "quote": match.group(0),
                }]
                break

        if not support:
            return make_result(
                "I couldn't find a supported cosine formula passage "
                "in the retrieved notes, so I haven't calculated it.",
                ResultStatus.INSUFFICIENT_EVIDENCE,
                action,
                tools_used=tools_used,
                results=results,
            )

        tools_used.append(Action.COSINE_SIMILARITY)
        debug("MULTI-TOOL STEP 2: cosine_similarity")

        calculation = cosine_similarity(a, b)

        answer = (
            "**Formula from your notes**\n\n"
            + support[0]["quote"]
            + "\n\n**Calculation**\n\n"
            + f"A = {a}\n\n"
            + f"B = {b}\n\n"
            + f"Dot product = {calculation['dot_product']:.10g}\n\n"
            + f"‖A‖ = {calculation['norm_a']:.10g}\n\n"
            + f"‖B‖ = {calculation['norm_b']:.10g}\n\n"
            + "Cosine similarity = dot product / (‖A‖ × ‖B‖)\n\n"
            + f"**Result: {calculation['similarity']:.10g}**"
        )

        return make_result(
            answer,
            ResultStatus.CALCULATION_COMPLETED,
            action,
            tools_used=tools_used,
            results=results,
            support=support,
        )

    except (ValueError, SyntaxError) as error:
        return make_result(
            str(error),
            ResultStatus.INVALID_CALCULATION_REQUEST,
            action,
            tools_used=tools_used,
        )

    except Exception as error:
        debug("COSINE PIPELINE ERROR:", type(error).__name__)

        return make_result(
            "I couldn't complete the search and calculation.",
            ResultStatus.EXECUTION_ERROR,
            action,
            tools_used=tools_used,
        )


def cosine_similarity(a, b):
    if len(a) != len(b):
        raise ValueError("Vectors must have equal dimensions.")

    norm_a = math.hypot(*a)
    norm_b = math.hypot(*b)

    if norm_a == 0 or norm_b == 0:
        raise ValueError(
            "Cosine similarity is undefined for a zero vector."
        )

    similarity = math.fsum(
        (x / norm_a) * (y / norm_b)
        for x, y in zip(a, b)
    )

    return {
        "similarity": similarity,
        "dot_product": math.fsum(
            x * y for x, y in zip(a, b)
        ),
        "norm_a": norm_a,
        "norm_b": norm_b,
    }

def run_search_and_calculate(question, system_prompt):
    if re.search(
        rx.COSINE_REQUEST,
        question,
        flags=re.IGNORECASE,
    ):
        return run_cosine_search_and_calculate(question)

    tools_used = [Action.SEARCH_DOCUMENTS]

    debug("MULTI-TOOL STEP 1: search_documents")

    results = search_documents(
        question,
        n_results=CANDIDATE_K,
        max_chunks=CONTEXT_K,
        hybrid=True,
        multi_query=False,
    )

    formula_evidence = generate_document_answer(
        (
            instructions.FORMULA_REQUEST.format(question=question)
        ),
        results,
        system_prompt=system_prompt,
        required_parts=[
            instructions.FORMULA_QUESTION
        ],
    )

    if not formula_evidence["answerable"]:
        return make_result(
            "I couldn't obtain verified formula evidence from your notes, "
            "so I haven't performed the calculation.",
            formula_evidence["status"],
            Action.SEARCH_AND_CALCULATE,
            tools_used=tools_used,
            results=results,
        )

    response = client.chat(
        model=CHAT_MODEL,
        format=SEARCH_AND_CALC_SCHEMA,
        options={"temperature": 0},
        messages=[
            {
                "role": Role.SYSTEM,
                "content": load_prompt(PromptName.SEARCH_AND_CALCULATE),
            },
            {
                "role": Role.USER,
                "content": json.dumps({
                    "request": question,
                    "formula_evidence": [
                        item["quote"]
                        for item in formula_evidence["support"]
                    ],
                }, ensure_ascii=False),
            },
        ],
    )

    calculation = json.loads(response["message"]["content"])

    if (
        not isinstance(calculation, dict)
        or set(calculation) != {"ready", "expression"}
        or type(calculation["ready"]) is not bool
        or not isinstance(calculation["expression"], str)
    ):
        raise ValueError("Invalid calculation-plan response.")

    expression = calculation["expression"].strip()

    if not calculation["ready"]:
        if expression:
            raise ValueError("Unexpected expression for an unready plan.")

        return make_result(
            "The formula, numerical inputs, or supported operations "
            "aren't sufficient for this calculation. "
            "Please provide the complete values and clarify the calculation.",
            ResultStatus.NEEDS_CLARIFICATION,
            Action.SEARCH_AND_CALCULATE,
            tools_used=tools_used,
            results=results,
            support=formula_evidence["support"],
        )

    if not expression:
        raise ValueError("Calculation expression is missing.")

    tools_used.append(Action.CALCULATOR)

    debug("MULTI-TOOL STEP 2: calculator")
    debug("CALCULATOR EXPRESSION:", expression)

    try:
        value = calculate(expression)
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
        return make_result(
            "I found formula evidence, but the proposed calculation "
            "couldn't be executed by the calculator.",
            ResultStatus.CALCULATION_ERROR,
            Action.SEARCH_AND_CALCULATE,
            tools_used=tools_used,
            results=results,
            support=formula_evidence["support"],
        )

    answer = (
        f"Formula evidence from your notes:\n\n"
        f"{formula_evidence['answer']}\n\n"
        f"Calculation:\n\n"
        f"`{expression}`\n\n"
        f"Result: **{value:.10g}**"
    )

    return make_result(
        answer,
        ResultStatus.CALCULATION_COMPLETED,
        Action.SEARCH_AND_CALCULATE,
        tools_used=tools_used,
        results=results,
        support=formula_evidence["support"],
    )

