from main.src.engineering.tracing import timed_step
"""Local intent interpretation and automatic dispatch across available sources."""
from main.src.utils.enums import AnswerKind, Connection, Intent, PromptName, ResultStatus, Role, SearchMode
from main.src.utils import regex_constants as rx
from main.src.utils import instructions
import json
import re
from jsonschema import validate
from main.src.tools.llm import get_client
from main.src.utils.common_utils import load_prompt, make_result
from main.src.utils.constants import ROUTER_MODEL
from main.src.utils.schemas import assistant_schema
from main.src.utils.telemetry import instrument_request
from main.src.rag.citations import requests_source_details
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
from main.src.memory.document_memory import load_document_records
from main.src.integrations.mcp_client import load_servers, run_mcp_question
from main.src.tools.calculator import parse_explicit_arithmetic, resolve_arithmetic_followup
from main.src.agent.agent_utils import is_direct_conversation, is_local_code_request, needs_conversation_context
from main.src.agent.agent_service import run_agent
from main.src.rag.context import active_document_filter, active_source_request
from main.src.integrations.jira_workflow import work_subject

PRIVATE_SCOPE = re.compile(rx.PRIVATE_DOCUMENT_SCOPE, re.I)
MEMORY_SCOPE = {Intent.MEMORY_READ, Intent.MEMORY_WRITE, Intent.MEMORY_DELETE}


def has_jira_intent(question):
    """A person's name alone does not establish a Jira lookup."""
    return bool(re.search(rx.JIRA_SOURCE_INTENT, question, re.I)
                or work_subject(question))


def matches_uploaded_document(question, filenames):
    terms = set(re.findall(rx.CONTEXT_WORD, question.casefold()))
    # Filename subjects (e.g. Amit in a resume) help choose a source, never
    # provide evidence for the answer itself.
    ignored = {'pdf', 'the', 'and', 'from', 'with', 'document', 'documents', 'file'}
    return any(terms & (set(re.findall(rx.CONTEXT_WORD, name.casefold())) - ignored)
               for name in filenames)


def preserve_document_question(question, plan):
    """A standalone source question is authoritative, not a model paraphrase."""
    if (plan['connection'] == Connection.LOCAL
            and plan['mode'] == SearchMode.DOCUMENTS
            and plan['intent'] == Intent.TASK
            and not plan['clarification']
            and not needs_conversation_context(question)
            and plan['question'] != question.strip()):
        plan['question'] = question.strip()
        plan['state'] = {**plan['state'], 'goal': question.strip()}
        event('interpretation_anchors_preserved', status='original_document_question_retained')


def referenced_document_filter(question, filenames):
    """Resolve one literal filename/unique title; do not narrow comparisons."""
    question = re.sub(rx.URL_REFERENCE, '', question, flags=re.I)
    matches = [(match.start(), match.end(), name)
               for name in filenames
               for match in re.finditer(rx.document_reference_pattern(name), question, re.I)]
    # 'Test PDF' inside 'Test Pdf 2' is not a second independent reference.
    names = {name for start, end, name in matches
             if not any(a <= start and end <= b and b-a > end-start
                        for a, b, other in matches if other != name)}
    return {'filename': names.pop()} if len(names) == 1 else None


@timed_step('Understand request and choose source')
def plan_request(question, history=None, servers=None, model_client=None, state=None):
    # Checking Question and its character limit
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
        raise ValueError('Question must contain 1–4000 characters')
    # if no servers present then loadServers is called
    if servers is None:
        servers = load_servers()

    # putting all under one variable
    names = [Connection.LOCAL, *servers]
    # Adding hardcoded capabilities
    capabilities = [
        {
            'name': Connection.LOCAL,
            'purpose': 'General knowledge, explanations, writing, coding and conversation without search; '
                       'natural saved-preference read/write/delete; uploaded PDF evidence; arithmetic; '
                       'optional web search for explicit browsing or current facts'
        }
    ]
    # Adding dynamic capabilities from servers
    capabilities.extend(
        {
            'name': name,
            'label': config.get('label', name),
            'context': config.get('context', {}),
            'read_tools': config.get('allowed_tools', [])
        } for name, config in servers.items()
    )
    # Getting recent messages from history related to question
    recent = context_messages(history, question)
    filenames = list(load_document_records())
    checkpoint('interpreting_request', model=ROUTER_MODEL)
    # Calling LLM for getting plan action
    response = (model_client or get_client(timeout=90)).chat(
        model=ROUTER_MODEL,
        think=False,
        format=assistant_schema(names),
        messages=[
            {
                'role': Role.SYSTEM,
                'content': load_prompt(PromptName.ASSISTANT)
            },
            {
                'role': Role.USER,
                'content': json.dumps({
                    'question': question,
                    'history': recent,
                    'capabilities': capabilities,
                    'uploaded_documents': filenames,
                    'state': state or EMPTY_STATE,
                    'saved_note_keys': list(list_notes())[:100]
                }, ensure_ascii=False)
            }
        ],
        options={
            'temperature': 0,
            'num_predict': 1536
        }
    )
    # get response from LLM
    plan = json.loads(response['message']['content'])
    # validate as per schema
    validate(plan, assistant_schema(names))
    # set local variables to monitor change
    planQuestion = plan['question'].strip()
    planClarification = plan['clarification'].strip()
    planIntent = plan['intent'].strip()
    planState = plan['state']

    if planClarification:
        planQuestion = ''
    elif not planQuestion and planIntent.startswith('memory_'):
        planQuestion = question.strip()
    elif not planQuestion:
        planClarification = 'Which subject or item would you like me to look up?'

    # Language interpretation may repair words, but cannot silently change an
    # explicit number, ticket key, URL or filename supplied by the user.
    anchors = re.findall(rx.REQUEST_ANCHOR, question, re.I)
    if planQuestion and any(not re.search(rx.exact_anchor_pattern(a), planQuestion, re.I) for a in anchors):
        planQuestion = question.strip()
        event('interpretation_anchors_preserved', status='original_question_retained')
    if planQuestion:
        original_context = question + '\n' + '\n'.join(m['content'] for m in recent) + json.dumps(state or EMPTY_STATE)
        introduced = re.findall(rx.REQUEST_IDENTIFIER, planQuestion, re.I)
        if any(a.casefold() not in original_context.casefold() for a in introduced):
            planQuestion = question.strip()
            event('interpretation_anchors_preserved', status='invented_identifier_discarded')
    original_context = question + '\n' + '\n'.join(m['content'] for m in recent) + json.dumps(state or EMPTY_STATE)
    state_ids = re.findall(rx.REQUEST_IDENTIFIER, json.dumps(planState), re.I)
    if any(identifier.casefold() not in original_context.casefold() for identifier in state_ids):
        planState = state or dict(EMPTY_STATE)
        event('interpretation_anchors_preserved', status='invented_state_identifier_discarded')

    # Updating plan with changes made
    event(f'interpretation_anchors_update_plan',
          existing_plan=plan, plan_state=planState, plan_question=planQuestion,
          plan_clarification=planClarification, plan_intent=planIntent)
    plan.update(
        question=planQuestion,
        clarification=planClarification,
        intent=planIntent,
        state=planState
    )
    event(f'interpretation_anchors_updated_plan', plan=plan)

    # A private-source boundary applies to interpretation as well as dispatch.
    # Auto permits web fallback, so an explicitly scoped request must be Documents.
    if (PRIVATE_SCOPE.search(question)
            and planIntent not in {
                Intent.REWRITE,
                *MEMORY_SCOPE,
            }
    ):
        plan.update(
            connection=Connection.LOCAL,
            mode=SearchMode.DOCUMENTS,
            intent=Intent.TASK
        )
    # Gate automatic Jira routing using the user's request, not a model's
    # invented interpretation. Only contextual follow-ups may inherit intent.
    jira_forbidden = bool(re.search(rx.JIRA_NEGATION, question, re.I))
    jira_intent = has_jira_intent(question) and not jira_forbidden
    explicit_web = bool(re.search(rx.EXPLICIT_WEB_SCOPE, question, re.I))
    profile_request = bool(re.search(rx.DOCUMENT_PROFILE_REQUEST, question, re.I))
    document_followup = False
    if needs_conversation_context(question):
        previous = next((m for m in reversed(history or []) if m.get('role') == Role.ASSISTANT), {})
        document_followup = (previous.get('connection') == Connection.LOCAL
                             and previous.get('source_mode') == SearchMode.DOCUMENTS)
        if not document_followup and not jira_forbidden and not profile_request:
            # Only the active topic may supply a missing source. Old tickets
            # elsewhere in history must not turn a new subject into a Jira read.
            user_context = next((m['content'] for m in reversed(recent) if m['role'] == Role.USER), '')
            if previous.get('connection') == 'jira':
                jira_intent = jira_intent or has_jira_intent(user_context)
            elif not previous and not user_context:
                jira_intent = jira_intent or has_jira_intent(json.dumps(state or EMPTY_STATE))
    if plan['intent'] not in {Intent.REWRITE, *MEMORY_SCOPE}:
        document_subject = matches_uploaded_document(question, filenames)
        # A PDF URL names a remote resource, not an uploaded local file.
        local_references = re.sub(rx.URL_REFERENCE, '', question, flags=re.I)
        explicit_documents = PRIVATE_SCOPE.search(question) or re.search(rx.PDF_FILENAME_REFERENCE, local_references, re.I)
        if (explicit_documents or (not explicit_web and (
                (document_followup and not jira_intent)
                or (document_subject and not jira_intent)
                or (plan['connection'] == 'jira' and not jira_intent)))):
            plan.update(connection=Connection.LOCAL, mode=SearchMode.DOCUMENTS,
                        intent=Intent.TASK)
        elif explicit_web:
            plan.update(connection=Connection.LOCAL, mode=SearchMode.WEB, intent=Intent.TASK)
        elif work_subject(question) and 'jira' in servers and not jira_forbidden:
            plan.update(connection='jira', mode=SearchMode.AUTO, intent=Intent.TASK)
    if is_local_code_request(question):
        plan.update(
            connection=Connection.LOCAL,
            mode=SearchMode.AUTO,
            intent=Intent.CHAT,
            question=question.strip(),
            clarification=''
        )
    preserve_document_question(question, plan)
    return plan


@instrument_request
def run_assistant(question, history=None, connection=Connection.AUTO, mode=SearchMode.AUTO, filters=None,
                  model_client=None, session_id=None):
    state = load_state(session_id, history)
    servers = load_servers()
    # check if said connection is supported
    if connection not in {
        Connection.AUTO,
        Connection.LOCAL,
        *servers
    }:
        raise ValueError('Unknown connection')
    # check if said mode is supported
    if mode not in {
        SearchMode.AUTO,
        SearchMode.DOCUMENTS,
        SearchMode.WEB,
        SearchMode.DOCUMENTS_AND_WEB
    }:
        raise ValueError('Unknown source mode')
    # Check if question is present
    if not isinstance(question, str) or not question.strip():
        return make_result('Please enter a question.', ResultStatus.INVALID_REQUEST, None)

    text = question.strip()
    arithmetic_followup = resolve_arithmetic_followup(text, history)

    # Clear deterministic commands need no extra interpretation/model roundtrip.
    memory_related = text.casefold().startswith(('remember:', 'recall:', 'forget:')) or text.casefold() == 'memories'
    simple = (memory_related
              or is_direct_conversation(text)
              or parse_explicit_arithmetic(text) is not None
              or arithmetic_followup is not None)
    if simple and connection in {
        Connection.AUTO,
        Connection.LOCAL
    }:
        plan = {
            'connection': Connection.LOCAL,
            'mode': mode,
            'question': arithmetic_followup or text,
            'clarification': '',
            'intent': Intent.CHAT if is_direct_conversation(text) else Intent.TASK,
            'state': state,
            'memory_key':'',
            'memory_value':''
        }
    else:
        plan = plan_request(text, history, servers, model_client, state)

    if (filters is None and connection in {Connection.AUTO, Connection.LOCAL}
            and mode in {SearchMode.AUTO, SearchMode.DOCUMENTS}
            and not re.search(rx.EXPLICIT_WEB_SCOPE, text, re.I)):
        filters = referenced_document_filter(text, load_document_records())

    # Memory and editing never acquire external tools merely through model routing.
    if plan['intent'] in {
        Intent.CHAT,
        Intent.REWRITE,
        *MEMORY_SCOPE,
    }:
        plan['connection'] = Connection.LOCAL
    if connection not in {
        Connection.AUTO,
        Connection.LOCAL
    } and plan['intent'] not in {
        Intent.REWRITE,
        *MEMORY_SCOPE,
    }:
        plan.update(
            connection=connection,
            intent=Intent.TASK
        )
    elif connection == Connection.LOCAL:
        plan['connection'] = Connection.LOCAL
    if filters or mode != SearchMode.AUTO:
        if plan['intent'] not in {
            Intent.REWRITE,
            *MEMORY_SCOPE,
        } and not is_direct_conversation(text):
            plan['intent'] = Intent.TASK
        if filters or mode == SearchMode.DOCUMENTS:
            plan.update(connection=Connection.LOCAL, mode=SearchMode.DOCUMENTS)
        elif plan['connection'] == Connection.LOCAL:
            plan['mode'] = mode
    scoped = PRIVATE_SCOPE.search(text)
    if scoped and plan['intent'] not in {
        Intent.REWRITE,
        *MEMORY_SCOPE,
    }:
        plan.update(connection=Connection.LOCAL,mode=SearchMode.DOCUMENTS,intent=Intent.TASK)
    if re.search(rx.LOCAL_ONLY_REQUEST, text, re.I):
        plan['connection']=Connection.LOCAL
        if plan['intent'] == Intent.TASK:
            plan['mode'] = SearchMode.DOCUMENTS
    if plan['connection'] == 'jira' and re.search(rx.JIRA_NEGATION, text, re.I):
        plan.update(connection=Connection.LOCAL, mode=SearchMode.DOCUMENTS)
    # Caller filters/mode can establish document scope after interpretation.
    preserve_document_question(text, plan)
    if (plan['connection'] == Connection.LOCAL and plan['mode'] == SearchMode.DOCUMENTS
            and plan['intent'] == Intent.TASK and not plan['clarification']
            and re.search(rx.IMAGE_CONTENT_REQUEST, text, re.I)):
        # Normalize an elliptical content request without dropping its subject.
        plan['question'] = instructions.IMAGE_CONTENT_QUESTION.format(request=plan['question'])
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
        request_token = active_source_request.set(text)
        try:
            personality = load_prompt(PromptName.PERSONALITY)
            result = run_agent(
                plan['question'],
                system_prompt=personality,
                history=history,
                search_mode=plan['mode']
            )
        finally:
            active_source_request.reset(request_token)
            active_document_filter.reset(token)
        # A request for image contents should retain the verified transcription.
        if (not requests_source_details(text)
                and not result.get('verbatim_transcription')
                and not re.search(rx.IMAGE_CONTENT_REQUEST, text, re.I)):
            result = natural_summary(plan['question'], result)
    else:
        result = run_mcp_question(
            plan['question'],
            plan['connection'],
            history=history
        )
    if not plan['clarification']:
        checkpoint()
        save_state(session_id, plan['state'])
    result['conversation_state']=plan['state']
    result.update(
        connection=result.get('connection',plan['connection']),
        source_mode=plan['mode'],
        interpreted_question=plan['question'],
        request_intent=plan['intent']
    )
    label = servers.get(result['connection'], {}).get('label', plan['mode'] + ' · local')
    if plan['intent'] == Intent.REWRITE:
        label = 'Prior answer and available evidence · ' + label
    result.setdefault('notices', []).insert(0, 'Source: ' + label)
    event('request_dispatched', server=plan['connection'], strategy=plan['mode'])
    return result
