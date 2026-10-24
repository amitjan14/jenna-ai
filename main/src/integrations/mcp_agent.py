from main.src.engineering.tracing import timed_step
"""General local tool-calling agent driven by discovered MCP schemas."""
from main.src.utils import instructions
from main.src.utils.common_utils import load_prompt
from main.src.utils.enums import PromptName
from main.src.utils import regex_constants as rx
import re
from main.src.integrations.jira_workflow import prepare_due_date_read, due_date_facts
from main.src.utils.enums import ExecutionStatus, ResultStatus, Role
from main.src.utils.constants import DEFAULT_CHAT_MODEL, DEFAULT_MCP_CONTEXT_TOKENS
import hashlib
import asyncio
import json
import os
import time
from time import perf_counter
from main.src.utils.schemas import MCP_VERIFY_SCHEMA, MCP_REPAIR_SCHEMA, DISCOVER_TOOLS_SCHEMA, mcp_tool_definition, discovery_tool_definition
from jsonschema import ValidationError
from main.src.engineering.context import select_tools,fit_messages,summarize_history
from main.src.engineering.runtime import checkpoint
from main.src.engineering.tracing import event
from jsonschema import validate

SYSTEM = load_prompt(PromptName.MCP_AGENT)


def bounded(value, limit=6000, items=30):
    """Preserve JSON keys/identifiers/pagination while bounding long text and lists."""
    if isinstance(value, dict):
        result = {key: bounded(child, limit, items) for key, child in value.items()}
        return result
    if isinstance(value, list):
        trimmed = [bounded(child, limit, items) for child in value[:items]]
        if len(value) > items:
            trimmed.append({'_truncated_items': len(value) - items, '_returned_items': len(value)})
        return trimmed
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + instructions.TEXT_TRUNCATED_MARKER
    return value


def message_dict(message):
    return message.model_dump(exclude_none=True) if hasattr(message, 'model_dump') else dict(message)


def pending_pages(evidence):
    """Track the latest page per read/query, not an old first-page marker."""
    latest = {}
    for item in evidence:
        if item['is_error']:
            continue
        arguments = {key: value for key, value in item.get('arguments', {}).items()
                     if key not in {'startAt', 'maxResults', 'nextPageToken'}}
        signature = (item['tool'], json.dumps(arguments, sort_keys=True))
        value = item['content']
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
            value = value[0].get('text', value)
        if isinstance(value, dict):
            value = value.get('data', value)
        if not isinstance(value, dict):
            continue
        latest[signature] = value.get('isLast') is False or bool(value.get('nextPageToken'))
    return [tool for (tool, _), incomplete in latest.items() if incomplete]


@timed_step('Reason over MCP evidence')
async def run(question, config, name, tools, execute, client, identifier_check=None, history=None):
    event('agent_started',model=os.getenv('JENNA_MCP_MODEL',DEFAULT_CHAT_MODEL),
          prompt_version=hashlib.sha256(SYSTEM.encode()).hexdigest())
    started = perf_counter()
    model = os.getenv('JENNA_MCP_MODEL', DEFAULT_CHAT_MODEL)
    max_steps = int(os.getenv('JENNA_MCP_MAX_STEPS', '10'))
    max_reads = int(os.getenv('JENNA_MCP_MAX_READS', '16'))
    if not 1 <= max_steps <= 20 or not 1 <= max_reads <= 40:
        raise ValueError('Invalid MCP agent budget')
    selected,remaining_tools=select_tools(
        question,
        tools,
        history,
        limit=int(os.getenv('JENNA_TOOL_SCHEMA_LIMIT','8'))
    )
    def rebuild_definitions():
        result=[mcp_tool_definition(tool.name, tool.description, tool.input_schema) for tool in selected]
        if remaining_tools:
            result.append(discovery_tool_definition())
        return result
    definitions=rebuild_definitions()
    messages = [{
        'role': Role.SYSTEM,
        'content': SYSTEM + instructions.MCP_CONFIGURED_CONTEXT_PREFIX + json.dumps(config.get('context', {}))
    }]
    summary=summarize_history(history)
    if summary:messages.append({
        'role':Role.USER,
        'content':instructions.MCP_OLDER_CONTEXT_PREFIX+summary
    })
    messages.extend(
        {
            'role': m['role'],
            'content': m['content'][:6000]
        } for m in (history or [])[-6:]
            if m.get('role') in {Role.USER, Role.ASSISTANT}
            and isinstance(m.get('content'), str)
    )
    messages.append({
        'role': Role.USER,
        'content': question
    })
    references = question + '\n' + '\n'.join(m['content'][:6000] for m in (history or [])[-6:]
        if m.get('role') in {Role.USER, Role.ASSISTANT} and isinstance(m.get('content'), str))
    evidence, used, attempted, calls, reads = [], [], set(), 0, 0
    answer, status = '', ResultStatus.INSUFFICIENT_EVIDENCE
    for step in range(max_steps):
        checkpoint('planning',model=model,step=step)
        prepared,compacted=fit_messages(
            messages,
            definitions,
            int(os.getenv('JENNA_MCP_CONTEXT_TOKENS',str(DEFAULT_MCP_CONTEXT_TOKENS))),
            int(os.getenv('JENNA_MCP_OUTPUT_TOKENS','2048')),
            question
        )
        if compacted:event('context_compacted',message_count=len(messages),retained=len(prepared))
        response = await asyncio.to_thread(
            client.chat,
            model=model,
            messages=prepared,
            tools=definitions,
            think=os.getenv('JENNA_MCP_THINK', 'false').lower() == 'true',
            options={
                'temperature': 0,
                'num_ctx': int(os.getenv('JENNA_MCP_CONTEXT_TOKENS', str(DEFAULT_MCP_CONTEXT_TOKENS))),
                'num_predict': int(os.getenv('JENNA_MCP_OUTPUT_TOKENS', '2048'))
            })
        calls += 1
        message = message_dict(response['message'])
        tool_calls = message.get('tool_calls') or []
        if not tool_calls:
            candidate = (message.get('content') or '').strip()
            remaining = pending_pages(evidence)
            if remaining and step < max_steps - 1 and reads < max_reads:
                messages.append({
                    'role': Role.ASSISTANT,
                    'content': candidate or instructions.MCP_RETRIEVED_FALLBACK
                })
                messages.append({
                    'role': Role.USER,
                    'content': instructions.MCP_INCOMPLETE_PREFIX
                         + ', '.join(remaining) + instructions.MCP_INCOMPLETE_SUFFIX
                })
                continue
            if candidate and any(not item['is_error'] and not item.get('catalog_only') for item in evidence):
                answer, status = candidate, ResultStatus.ANSWERED
                break
            if step < max_steps - 1:
                messages.append({'role': Role.ASSISTANT, 'content': candidate or instructions.MCP_NO_TOOL_FALLBACK})
                messages.append({'role': Role.USER, 'content': instructions.MCP_NO_EVIDENCE})
            else:
                answer = candidate or 'I could not retrieve evidence for this request.'
            continue
        messages.append(message)
        for call in tool_calls:
            function = message_dict(call['function']) if not isinstance(call, dict) else call['function']
            tool_name, arguments = function.get('name', ''), function.get('arguments', {})
            result = {'tool': tool_name, 'arguments': arguments, 'is_error': True, 'content': ''}
            tool = next((item for item in tools if item.name == tool_name), None)
            try:
                if isinstance(arguments, str): arguments = json.loads(arguments)
                if tool_name=='discover_tools' and remaining_tools:
                    validate(arguments,DISCOVER_TOOLS_SCHEMA)
                    additions,_=select_tools(arguments['query'],remaining_tools,limit=4)
                    selected.extend(additions)
                    foundation=[item for item in selected if item.name in {'getAccessibleAtlassianResources','getJiraCurrentUser'}]
                    cap=int(os.getenv('JENNA_TOOL_SCHEMA_LIMIT','8'))
                    selected=foundation+[item for item in selected if item not in foundation][-max(1,cap-len(foundation)):]
                    remaining_tools=[item for item in tools if item not in selected]
                    definitions=rebuild_definitions()
                    result={
                        'tool':tool_name,
                        'arguments':arguments,
                        'is_error':False,
                        'catalog_only':True,
                        'content':{
                            'tools':[
                                {
                                    'name':item.name,
                                    'description':item.description,
                                    'input_schema':item.input_schema
                                } for item in additions
                            ]
                        }
                    }
                    evidence.append(result)
                    messages.append({
                        'role':Role.TOOL,
                        'tool_name':tool_name,
                        'content':json.dumps(result)
                    })
                    event('tool_discovery',count=len(additions));continue
                if tool is None:
                    raise ValueError(instructions.MCP_UNKNOWN_CATALOG_TOOL)
                if not isinstance(arguments, dict):
                    raise ValueError(instructions.MCP_INVALID_ARGUMENT_OBJECT)
                # Optional placeholders are not pagination tokens or meaningful filters.
                required = tool.input_schema.get('required', [])
                arguments = {key: value for key, value in arguments.items() if key in required or
                             value is not None and value not in ('', 'null', 'None', 'undefined')}
                if name == 'jira':
                    arguments = prepare_due_date_read(question, tool, arguments)
                signature = (tool_name, json.dumps(arguments, sort_keys=True))
                if signature in attempted:
                    raise ValueError(instructions.MCP_DUPLICATE_READ)
                if reads >= max_reads:
                    raise ValueError(instructions.MCP_READ_BUDGET)
                if identifier_check and not identifier_check(arguments, evidence, config, references):
                    raise ValueError(instructions.MCP_UNVERIFIED_READ_ID)
                attempted.add(signature)
                reads += 1
                checkpoint('tool_started',tool=tool_name,arguments=arguments)
                stamp=time.perf_counter()
                raw = await execute(tool_name, arguments)
                result = {**raw, 'content': bounded(raw['content'])}
                event('tool_finished',
                      tool=tool_name,
                      seconds=time.perf_counter()-stamp,
                      output_bytes=len(json.dumps(raw['content'])),
                      status='error' if raw['is_error'] else ExecutionStatus.COMPLETED
                )
                used.append(f'{name}:{tool_name}')
            except ValidationError as error:
                result['content'] = instructions.MCP_SCHEMA_ERROR_PREFIX + error.message[:500]
            except (ValueError, TypeError) as error:
                result['content'] = str(error)[:500]
            evidence.append(result)
            if name == 'jira' and re.search(rx.JIRA_DUE_DATE_REQUEST, question, re.I):
                result['requested_field_facts'] = due_date_facts([result])
            messages.append({
                'role': Role.TOOL,
                'tool_name': tool_name,
                'content': json.dumps(result, ensure_ascii=False)
            })
        if reads >= max_reads:
            break
    if not answer:
        # One final bounded synthesis without tools, so budget exhaustion cannot
        # silently trigger more network calls.
        prepared, _ = fit_messages(
            messages,
            [],
            int(os.getenv('JENNA_MCP_CONTEXT_TOKENS', str(DEFAULT_MCP_CONTEXT_TOKENS))),
            2048,
            question
        )
        response = await asyncio.to_thread(
            client.chat,
            model=model,
            messages=prepared + [{
                'role': Role.USER,
                'content': instructions.MCP_BUDGET_REACHED
            }],
            think=False,
            options={
                'temperature': 0,
                'num_ctx': int(os.getenv('JENNA_MCP_CONTEXT_TOKENS', str(DEFAULT_MCP_CONTEXT_TOKENS))),
                'num_predict': 2048
            }
        )
        calls += 1
        answer = (response['message'].get('content') or '').strip()
        if answer and any(not item['is_error'] and not item.get('catalog_only') for item in evidence):
            status = ResultStatus.ANSWERED
    if not any(not item['is_error'] and not item.get('catalog_only') for item in evidence):
        if answer.endswith('?'):
            status = ResultStatus.NEEDS_CLARIFICATION
        else:
            answer = 'I could not retrieve successful MCP evidence for this request. Please review the tool errors.'
    rejection_reason = ''
    if (name == 'jira' and status == ResultStatus.ANSWERED
            and re.search(rx.JIRA_DUE_DATE_REQUEST, question, re.I)):
        requested = set(key.upper() for key in re.findall(rx.JIRA_ISSUE_KEY_REFERENCE, question))
        missing = {fact['issue'].upper() for fact in due_date_facts(evidence) if not fact['returned']}
        if len(requested) == 1 and requested <= missing:
            key = next(iter(requested))
            status = ResultStatus.PARTIAL_ANSWER
            rejection_reason = 'The requested duedate field was not returned by Jira.'
            answer = (f'Jira did not return the due-date field for {key}. '
                      'I cannot determine whether a due date is set from these results.')
    if status == ResultStatus.ANSWERED:
        verification_budget=max(4000,(int(os.getenv('JENNA_MCP_CONTEXT_TOKENS',str(DEFAULT_MCP_CONTEXT_TOKENS)))-1024)*3-len(answer)-len(references)-len(question)-3000)
        verification_evidence=[];used_bytes=0
        for item in reversed(evidence):
            candidate=bounded(item,limit=1200,items=20)
            size=len(json.dumps(candidate))
            if used_bytes+size>verification_budget:continue
            verification_evidence.insert(0,candidate);used_bytes+=size
        verification_omitted=len(evidence)-len(verification_evidence)
        if verification_omitted:event('verification_context_compacted',omitted=verification_omitted)
        # Independent semantic check: successful unrelated reads cannot turn an
        # unsupported answer into an answered request.
        async def verify(candidate_answer):
            return await asyncio.to_thread(client.chat, model=model, think=False, format=MCP_VERIFY_SCHEMA,
            messages=[{
                'role': Role.SYSTEM,
                'content': load_prompt(PromptName.MCP_VERIFY)
            },
            {
                'role': Role.USER,
                'content': json.dumps({
                    'question': question,
                    'conversation': '\n'.join(m['content'][:6000] for m in (history or [])[-6:]
                                              if m.get('role') == Role.USER and isinstance(m.get('content'), str)),
                    'candidate': candidate_answer,
                    'evidence': verification_evidence,
                    'requested_field_facts': due_date_facts(verification_evidence) if name == 'jira' else [],
                    'omitted_results':verification_omitted
                }, ensure_ascii=False)
            }],
            options={
                'temperature': 0,
                'num_ctx': int(os.getenv('JENNA_MCP_CONTEXT_TOKENS', str(DEFAULT_MCP_CONTEXT_TOKENS))),
                'num_predict': 1024
            })
        check = await verify(answer)
        calls += 1
        try:
            verification = json.loads(check['message']['content'])
            validate(verification, MCP_VERIFY_SCHEMA)
            if not verification['supported']:
                # One repair from the same successful evidence, then verify again.
                # This never turns an unchecked candidate into an accepted answer.
                checkpoint('repairing_answer', model=model)
                repair_schema = MCP_REPAIR_SCHEMA
                repair = await asyncio.to_thread(
                    client.chat,
                    model=model,
                    think=False,
                    format=repair_schema,
                    messages=[{
                        'role': Role.SYSTEM,
                        'content': load_prompt(PromptName.MCP_REPAIR)
                    },
                    {
                        'role': Role.USER,
                        'content': json.dumps({
                            'question': question,
                            'candidate': answer,
                            'rejection': verification['reason'],
                            'evidence': [item for item in verification_evidence
                                         if not item['is_error'] and not item.get('catalog_only')]
                        }, ensure_ascii=False)
                    }],
                    options={
                        'temperature': 0,
                        'num_ctx': int(os.getenv('JENNA_MCP_CONTEXT_TOKENS', str(DEFAULT_MCP_CONTEXT_TOKENS))),
                        'num_predict': 1536
                    }
                )
                calls += 1
                repaired = json.loads(repair['message']['content'])
                validate(repaired, repair_schema)
                if repaired['answer'].strip():
                    check = await verify(repaired['answer'])
                    calls += 1
                    repair_verdict = json.loads(check['message']['content'])
                    validate(repair_verdict, MCP_VERIFY_SCHEMA)
                    if repair_verdict['supported']:
                        answer, verification = repaired['answer'].strip(), repair_verdict
                        event('answer_repaired', status='verified')
            if not verification['supported']:
                status = ResultStatus.INSUFFICIENT_EVIDENCE
                rejection_reason = verification['reason']
                answer = 'I could not verify the answer from the MCP results. Please review the retrieved evidence.'
            elif not verification['complete']:
                status = ResultStatus.PARTIAL_ANSWER
                rejection_reason = verification['reason']
            elif verification_omitted:
                status=ResultStatus.PARTIAL_ANSWER
                rejection_reason='Some tool evidence exceeded the verification context budget.'
        except (ValueError, ValidationError):
            status = ResultStatus.INSUFFICIENT_EVIDENCE
            answer = 'The local model could not verify this answer. Please review the MCP tool evidence.'
    return {
        'status': status,
        'answer': answer or 'I could not retrieve evidence for this request.',
        'tools_used': used,
        'support': [],
        'results': [],
        'mcp_evidence': evidence,
        'notices': [f'Connected directly to {config.get("label", name)}. Reasoning runs locally with {model}.'],
        'metrics': {
            'total_seconds': perf_counter() - started,
            'llm_calls': calls,
            'mcp_reads': reads
        },
        'model': model,
        'rejection_reason': rejection_reason
    }
