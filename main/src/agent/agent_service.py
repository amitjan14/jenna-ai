from main.src.utils.enums import Action, FollowupStatus, PromptName, ResultStatus, Role, SearchMode
from main.src.utils import regex_constants as rx
import json
import re

from main.src.agent.agent_utils import is_search_calculation_request, is_direct_conversation, is_local_code_request, \
    is_document_inventory_request, needs_conversation_context
from main.src.memory.note_memory import handle_memory_command
from main.src.rag.document_store import search_documents, list_documents
from main.src.rag.rag_service import rewrite_search_query, generate_document_answer, plan_question_parts
from main.src.tools.calculator import calculate, run_search_and_calculate, run_calculation, resolve_arithmetic_followup
from main.src.tools.llm import get_client
from main.src.tools.web_tools import run_online_search
from main.src.utils.common_utils import load_prompt, make_result
from main.src.utils.constants import CHAT_MODEL, ROUTER_MODEL, CANDIDATE_K, CONTEXT_K
from main.src.utils.diagnostics import debug
from main.src.utils.schemas import ROUTE_SCHEMA, RESOLVE_FOLLOWUP_SCHEMA
from main.src.utils.telemetry import instrument_request


def decide_action(question):
    if is_search_calculation_request(question):
        return {
            "action": Action.SEARCH_AND_CALCULATE,
            "expression": "",
        }

    if is_direct_conversation(question) or is_local_code_request(question):
        return {"action": Action.ANSWER_DIRECTLY, "expression": ""}
    if is_document_inventory_request(question):
        return {"action": Action.LIST_DOCUMENTS, "expression": ""}
    from main.src.tools.calculator import parse_explicit_arithmetic
    expression = parse_explicit_arithmetic(question)
    if expression is not None:
        return {"action": Action.CALCULATOR, "expression": expression}

    response = get_client().chat(
        model=ROUTER_MODEL,
        messages=[
            {"role": Role.SYSTEM, "content": load_prompt(PromptName.ROUTING)},
            {"role": Role.USER, "content": question},
        ],
        format=ROUTE_SCHEMA,
        options={"temperature": 0},
    )

    route = json.loads(response["message"]["content"])

    if not isinstance(route, dict):
        raise ValueError("Routing response must be an object.")

    if set(route) != {"action", "expression"}:
        raise ValueError("Unexpected routing fields.")

    allowed = set(ROUTE_SCHEMA["properties"]["action"]["enum"])

    if not isinstance(route["action"], str):
        raise ValueError("Invalid routing action.")

    if route["action"] not in allowed:
        raise ValueError("Unknown routing action.")

    if not isinstance(route["expression"], str):
        raise ValueError("Calculator expression must be text.")

    if route["action"] == Action.CALCULATOR and not re.search(
            rx.CALCULATOR_INTENT, question, re.I):
        route = {"action": Action.SEARCH_DOCUMENTS, "expression": ""}

    if route["action"] != Action.CALCULATOR:
        # Non-calculator routes cannot execute an expression. Normalize the
        # model's unused field rather than failing an otherwise usable route.
        route["expression"] = ""

    return route

def clarification_selection(question, history):
    """Resolve an exact selection from 'Do you mean X or Y?'."""
    if not history:
        return None

    last_message = history[-1]

    if (
        last_message.get("role") != Role.ASSISTANT
        or last_message.get("status") != ResultStatus.NEEDS_CLARIFICATION
    ):
        return None

    match = re.fullmatch(
        rx.CLARIFICATION_CHOICES,
        last_message["content"],
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    def normalize(text):
        return " ".join(text.casefold().split()).strip(" .!?")

    choices = [choice.strip() for choice in match.groups()]

    selected = next(
        (
            choice
            for choice in choices
            if normalize(choice) == normalize(question)
        ),
        None,
    )

    if selected is None:
        return None

    # Find the unresolved request before the clarification.
    for message in reversed(history[:-1]):
        if message.get("role") != Role.USER:
            continue

        request = message["content"]

        references = list(re.finditer(
            rx.FOLLOWUP_REFERENCE,
            request,
            flags=re.IGNORECASE,
        ))

        if not references:
            continue

        # Multiple references need a more specific interpretation.
        if len(references) != 1:
            return None

        reference = references[0]

        return (
            request[:reference.start()]
            + selected
            + request[reference.end():]
        )

    return None

def resolve_followup(question, history=None):
    arithmetic = resolve_arithmetic_followup(question, history)
    if arithmetic is not None:
        return {'status': FollowupStatus.RESOLVED, 'question': arithmetic, 'clarification': ''}
    # Simple greetings and capability requests need no resolution.
    text = " ".join(question.casefold().split()).strip(" .!?")

    valid_history = [
        message
        for message in (history or [])
        if isinstance(message, dict)
           and message.get("role") in {Role.USER, Role.ASSISTANT}
           and isinstance(message.get("content"), str)
    ]

    # An explicitly named subject in a compound current request provides its
    # own context. Preserve the full request so resolution cannot drop clauses.
    if (re.search(rx.MULTIPART_CONJUNCTION, question, re.I)
            and re.search(rx.NAMED_SUBJECT_QUESTION, question)):
        return {"status": FollowupStatus.STANDALONE, "question": question, "clarification": ""}

    selected_question = clarification_selection(
        question,
        valid_history,
    )

    if selected_question is not None:
        debug("CLARIFICATION SELECTION:", selected_question)

        return {
            "status": FollowupStatus.RESOLVED,
            "question": selected_question,
            "clarification": "",
        }

    last_message = valid_history[-1] if valid_history else {}

    pending_clarification = (
            last_message.get("role") == Role.ASSISTANT
            and last_message.get("status") == ResultStatus.NEEDS_CLARIFICATION
    )

    # A complete new request may replace the pending clarification.
    explicit_new_request = bool(
        re.match(
            rx.QUESTION_PREFIX,
            text,
        )
        and not needs_conversation_context(question)
    )

    vague_reply = text in {
        "something else",
        "previous item",
        "the previous item",
        "topic",
    }

    if vague_reply and pending_clarification:
        return {
            "status": ResultStatus.NEEDS_CLARIFICATION,
            "question": "",
            "clarification": (
                "Please name the topic or item you mean."
            ),
        }

    if is_direct_conversation(question):
        return {
            "status": FollowupStatus.STANDALONE,
            "question": question,
            "clarification": "",
        }

    if (
            not needs_conversation_context(question)
            and (
            not pending_clarification
            or explicit_new_request
    )
    ):
        return {
            "status": FollowupStatus.STANDALONE,
            "question": question,
            "clarification": "",
        }

    recent_history = []

    for message in (history or [])[-8:]:
        if (
            isinstance(message, dict)
            and message.get("role") in {Role.USER, Role.ASSISTANT}
            and isinstance(message.get("content"), str)
        ):
            recent_history.append({
                "role": message["role"],
                "content": message["content"][:2000],
            })

    if not recent_history and not re.search(rx.MULTIPART_REQUEST, question, re.I):
        return {
            "status": ResultStatus.NEEDS_CLARIFICATION,
            "question": "",
            "clarification": (
                "Which topic or previous item do you mean?"
            ),
        }

    response = get_client().chat(
        model=CHAT_MODEL,
        messages=[
            {
                "role": Role.SYSTEM,
                "content": load_prompt(PromptName.RESOLVE_FOLLOWUP),
            },
            {
                "role": Role.USER,
                "content": json.dumps({
                    "history": recent_history,
                    "current_message": question,
                    "pending_clarification": (
                            pending_clarification
                            and not explicit_new_request
                    ),
                }, ensure_ascii=False),
            },
        ],
        format=RESOLVE_FOLLOWUP_SCHEMA,
        options={"temperature": 0},
    )

    payload = json.loads(response["message"]["content"])

    expected_keys = {"status", "question", "clarification"}

    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ValueError("Invalid follow-up response.")

    if any(not isinstance(payload[key], str) for key in expected_keys):
        raise ValueError("Follow-up fields must be strings.")

    status = payload["status"]

    if status not in {
        FollowupStatus.STANDALONE,
        FollowupStatus.RESOLVED,
        ResultStatus.NEEDS_CLARIFICATION,
    }:
        raise ValueError("Unknown follow-up status.")

    if (
        status == FollowupStatus.RESOLVED
        and payload["question"].strip() == question
        and payload["clarification"] == ""
    ):
        payload["status"] = FollowupStatus.STANDALONE
        payload["question"] = question
        status = FollowupStatus.STANDALONE

    if status == ResultStatus.NEEDS_CLARIFICATION:
        if payload["question"] != "":
            raise ValueError("Ambiguous request must not include a question.")

        clarification = payload["clarification"].strip()

        if not clarification or len(clarification) > 500:
            raise ValueError("Invalid clarification.")

        payload["clarification"] = clarification

    else:
        if payload["clarification"] != "":
            raise ValueError("Unexpected clarification.")

        if status == FollowupStatus.STANDALONE:
            if payload["question"] != question:
                raise ValueError("Standalone message was modified.")
        else:
            resolved_question = payload["question"].strip()

            if not resolved_question or len(resolved_question) > 4000:
                raise ValueError("Invalid resolved question.")

            payload["question"] = resolved_question

    return payload

def search_and_answer(original_question, search_query, system_prompt):
    results = search_documents(
        search_query,
        n_results=CANDIDATE_K,
        max_chunks=CONTEXT_K,
        hybrid=True,
        multi_query=False,
    )

    question_key = " ".join(original_question.casefold().split())

    required_parts = plan_question_parts(original_question)

    # Answer the original question, not the rewritten search query.
    document_answer = generate_document_answer(
        original_question,
        results,
        system_prompt=system_prompt,
        required_parts=required_parts,
    )

    return results, document_answer

@instrument_request
def run_agent(
    question,
    system_prompt="",
    history=None,
    search_mode=SearchMode.AUTO,
):
    if not isinstance(question, str) or not question.strip():
        return make_result(
            "Please enter a question.",
            ResultStatus.INVALID_REQUEST,
            None,
        )

    question = question.strip()
    memory_result = handle_memory_command(question)

    if memory_result is not None:
        return memory_result
    original_question = question
    debug("ORIGINAL USER QUESTION:", original_question)

    try:
        resolution = resolve_followup(original_question, history)
    except Exception as error:
        debug(
            "FOLLOW-UP RESOLUTION ERROR:",
            type(error).__name__,
            str(error),
        )

        return make_result(
            "I couldn't interpret that request. "
            "Please restate it with the topic included.",
            ResultStatus.RESOLUTION_ERROR,
            None,
        )

    debug("FOLLOW-UP STATUS:", resolution["status"])

    if resolution["status"] == ResultStatus.NEEDS_CLARIFICATION:
        return make_result(
            resolution["clarification"],
            ResultStatus.NEEDS_CLARIFICATION,
            None,
        )

    question = resolution["question"]
    debug("RESOLVED QUESTION:", question)

    try:
        debug("AGENT QUESTION:", question)
        route = decide_action(question)
    except Exception as error:
        debug("AGENT ROUTING ERROR:", type(error).__name__, str(error))

        return make_result(
            "I couldn't choose an action for that request. Please try again.",
            ResultStatus.ROUTING_ERROR,
            None,
        )

    action = route["action"]
    if (
            action == Action.LIST_DOCUMENTS
            and not is_document_inventory_request(question)
    ):
        debug("ROUTING CORRECTION: list_documents -> search_documents")
        action = Action.SEARCH_DOCUMENTS
    if (
            action == Action.ANSWER_DIRECTLY
            and not is_direct_conversation(question)
            and not (is_local_code_request(question) and search_mode == SearchMode.AUTO)
    ):
        debug("ROUTING CORRECTION: answer_directly -> search_documents")
        action = Action.SEARCH_DOCUMENTS

    allowed_modes = {SearchMode.AUTO, SearchMode.DOCUMENTS, SearchMode.WEB, SearchMode.DOCUMENTS_AND_WEB}

    if search_mode not in allowed_modes:
        return make_result(
            "Invalid search mode.",
            ResultStatus.INVALID_SEARCH_MODE,
            None,
        )

    if action == Action.SEARCH_DOCUMENTS and search_mode in {SearchMode.WEB, SearchMode.DOCUMENTS_AND_WEB}:
        mode = (
            "hybrid"
            if search_mode == SearchMode.DOCUMENTS_AND_WEB
            else "web"
        )

        debug("ONLINE SEARCH MODE:", mode)

        try:
            return run_online_search(
                question,
                mode,
                system_prompt,
            )
        except Exception as error:
            debug("ONLINE ANSWER ERROR:", type(error).__name__)

            return make_result(
                "I couldn't complete the answer from online sources.",
                ResultStatus.EXECUTION_ERROR,
                mode,
            )

    tools_used = []

    debug("AGENT ACTION:", action)

    try:
        if action == Action.SEARCH_AND_CALCULATE:
            return run_search_and_calculate(
                question,
                system_prompt,
            )

        if action == Action.CALCULATOR:
            return run_calculation(question, route['expression'])

        if action == Action.LIST_DOCUMENTS:
            tools_used.append(action)
            filenames = list_documents()

            if filenames:
                answer = (
                    f"I have {len(filenames)} indexed document(s):\n\n"
                    + "\n".join(f"- {name}" for name in filenames)
                )
            else:
                answer = "There are no indexed documents yet."

            return make_result(
                answer,
                ResultStatus.TOOL_COMPLETED,
                action,
                tools_used,
            )

        if action == Action.SEARCH_DOCUMENTS:
            tools_used.append(action)

            results, document_answer = search_and_answer(
                question,
                question,
                system_prompt,
            )

            retrieval_trace = [{
                "attempt": 1,
                "query": question,
                "status": document_answer["status"],
            }]

            debug("RETRIEVAL ATTEMPT 1:", document_answer["status"])

            retryable_statuses = {
                ResultStatus.NO_CONTEXT,
                ResultStatus.INSUFFICIENT_EVIDENCE,
            }

            document_scoped = bool(re.search(
                rx.PRIVATE_SOURCE_REFERENCE, question, re.I))
            if (
                not document_answer["answerable"]
                and (search_mode != SearchMode.AUTO or document_scoped)
                and document_answer["status"] in retryable_statuses
            ):
                try:
                    rewritten_query = rewrite_search_query(question)

                    original_key = " ".join(question.casefold().split())
                    rewritten_key = " ".join(
                        rewritten_query.casefold().split()
                    )

                    if rewritten_key == original_key:
                        debug("RETRIEVAL RETRY SKIPPED: unchanged query")

                        retrieval_trace.append({
                            "attempt": 2,
                            "query": rewritten_query,
                            "status": ResultStatus.SKIPPED_UNCHANGED_QUERY,
                        })
                    else:
                        debug("RETRIEVAL RETRY QUERY:", rewritten_query)

                        # Repeated entries record repeated tool calls.
                        tools_used.append(action)

                        retry_results, retry_answer = search_and_answer(
                            question,
                            rewritten_query,
                            system_prompt,
                        )

                        retrieval_trace.append({
                            "attempt": 2,
                            "query": rewritten_query,
                            "status": retry_answer["status"],
                        })

                        debug(
                            "RETRIEVAL ATTEMPT 2:",
                            retry_answer["status"],
                        )

                        if retry_answer["answerable"]:
                            # Replace both together so source IDs stay valid.
                            results = retry_results
                            document_answer = retry_answer
                        else:
                            debug(
                                "RETRIEVAL RETRY DID NOT PRODUCE AN ANSWER; "
                                "keeping the original refusal"
                            )

                except Exception as error:
                    debug(
                        "RETRIEVAL RETRY ERROR:",
                        type(error).__name__,
                        str(error),
                    )

                    retrieval_trace.append({
                        "attempt": 2,
                        "status": ResultStatus.RETRY_ERROR,
                        "error_type": type(error).__name__,
                    })

            document_scoped = bool(re.search(
                rx.PRIVATE_SOURCE_REFERENCE, question, re.I))
            if search_mode == SearchMode.AUTO and not document_answer["answerable"] and not document_scoped:
                online_result = run_online_search(question, "web", system_prompt)
                online_result["tools_used"] = tools_used + online_result["tools_used"]
                online_result["notices"].insert(0,
                    "Documents did not provide a verified answer; tried online search.")
                online_result["retrieval_trace"] = retrieval_trace + [{
                    "attempt": len(retrieval_trace) + 1, "query": question,
                    "source": "web", "status": online_result["status"],
                }]
                if online_result["status"] == ResultStatus.RETRIEVAL_UNAVAILABLE:
                    online_result["answer"] = (
                        "I couldn't answer from the uploaded documents, and online search "
                        "is unavailable. " + " ".join(online_result["notices"][1:]))
                return online_result

            if document_answer["answerable"]:
                answer = document_answer["answer"]
                support = document_answer["support"]
            else:
                support = []

                if document_answer["status"] in retryable_statuses:
                    answer = (
                        "I couldn't find enough information "
                        "in the uploaded documents."
                    )
                else:
                    answer = (
                        "I couldn't verify the answer "
                        "against the uploaded documents."
                    )

            result = make_result(
                answer,
                document_answer["status"],
                action,
                tools_used,
                results,
                support,
            )

            result["retrieval_trace"] = retrieval_trace
            return result

        messages = [
            {
                "role": Role.SYSTEM,
                "content": (
                    system_prompt
                    + load_prompt(PromptName.RUN_AGENT)
                ),
            }
        ]

        for message in (history or [])[-12:]:
            if (
                isinstance(message, dict)
                and message.get("role") in {Role.USER, Role.ASSISTANT}
                and isinstance(message.get("content"), str)
            ):
                messages.append({
                    "role": message["role"],
                    "content": message["content"],
                })

        messages.append({"role": Role.USER, "content": question})

        response = get_client().chat(
            model=CHAT_MODEL,
            messages=messages,
            options={"temperature": 0.3},
        )

        answer = response["message"]["content"].strip()

        if not answer:
            raise ValueError("The model returned an empty response.")

        return make_result(
            answer,
            ResultStatus.CONVERSATION_COMPLETED,
            action,
        )

    except Exception as error:
        debug("AGENT EXECUTION ERROR:", type(error).__name__, str(error))

        if action == Action.CALCULATOR and isinstance(
            error, (ValueError, SyntaxError, ZeroDivisionError)
        ):
            answer = (
                "I couldn't calculate that expression. "
                "Use numbers, parentheses, and +, -, *, / or %. "
                "Division by zero is not supported."
            )
        else:
            answer = "I couldn't complete that action. Please try again."

        return make_result(
            answer,
            ResultStatus.EXECUTION_ERROR,
            action,
            tools_used,
        )
