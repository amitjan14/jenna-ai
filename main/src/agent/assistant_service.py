"""Local intent interpretation and automatic dispatch across available sources."""
from main.src.utils.enums import AnswerKind, Connection, Intent, PromptName, ResultStatus, Role, SearchMode
from main.src.utils import regex_constants as rx
import json
import re
from jsonschema import validate
from main.src.tools.llm import get_client
from main.src.utils.common_utils import load_prompt, make_result
from main.src.utils.constants import ROUTER_MODEL
from main.src.utils.schemas import assistant_schema
from main.src.utils.telemetry import instrument_request
from main.src.engineering.runtime import checkpoint
from main.src.engineering.tracing import event
from main.src.agent.conversation import (
    EMPTY_STATE,
    context_messages,
    load_state,
    save_state,
    general_reply,
    rewrite_reply,
    memory_request,
    natural_summary,
)
from main.src.memory.note_memory import list_notes
from main.src.integrations.mcp_client import load_servers
from main.src.tools.calculator import parse_explicit_arithmetic, resolve_arithmetic_followup
from main.src.agent.agent_utils import is_direct_conversation
from main.src.agent.agent_service import run_agent
from main.src.rag.context import active_document_filter

PRIVATE_SCOPE = re.compile(rx.PRIVATE_DOCUMENT_SCOPE, re.I)

def plan_request(question, history=None, servers=None, model_client=None, state=None):
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
        raise ValueError('Question must contain 1–4000 characters')
    if servers is None:
        servers = load_servers()

    names = [Connection.LOCAL, *servers]
    capabilities = [{'name': Connection.LOCAL, 'purpose': 'General knowledge, explanations, writing, coding and conversation without search; natural saved-preference read/write/delete; uploaded PDF evidence; arithmetic; optional web search for explicit browsing or current facts'}]
    capabilities.extend({'name': name, 'label': config.get('label', name),
                         'context': config.get('context', {}),
                         'read_tools': config.get('allowed_tools', [])} for name, config in servers.items())
    recent = context_messages(history, question)
    checkpoint('interpreting_request', model=ROUTER_MODEL)
    response = (model_client or get_client(timeout=90)).chat(model=ROUTER_MODEL, think=False,
        format=assistant_schema(names), messages=[{'role': Role.SYSTEM, 'content': load_prompt(PromptName.ASSISTANT)},
          {'role': Role.USER, 'content': json.dumps({'question': question, 'history': recent,
                                               'capabilities': capabilities, 'state': state or EMPTY_STATE,
                                               'saved_note_keys': list(list_notes())[:100]}, ensure_ascii=False)}],
        options={'temperature': 0, 'num_predict': 1536})
    plan = json.loads(response['message']['content'])
    validate(plan, assistant_schema(names))
    plan['question'] = plan['question'].strip()
    plan['clarification'] = plan['clarification'].strip()
    if plan['clarification']:
        plan['question'] = ''
    elif not plan['question'] and plan['intent'].startswith('memory_'):
        plan['question'] = question.strip()
    elif not plan['question']:
        plan['clarification'] = 'Which subject or item would you like me to look up?'
    # Language interpretation may repair words, but cannot silently change an
    # explicit number, ticket key, URL or filename supplied by the user.
    anchors = re.findall(rx.REQUEST_ANCHOR, question, re.I)
    if plan['question'] and any(not re.search(rx.exact_anchor_pattern(a), plan['question'], re.I) for a in anchors):
        plan['question'] = question.strip()
        event('interpretation_anchors_preserved', status='original_question_retained')
    if plan['question']:
        original_context = question + '\n' + '\n'.join(m['content'] for m in recent) + json.dumps(state or EMPTY_STATE)
        introduced = re.findall(rx.REQUEST_IDENTIFIER, plan['question'], re.I)
        if any(a.casefold() not in original_context.casefold() for a in introduced):
            plan['question'] = question.strip()
            event('interpretation_anchors_preserved', status='invented_identifier_discarded')
    original_context = question + '\n' + '\n'.join(m['content'] for m in recent) + json.dumps(state or EMPTY_STATE)
    state_ids = re.findall(rx.REQUEST_IDENTIFIER, json.dumps(plan['state']), re.I)
    if any(identifier.casefold() not in original_context.casefold() for identifier in state_ids):
        plan['state'] = state or dict(EMPTY_STATE)
        event('interpretation_anchors_preserved', status='invented_state_identifier_discarded')
    # A private-source boundary applies to interpretation as well as dispatch.
    # Auto permits web fallback, so an explicitly scoped request must be Documents.
    if PRIVATE_SCOPE.search(question) and plan['intent'] not in {Intent.REWRITE,Intent.MEMORY_READ,Intent.MEMORY_WRITE,Intent.MEMORY_DELETE}:
        plan.update(connection=Connection.LOCAL, mode=SearchMode.DOCUMENTS, intent=Intent.TASK)
    from main.src.agent.agent_utils import is_local_code_request
    if is_local_code_request(question):
        plan.update(connection=Connection.LOCAL, mode=SearchMode.AUTO, intent=Intent.CHAT,
                    question=question.strip(), clarification='')
    return plan


@instrument_request
def run_assistant(question, history=None, connection=Connection.AUTO, mode=SearchMode.AUTO, filters=None, model_client=None, session_id=None):
    state = load_state(session_id, history)
    servers = load_servers()
    if connection not in {Connection.AUTO, Connection.LOCAL, *servers}:
        raise ValueError('Unknown connection')
    if mode not in {SearchMode.AUTO, SearchMode.DOCUMENTS, SearchMode.WEB, SearchMode.DOCUMENTS_AND_WEB}:
        raise ValueError('Unknown source mode')
    if not isinstance(question, str) or not question.strip():
        return make_result('Please enter a question.', ResultStatus.INVALID_REQUEST, None)
    text = question.strip()
    arithmetic_followup = resolve_arithmetic_followup(text, history)
    # Clear deterministic commands need no extra interpretation/model roundtrip.
    simple = text.casefold().startswith(('remember:', 'recall:', 'forget:')) or text.casefold() == 'memories'
    simple = simple or is_direct_conversation(text) or parse_explicit_arithmetic(text) is not None or arithmetic_followup is not None
    if simple and connection in {Connection.AUTO, Connection.LOCAL}:
        plan = {'connection': Connection.LOCAL, 'mode': mode, 'question': arithmetic_followup or text, 'clarification': '',
                'intent': Intent.CHAT if is_direct_conversation(text) else Intent.TASK, 'state': state, 'memory_key':'', 'memory_value':''}
    else:
        plan = plan_request(text, history, servers, model_client, state)
    # Memory and editing never acquire external tools merely through model routing.
    if plan['intent'] in {Intent.CHAT,Intent.REWRITE,Intent.MEMORY_READ,Intent.MEMORY_WRITE,Intent.MEMORY_DELETE}:
        plan['connection'] = Connection.LOCAL
    if connection not in {Connection.AUTO,Connection.LOCAL} and plan['intent'] not in {Intent.REWRITE,Intent.MEMORY_READ,Intent.MEMORY_WRITE,Intent.MEMORY_DELETE}:
        plan.update(connection=connection,intent=Intent.TASK)
    elif connection == Connection.LOCAL: plan['connection']=Connection.LOCAL
    if filters or mode != SearchMode.AUTO:
        if plan['intent'] not in {Intent.REWRITE,Intent.MEMORY_READ,Intent.MEMORY_WRITE,Intent.MEMORY_DELETE} and not is_direct_conversation(text):
            plan['intent']=Intent.TASK
        if filters or mode == SearchMode.DOCUMENTS: plan.update(connection=Connection.LOCAL,mode=SearchMode.DOCUMENTS)
        elif plan['connection']==Connection.LOCAL: plan['mode']=mode
    scoped = PRIVATE_SCOPE.search(text)
    if scoped and plan['intent'] not in {Intent.REWRITE,Intent.MEMORY_READ,Intent.MEMORY_WRITE,Intent.MEMORY_DELETE}:
        plan.update(connection=Connection.LOCAL,mode=SearchMode.DOCUMENTS,intent=Intent.TASK)
    if re.search(rx.LOCAL_ONLY_REQUEST, text, re.I):
        plan['connection']=Connection.LOCAL
        if plan['intent']==Intent.TASK:plan['mode']=SearchMode.DOCUMENTS
    checkpoint()
    if plan['clarification']:
        result = make_result(plan['clarification'], ResultStatus.NEEDS_CLARIFICATION, None)
    elif plan['intent'] == Intent.CHAT:
        result = general_reply(text, history, plan['state'])
        result['answer_kind']=AnswerKind.CONVERSATION
    elif plan['intent'] == Intent.REWRITE:
        result = rewrite_reply(text, history, plan['state'])
    elif plan['intent'].startswith('memory_'):
        result = memory_request(plan['intent'], plan['memory_key'], plan['memory_value'], text, session_id)
    elif plan['connection'] == Connection.LOCAL:
        token = active_document_filter.set(filters)
        try:
            personality = load_prompt(PromptName.PERSONALITY)
            result = run_agent(plan['question'], system_prompt=personality, history=history, search_mode=plan['mode'])
        finally: active_document_filter.reset(token)
        result = natural_summary(plan['question'], result)
    else:
        from main.src.integrations.mcp_client import run_mcp_question
        result = run_mcp_question(plan['question'], plan['connection'], history=history)
    if not plan['clarification']:
        checkpoint()
        save_state(session_id, plan['state'])
    result['conversation_state']=plan['state']
    result.update(connection=result.get('connection',plan['connection']), source_mode=plan['mode'], interpreted_question=plan['question'], request_intent=plan['intent'])
    label = servers.get(result['connection'], {}).get('label', plan['mode'] + ' · local')
    if plan['intent'] == Intent.REWRITE: label = 'Prior answer and available evidence · ' + label
    result.setdefault('notices', []).insert(0, 'Source: ' + label)
    event('request_dispatched', server=plan['connection'], strategy=plan['mode'])
    return result
