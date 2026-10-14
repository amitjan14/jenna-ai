from main.src.utils import regex_constants as rx
import re
import ast
import math

def parse_vector(question, label):
    matches = re.findall(
        rx.vector_pattern(label),
        question,
        flags=re.IGNORECASE,
    )

    if len(matches) != 1:
        raise ValueError(
            f"Provide exactly one vector {label}, "
            f"such as {label} = [1, 2, 3]."
        )

    if len(matches[0]) > 2000:
        raise ValueError("Vector input is too long.")

    values = ast.literal_eval(matches[0])

    if (
        not isinstance(values, list)
        or not 1 <= len(values) <= 100
    ):
        raise ValueError("Use vectors containing 1–100 numbers.")

    if any(
        type(value) not in (int, float)
        or abs(value) > 1e12
        or not math.isfinite(value)
        for value in values
    ):
        raise ValueError(
            "Vector components must be finite numbers "
            "with magnitude no greater than 1e12."
        )

    return values

def is_search_calculation_request(question):
    text = question.casefold()

    has_documents = bool(
        re.search(rx.DOCUMENT_REFERENCE, text)
    )

    has_search = bool(
        re.search(rx.SEARCH_REQUEST, text)
    )

    has_calculation = bool(
        re.search(rx.CALCULATION_REQUEST, text)
    )

    return has_documents and has_search and has_calculation

def is_document_inventory_request(question):
    text = question.casefold()

    has_document_reference = bool(
        re.search(rx.DOCUMENT_INVENTORY_REFERENCE, text)
    )

    has_inventory_intent = bool(
        re.search(
            rx.DOCUMENT_INVENTORY_REQUEST,
            text,
        )
    )

    has_content_filter = bool(
        re.search(
            rx.DOCUMENT_CONTENT_FILTER,
            text,
        )
    )

    return (
        has_document_reference
        and has_inventory_intent
        and not has_content_filter
    )

def is_local_code_request(question):
    """Inline code help needs reasoning, unless external evidence is requested."""
    return bool(re.search(rx.INLINE_CODE, question, re.I)
                and re.search(rx.CODE_HELP_REQUEST, question, re.I)
                and not re.search(rx.CODE_SOURCE_REQUEST, question, re.I))


def is_direct_conversation(question):
    text = " ".join(question.casefold().split())
    text = text.strip(" \t\n.!?")

    patterns = rx.DIRECT_CONVERSATION_PATTERNS

    return any(re.fullmatch(pattern, text) for pattern in patterns)

def needs_conversation_context(question):
    text = " ".join(question.casefold().split())

    patterns = rx.CONTEXT_REFERENCE_PATTERNS

    return any(re.search(pattern, text) for pattern in patterns)
