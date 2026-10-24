from main.src.engineering.tracing import timed_step
"""Local dialogue, bounded session state, evidence-preserving edits and summaries."""
from main.src.utils import instructions
from main.src.utils.enums import Action, AnswerKind, Connection, Intent, PromptName, ResultStatus, Role, SourceKind
from main.src.utils import regex_constants as rx
import json
import re
import httpx2
import ollama
from jsonschema import validate, ValidationError
from main.src.utils.common_utils import make_result, load_prompt
from main.src.utils.constants import CHAT_MODEL
from main.src.tools.llm import get_client
from main.src.utils.schemas import STATE_SCHEMA, GROUNDED_VERIFY_SCHEMA, GROUNDED_SUMMARY_SCHEMA
from main.src.memory.note_memory import remember_note, recall_note, forget_note, list_notes
from main.src.utils.common_utils import normalize_key
from main.src.memory.memory_service import database
from main.src.agent.agent_utils import is_local_code_request
from main.src.engineering.runtime import RequestCancelled, DeadlineExceeded
from main.src.integrations.mcp_agent import bounded

EMPTY_STATE = {'goal': '', 'constraints': [], 'references': []}

def load_state(session_id=None, history=None):
    if session_id:
        with database() as db:
            row = db.execute('SELECT payload FROM conversation_state WHERE session_id=?', (session_id,)).fetchone()
        if row:
            state = json.loads(row[0])
            validate(state, STATE_SCHEMA)
            return state
    for message in reversed(history or []):
        state = message.get('conversation_state')
        if state:
            try:
                validate(state, STATE_SCHEMA)
                return state
            except (ValueError, TypeError, ValidationError):
                pass
    return dict(EMPTY_STATE)


def save_state(session_id, state):
    validate(state, STATE_SCHEMA)
    if session_id:
        with database() as db:
            db.execute(
                'INSERT INTO conversation_state(session_id,payload) VALUES (?,?) '
                'ON CONFLICT(session_id) DO UPDATE SET payload=excluded.payload,updated_at=CURRENT_TIMESTAMP',
                (session_id,
                 json.dumps(state, ensure_ascii=False))
            )


def context_messages(history, question, max_chars=18000):
    """Keep recent turns plus relevant older turns; state carries goals/constraints."""
    valid = [m for m in (history or []) if m.get('role') in {Role.USER, Role.ASSISTANT} and isinstance(m.get('content'), str)]
    terms = set(re.findall(rx.CONTEXT_WORD, question.casefold()))
    score = lambda pair: len(terms & set(re.findall(rx.CONTEXT_WORD, pair[1]['content'].casefold())))
    older = [pair for pair in sorted(enumerate(valid[:-12]), key=score, reverse=True) if score(pair)>0][:4]
    selected = {}
    used = 0
    # Reserve up to a third for older references, so long recent messages cannot
    # crowd out the relevant option or requirement the user is referring to.
    for index, message in older:
        text = message['content'][:min(2000, max_chars//3-used)]
        if text:
            selected[index] = {
                'role': message['role'],
                'content': text
            }
            used += len(text)
    for index in range(len(valid)-1, max(-1,len(valid)-13), -1):
        message = valid[index]
        text = message['content'][:5000]
        if used + len(text) > max_chars:
            continue
        selected[index] = {
            'role': message['role'],
            'content': text
        }
        used += len(text)
    return [selected[index] for index in sorted(selected)]


@timed_step('Generate conversation answer')
def general_reply(question, history=None, state=None, client=None):
    # Preference values stay in local generation; never put them in remote tool arguments.
    notes = dict(list(list_notes().items())[:20])
    system = load_prompt(PromptName.GENERATE_REPLY)
    messages = [
        {
            'role': Role.SYSTEM,
            'content': system
        },
        {
            'role': Role.SYSTEM,
            'content': instructions.USER_CONTEXT_PREFIX + json.dumps({
                'state': state or EMPTY_STATE,
                'saved_preferences': notes
            }, ensure_ascii=False)
        }
    ]
    messages.extend(context_messages(history, question))
    messages.append({
        'role': Role.USER,
        'content': question
    })
    model = client or get_client(timeout=120)
    answer = model.stream_chat(model=CHAT_MODEL, messages=messages,
        options={
            'temperature': 0 if is_local_code_request(question) else .3,
            'num_predict': 2048
        }, think=False)
    return make_result(
        answer,
        ResultStatus.CONVERSATION_COMPLETED,
        Action.CONVERSATION
    )


def _sources_from_message(message):
    if (message.get('support')
            and message.get('results')):
        sources = message['results'][:40]
        support = [s for s in message['support'][:40] if isinstance(s.get('source_id'), int)
                   and 0 <= s['source_id'] < len(sources) and isinstance(s.get('quote'), str)
                   and s['quote'] and s['quote'] in sources[s['source_id']].get('text', '')]
        return sources, support
    sources, support = [], []
    for passage in message.get('passages', [])[:8]:
        quote = passage.get('quote', '')
        if quote:
            sources.append({
                **passage,
                'text': quote
            })
            support.append({
                'source_id': len(sources)-1,
                'quote': quote
            })
    if not sources:
        budget = 16000
        for evidence in message.get('mcp_evidence', [])[-6:]:
            if evidence.get('is_error') or evidence.get('catalog_only'):
                continue
            text = json.dumps(bounded(evidence.get('content'), limit=1000, items=12), ensure_ascii=False)
            text = text[:min(5000, budget)]
            budget -= len(text)
            if not text:
                break
            sources.append({
                'filename': evidence.get('tool', 'MCP evidence'),
                'text': text,
                'kind': SourceKind.MCP
            })
            support.append({
                'source_id': len(sources)-1,
                'quote': text
            })
    return sources, support


@timed_step('Verify final wording')
def verify_grounded(question, answer, sources, support, client=None):
    schema = GROUNDED_VERIFY_SCHEMA
    relevant = [
        {
            'source_id': s['source_id'],
             'title': sources[s['source_id']].get('filename', ''),
             'page': sources[s['source_id']].get('page'),
             'quote': s['quote'],
             'context': sources[s['source_id']].get('text', '')[:3500]
         } for s in support
    ]
    response = (client or get_client(timeout=90)).chat(
        model=CHAT_MODEL,
        think=False,
        format=schema,
        messages=[
            {
                'role': Role.SYSTEM,
                'content': load_prompt(PromptName.GROUNDED_VERIFY)
            },
            {
                'role': Role.USER,
                'content': json.dumps({
                    'request': question,
                    'answer': answer,
                    'evidence': relevant
                }, ensure_ascii=False)
            }
        ],
        options={
            'temperature': 0,
            'num_predict': 512
        }
    )
    verdict = json.loads(response['message']['content'])
    validate(verdict, schema)
    return verdict


@timed_step('Compose final answer')
def natural_summary(question, result, client=None):
    """Synthesize a cited answer only after extractive evidence validation succeeds."""
    if (result.get('status') != ResultStatus.PASSAGES_VERIFIED
            or not result.get('support')):
        return result

    schema = GROUNDED_SUMMARY_SCHEMA
    sources, support = result['results'], result['support']
    selected = [
        {
            'source_id': s['source_id'],
            'citation': f"[{s['source_id']+1}]",
            'quote': s['quote'],
            'title': sources[s['source_id']].get('filename', ''),
            'page': sources[s['source_id']].get('page')
        } for s in support
    ]
    try:
        response = (client or get_client(timeout=90)).chat(
            model=CHAT_MODEL,
            format=schema,
            think=False,
            messages=[
                {
                    'role': Role.SYSTEM,
                    'content': load_prompt(PromptName.GROUNDED_SUMMARY)
                },
                {
                    'role': Role.USER,
                    'content': json.dumps({
                        'question': question,
                        'verified_passages': selected
                    }, ensure_ascii=False)
                }
            ],
            options={
                'temperature': 0,
                'num_predict': 1536
            }
        )
        draft = json.loads(response['message']['content'])
        validate(draft, schema)
        allowed = {s['source_id'] for s in support}
        markers = {int(x)-1 for x in re.findall(rx.CITATION_MARKER, draft['answer'])}
        if (not draft['answer'].strip()
                or not markers
                or markers != set(draft['source_ids'])
                or not markers <= allowed
        ):
            return result
        verdict = verify_grounded(question, draft['answer'], sources, support, client)
        if verdict['supported'] and verdict['complete']:
            result = {
                **result,
                'extractive_answer': result['answer'],
                'answer': draft['answer'],
                'answer_kind': AnswerKind.GROUNDED_SUMMARY
            }
    except (RequestCancelled, DeadlineExceeded):
        raise
    except (ValueError, TypeError, KeyError, IndexError, ValidationError,
            ConnectionError, TimeoutError, httpx2.TransportError, ollama.ResponseError):
        pass
    return result


@timed_step('Rewrite conversation answer')
def rewrite_reply(question, history, state=None, client=None):
    previous = next((m for m in reversed(history or []) if m.get('role') == Role.ASSISTANT and m.get('content')), None)
    if not previous:
        return make_result(
            'Which answer or text would you like me to revise?',
            ResultStatus.NEEDS_CLARIFICATION,
            Action.REWRITE
        )
    sources, support = _sources_from_message(previous)
    grounded = previous.get('answer_kind') in {AnswerKind.GROUNDED_SUMMARY, AnswerKind.GROUNDED_REWRITE} or previous.get('status') in {ResultStatus.PASSAGES_VERIFIED, ResultStatus.ANSWERED, ResultStatus.PARTIAL_ANSWER, ResultStatus.REVISION_REJECTED} or bool(support)
    if grounded and not support:
        return make_result(
            'I can revise that answer once its supporting evidence is available.'
            ' Please ask me to retrieve it again.',
            ResultStatus.NEEDS_CLARIFICATION,
            Action.REWRITE
        )
    if not grounded:
        result = general_reply(question, history, state, client)
        result.update(action=Action.REWRITE, answer_kind=AnswerKind.REWRITE)
        return result
    response = (client or get_client(timeout=90)).chat(model=CHAT_MODEL, think=False,
        messages=[
            {
                'role': Role.SYSTEM,
                'content': instructions.GROUNDED_REVISION
            },
            {
                'role': Role.USER,
                'content': json.dumps({
                    'request': question,
                    'previous_answer': previous['content'],
                    'evidence': [s['quote'] for s in support]
                }, ensure_ascii=False)
            }
        ],
        options={
            'temperature': 0,
            'num_predict': 1536
        }
    )
    answer = response['message']['content'].strip()
    previous_markers = set(re.findall(rx.CITATION_MARKER, previous['content']))
    markers = {int(x)-1 for x in re.findall(rx.CITATION_MARKER, answer)}
    valid_citations = markers <= {s['source_id'] for s in support} and (not previous_markers or bool(markers))
    try:
        verdict = verify_grounded(question, answer, sources, support, client)
    except (ValueError, TypeError, KeyError, IndexError, ValidationError):
        verdict = {
            'supported': False,
            'complete': False
        }
    if not answer or not valid_citations or not verdict['supported'] or not verdict['complete']:
        return make_result(
            'I could not verify the revision, so here is the original supported answer:\n\n' + previous['content'],
            ResultStatus.REVISION_REJECTED,
            Action.REWRITE,
            results=sources,
            support=support
        )
    result = make_result(
        answer,
        ResultStatus.PASSAGES_VERIFIED,
        Action.REWRITE,
        results=sources,
        support=support
    )
    result['answer_kind'] = AnswerKind.GROUNDED_REWRITE
    result['mcp_evidence'] = previous.get('mcp_evidence', [])
    result['connection'] = previous.get('connection', Connection.LOCAL)
    return result


def memory_request(intent, key, value, question, session_id=None):
    notes = list_notes()
    key = normalize_key(key) if key else ''
    key = next((existing for existing in notes if existing.replace('_',' ') == key.replace('_',' ')), key)
    # Natural language is accepted, but writes still require an explicit save/delete request.
    save = re.search(rx.MEMORY_SAVE_REQUEST, question, re.I)
    delete = re.search(rx.MEMORY_DELETE_REQUEST, question, re.I)
    if intent == Intent.MEMORY_WRITE:
        if not save or not key or not value.strip():
            return make_result(
                'What preference would you like me to save for future chats?',
                ResultStatus.NEEDS_CLARIFICATION,
                Action.MEMORY
            )
        remember_note(key, value, provenance={
            'source': 'explicit_user_request',
            'request': question[:1000],
            'session_id': session_id
        })
        return make_result(
            f'Saved your preference: {key.replace("_", " ")} = {value}.',
            ResultStatus.MEMORY_COMPLETED,
            Action.REMEMBER_NOTE,
            [Action.REMEMBER_NOTE]
        )
    if intent == Intent.MEMORY_DELETE:
        if not delete or not key:
            return make_result(
                'Which saved preference would you like me to forget?',
                ResultStatus.NEEDS_CLARIFICATION,
                Action.MEMORY
            )
        removed = forget_note(key)
        return make_result(
            'Forgot that saved preference.' if removed else 'I have no saved preference with that name.',
            ResultStatus.MEMORY_COMPLETED,
            Action.FORGET_NOTE,
            [Action.FORGET_NOTE]
        )
    selected = {
        key: recall_note(key)
    } if key and key in notes else notes if not key else {}

    if not selected:
        return make_result(
            'I have not saved that preference.',
            ResultStatus.MEMORY_COMPLETED,
            Action.RECALL_NOTE,
            [Action.RECALL_NOTE]
        )
    sources = [
        {
            'kind': SourceKind.MEMORY,
            'filename': 'Saved preferences',
            'page': None,
            'chunk_index': i,
            'text': k+': '+v
        } for i,(k,v) in enumerate(selected.items())
    ]
    support = [
        {
            'source_id': i,
            'quote': source['text']
        } for i,source in enumerate(sources)
    ]
    return make_result(
        'Your saved preferences:\n\n'+'\n'.join('- '+s['text'].replace('_',' ') for s in sources),
        ResultStatus.MEMORY_COMPLETED,
        Action.RECALL_NOTE,
        [Action.RECALL_NOTE],
        sources,
        support
    )
