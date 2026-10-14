"""Direct MCP client: discovery, validated read tool calls, and local planning."""
from main.src.utils import instructions
from main.src.utils.common_utils import load_prompt
from main.src.utils.enums import PromptName
from main.src.utils.enums import AuthType, ResultStatus, Role, Transport
from main.src.utils.constants import DEFAULT_CHAT_MODEL
from main.src.utils import regex_constants as rx
import argparse
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
import json
import os
import re
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit

import httpx2
from main.src.utils.schemas import MCP_PLAN_SCHEMA, MCP_ANSWER_SCHEMA, mcp_selection_schema
from jsonschema import validate
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import PaginatedRequestParams

from main.src.integrations.mcp_auth import token_storage, oauth_provider, LoginCallback

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / 'mcp' / 'servers.json'


def load_servers(path=None):
    data = json.loads(Path(path or os.getenv('JENNA_MCP_CONFIG', str(DEFAULT_CONFIG))).read_text())
    servers = data['servers']
    for name, config in servers.items():
        if not name.replace('-', '').replace('_', '').isalnum():
            raise ValueError('Invalid MCP server name')
        if config['transport'] == Transport.STREAMABLE_HTTP:
            url = urlsplit(config['url'])
            if url.username or url.password or not url.hostname or not (
                url.scheme == 'https' or url.scheme == 'http' and url.hostname in {'localhost', '127.0.0.1', '::1'}
            ):
                raise ValueError('MCP URLs require HTTPS (except loopback) and no embedded credentials')
        elif config['transport'] != Transport.STDIO or not config.get('command'):
            raise ValueError('Expected streamable-http URL or stdio command')
        auth = config.get('auth', {'type': AuthType.NONE})
        if auth['type'] not in {AuthType.NONE, AuthType.OAUTH, AuthType.BEARER, AuthType.BASIC}:
            raise ValueError('Unsupported MCP authentication')
        if set(auth) - {'type', 'token_env', 'username_env', 'password_env'}:
            raise ValueError('Store MCP credentials in environment variables, not configuration')
    return servers


def required_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f'Missing MCP credential environment variable: {name}')
    return value


@asynccontextmanager
async def connect(config, name, oauth=None):
    async with AsyncExitStack() as stack:
        if config['transport'] == Transport.STDIO:
            params = StdioServerParameters(command=config['command'], args=config.get('args', []),
                env={**os.environ, **{key: required_env(ref) for key, ref in config.get('env_refs', {}).items()}})
            streams = await stack.enter_async_context(stdio_client(params))
        else:
            auth_config = config.get('auth', {'type': AuthType.NONE})
            headers, auth = {}, None
            if auth_config['type'] == AuthType.OAUTH:
                auth = oauth or oauth_provider(config, token_storage(name))
            elif auth_config['type'] == AuthType.BEARER:
                headers['Authorization'] = 'Bearer ' + required_env(auth_config['token_env'])
            elif auth_config['type'] == AuthType.BASIC:
                auth = httpx2.BasicAuth(required_env(auth_config['username_env']), required_env(auth_config['password_env']))
            http = await stack.enter_async_context(httpx2.AsyncClient(auth=auth, headers=headers, timeout=30))
            streams = await stack.enter_async_context(streamable_http_client(config['url'], http_client=http))
        session = await stack.enter_async_context(ClientSession(*streams, read_timeout_seconds=210 if oauth else 45))
        await session.initialize()
        yield session


def permitted(tool, config):
    # An explicit allowlist is a user-reviewed read policy, including older servers
    # that omit readOnlyHint. Otherwise require the server's read annotation.
    if 'allowed_tools' in config:
        return tool.name in config['allowed_tools']
    return bool(tool.annotations and tool.annotations.read_only_hint)


async def catalog(session, config):
    tools, cursor, seen = [], None, set()
    for _ in range(20):
        page = await session.list_tools(params=PaginatedRequestParams(cursor=cursor) if cursor else None)
        tools.extend(tool for tool in page.tools if permitted(tool, config))
        cursor = page.next_cursor
        if not cursor:
            return tools
        if cursor in seen:
            raise RuntimeError('MCP server repeated a pagination cursor')
        seen.add(cursor)
    raise RuntimeError('MCP tool catalog exceeded pagination limit')


async def call_read_tool(session, tools, name, arguments):
    tool = next((item for item in tools if item.name == name), None)
    if tool is None:
        raise ValueError('Tool is not in the permitted read catalog')
    validate(arguments, tool.input_schema)
    result = await session.call_tool(name, arguments=arguments)
    content = result.structured_content
    if content is None:
        content = [{'type': block.type, 'text': getattr(block, 'text', '')} for block in result.content]
        for block in content:
            try:
                parsed = json.loads(block['text'])
            except (ValueError, TypeError):
                continue
            # Search metadata/highlight markup wastes the local model's context.
            if isinstance(parsed, dict) and isinstance(parsed.get('hits'), list):
                parsed = {'hits': [{'url': hit.get('url'), 'title': hit.get('hierarchy', {}).get('lvl1'),
                    'content': hit.get('content')} for hit in parsed['hits']], 'nextCursor': parsed.get('nextCursor')}
            block['text'] = parsed
    blocks = content if isinstance(content, list) else [{'text': content}]
    payload_error = any(isinstance(block, dict) and isinstance(block.get('text'), dict) and
                        (block['text'].get('error') is True or isinstance(block['text'].get('data'), dict) and
                         block['text']['data'].get('error') is True) for block in blocks)
    return {'tool': name, 'arguments': arguments, 'is_error': bool(result.is_error) or payload_error, 'content': content}


async def discover(name):
    config = load_servers()[name]
    async with connect(config, name) as session:
        return [tool.model_dump(mode='json', by_alias=True) for tool in await catalog(session, config)]


def jira_identifiers_supported(arguments, evidence, config, question):
    """Block fabricated Jira IDs even when they satisfy a tool's JSON schema."""
    known = set()
    typed_ids = {'boardId': set(), 'filterId': set(), 'sprintId': set()}
    def collect(value):
        if isinstance(value, dict):
            for child in value.values(): collect(child)
        elif isinstance(value, list):
            for child in value: collect(child)
        elif isinstance(value, (str, int)):
            known.add(str(value))
    for item in evidence:
        if not item['is_error']:
            collect(item['content'])
            from main.src.integrations.jira_workflow import payload
            data = payload(item)
            def typed(value):
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key in typed_ids and isinstance(child, (str, int)): typed_ids[key].add(str(child))
                        if key in {'board', 'filter', 'sprint'} and isinstance(child, dict) and 'id' in child:
                            typed_ids[key + 'Id'].add(str(child['id']))
                        typed(child)
                elif isinstance(value, list):
                    for child in value: typed(child)
            typed(data)
            role = {'listJiraBoards': 'boardId', 'getJiraBoardConfig': 'boardId',
                    'listJiraBoardSprints': 'sprintId'}.get(item['tool'])
            if role and isinstance(data, dict):
                for value in data.get('values', data.get('boards', data.get('sprints', []))):
                    if isinstance(value, dict) and 'id' in value: typed_ids[role].add(str(value['id']))
                if item['tool'] == 'getJiraBoardConfig' and 'id' in data: typed_ids[role].add(str(data['id']))
    collect(config.get('context', {}))
    for key in ('cloudId', 'boardId', 'filterId', 'sprintId', 'accountId', 'issueIdOrKey'):
        if key in arguments:
            value = str(arguments[key])
            if key in {'boardId', 'filterId', 'sprintId'} and (not value.isdecimal() or int(value) < 1):
                return False
            if key in typed_ids and value not in typed_ids[key] and not re.search(
                    rx.typed_id_pattern(key, value), question, re.I):
                return False
            if value not in known and not re.search(rx.identifier_pattern(value), question):
                return False
    if 'nextPageToken' in arguments and (arguments['nextPageToken'] in {'null', 'None', '', None}
                                        or str(arguments['nextPageToken']) not in known):
        return False
    return True






def compact_evidence(result):
    content = result['content']
    if len(json.dumps(content)) > 6000:
        if isinstance(content, list):
            readable = '\n'.join(block['text'] if isinstance(block.get('text'), str)
                                 else json.dumps(block.get('text', block)) for block in content if isinstance(block, dict))
        else:
            readable = json.dumps(content)
        return {**result, 'content': readable[:6000], 'truncated': True}
    return result


def answer_evidence(question, items):
    """Keep relevant paragraphs within the small local model's context window."""
    stop = {'what', 'which', 'where', 'when', 'would', 'should', 'could', 'with', 'from',
            'that', 'this', 'have', 'does', 'into', 'then', 'your', 'the', 'and', 'for', 'use'}
    terms = set(re.findall(rx.SEARCH_TERM, question.lower())) - stop
    selected = []
    for item in items:
        content = item['content']
        if isinstance(content, list):
            text = '\n\n'.join(block['text'] if isinstance(block.get('text'), str)
                               else json.dumps(block.get('text', block)) for block in content if isinstance(block, dict))
        else:
            text = content if isinstance(content, str) else json.dumps(content)
        paragraphs = [paragraph[offset:offset + 1500]
                      for paragraph in re.split(rx.PARAGRAPH_BREAK, text) if paragraph.strip()
                      for offset in range(0, len(paragraph), 1500)]
        ranked = sorted(range(len(paragraphs)), key=lambda index:
                        len(terms & set(re.findall(rx.SEARCH_TERM, paragraphs[index].lower()))), reverse=True)
        indices = sorted(ranked[:4])
        selected.append({'tool': item['tool'], 'arguments': item.get('arguments', {}),
                         'excerpts': [paragraphs[index] for index in indices]})
    return selected


async def ask_legacy(name, question, history=None, model_client=None):
    from main.src.tools.llm import Client
    from main.src.utils.constants import CHAT_MODEL
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
        raise ValueError('MCP question must contain 1 to 4000 characters')
    config = load_servers()[name]
    client = model_client or Client(timeout=60)
    started = perf_counter()
    evidence, tools_used, calls = [], [], 0
    attempted = set()

    async def generate(messages, schema):
        nonlocal calls
        response = await asyncio.to_thread(client.chat, model=CHAT_MODEL, messages=messages,
                                           format=schema, options={'temperature': 0})
        calls += 1
        value = json.loads(response['message']['content'])
        validate(value, schema)
        return value

    async with connect(config, name) as session:
        tools = await catalog(session, config)
        if not tools:
            raise RuntimeError('This MCP server exposed no permitted read tools. Configure a read allowlist if needed.')
        if name == 'jira':
            from main.src.integrations.jira_workflow import assigned_work, active_sprints, issue_details
            async def execute_jira(tool_name, arguments):
                return await call_read_tool(session, tools, tool_name, arguments)
            work = await active_sprints(question, config, execute_jira)
            if work is None:
                work = await assigned_work(question, config, execute_jira)
            if work is None:
                work = await issue_details(question, config, execute_jira)
            if work is not None:
                work['metrics'] = {'total_seconds': perf_counter() - started, 'llm_calls': 0}
                return work
            # Every generic Jira question starts with real site discovery so the
            # model can use the cloud ID immediately instead of spending its
            # budget on unsupported IDs.
            discovery = compact_evidence(await execute_jira('getAccessibleAtlassianResources', {}))
            evidence.append(discovery)
            tools_used.append('jira:getAccessibleAtlassianResources')
            attempted.add(('getAccessibleAtlassianResources', '{}'))
        tool_data = [{'name': tool.name, 'description': (tool.description or '')[:1000]} for tool in tools]
        selection_schema = mcp_selection_schema([tool.name for tool in tools])
        messages = [{'role': Role.SYSTEM, 'content':
            load_prompt(PromptName.MCP_LEGACY_PLAN)},
            {'role': Role.USER, 'content': json.dumps({'question': question, 'context': config.get('context', {}),
                'history': [{'role': m['role'], 'content': m['content'][:2000]} for m in (history or [])[-4:]
                    if m.get('role') in {Role.USER, Role.ASSISTANT} and isinstance(m.get('content'), str)], 'tools': tool_data})}]
        # Search-first servers can make a deterministic initial read, then let the
        # local model choose follow-up tools. This avoids inventing a search query API.
        seed = config.get('initial_search')
        for item in evidence:
            messages.append({'role': Role.USER, 'content': instructions.MCP_TOOL_RESULT_PREFIX + json.dumps(item)})
        if seed:
            arguments = {**seed.get('defaults', {}), seed['question_argument']: question}
            result = compact_evidence(await call_read_tool(session, tools, seed['tool'], arguments))
            attempted.add((seed['tool'], json.dumps(arguments, sort_keys=True)))
            evidence.append(result)
            tools_used.append(f'{name}:{seed["tool"]}')
            messages.append({'role': Role.USER, 'content': instructions.MCP_TOOL_RESULT_PREFIX + json.dumps(result)})
        for _ in range(4 - len(evidence)):
            plan = await generate(messages, selection_schema)
            if plan['action'] == 'answer':
                break
            tool = next((item for item in tools if item.name == plan['tool_name']), None)
            if tool is None:
                result = {'tool': plan['tool_name'], 'is_error': True, 'content': instructions.MCP_UNKNOWN_TOOL}
            else:
                arguments = await generate([
                    {'role': Role.SYSTEM, 'content': instructions.MCP_LEGACY_ARGUMENTS},
                    {'role': Role.USER, 'content': json.dumps({'question': question, 'context': config.get('context', {}),
                        'tool': tool_data[[t.name for t in tools].index(tool.name)], 'evidence': evidence})}], tool.input_schema)
                signature = (tool.name, json.dumps(arguments, sort_keys=True))
                if name == 'jira' and not jira_identifiers_supported(arguments, evidence, config, question):
                    result = {'tool': tool.name, 'is_error': True,
                              'content': instructions.MCP_UNVERIFIED_IDENTIFIER}
                elif signature in attempted:
                    result = {'tool': tool.name, 'is_error': True, 'content': instructions.MCP_REPEATED_CALL}
                else:
                    attempted.add(signature)
                    result = compact_evidence(await call_read_tool(session, tools, tool.name, arguments))
                    tools_used.append(f'{name}:{tool.name}')
            evidence.append(result)
            messages.append({'role': Role.ASSISTANT, 'content': json.dumps(plan)})
            messages.append({'role': Role.USER, 'content': instructions.MCP_TOOL_RESULT_PREFIX + json.dumps(result)})

    successful = [item for item in evidence if not item['is_error']]
    # Search hits locate documents; prefer the fetched text for final grounding.
    fetched = [item for item in successful if item['tool'] in config.get('answer_tools', [])]
    if fetched:
        successful = fetched
    final = {'supported': False, 'answer': ''}
    if successful:
        final = await generate([
            {'role': Role.SYSTEM, 'content': load_prompt(PromptName.MCP_LEGACY_ANSWER)},
            {'role': Role.USER, 'content': json.dumps({'question': question,
                                                  'evidence': answer_evidence(question, successful)})}], MCP_ANSWER_SCHEMA)
    verified = final['supported'] and bool(successful) and bool(final['answer'].strip())
    return {'status': ResultStatus.ANSWERED if verified else ResultStatus.INSUFFICIENT_EVIDENCE,
        'answer': final['answer'] if verified else 'The MCP tools did not provide enough evidence.',
        'tools_used': tools_used, 'support': [], 'results': [],
        'notices': [f'Connected directly to {config.get("label", name)}.'], 'mcp_evidence': evidence,
        'metrics': {'total_seconds': perf_counter() - started, 'llm_calls': calls}}


async def ask(name, question, history=None, model_client=None):
    """Use one general local tool-calling agent for every MCP server/question."""
    from main.src.integrations.mcp_agent import run
    from main.src.tools.llm import Client
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
        raise ValueError('MCP question must contain 1 to 4000 characters')
    config = load_servers()[name]
    from main.src.engineering.tracing import request_trace,event
    from main.src.engineering.cache import metadata_cache,credential_key
    from main.src.engineering.runtime import retry_read,checkpoint
    with request_trace('mcp') as trace:
        async with connect(config, name) as session:
            checkpoint(ResultStatus.CONNECTED,server=name)
            key=credential_key(config,name)
            tools=metadata_cache.get(('catalog',key))
            if tools is None:
                tools=await retry_read(lambda:catalog(session,config))
                metadata_cache.put(('catalog',key),tools,60)
            else:event('catalog_cache',cache='hit')
            if not tools:
                raise RuntimeError('No permitted read tools were exposed by the MCP server')
            async def execute(tool_name, arguments):
                cache_key=(key,tool_name,json.dumps(arguments,sort_keys=True))
                stable=tool_name in {'getAccessibleAtlassianResources','server_status'}
                cached=metadata_cache.get(cache_key) if stable else None
                if cached is not None:
                    event('tool_cache',tool=tool_name,cache='hit');return cached
                value=await retry_read(lambda:call_read_tool(session,tools,tool_name,arguments))
                if stable and not value['is_error']:metadata_cache.put(cache_key,value,30)
                return value
            result=await run(question,config,name,tools,execute,model_client or Client(timeout=180),
                             jira_identifiers_supported if name=='jira' else None,history)
            trace.status=result['status'];result['trace_id']=trace.id
            return result


def run_mcp_question(question, server_name, history=None):
    import ollama
    from main.src.engineering.runtime import RequestCancelled,DeadlineExceeded
    try:
        return asyncio.run(ask(server_name, question, history))
    except (RequestCancelled,DeadlineExceeded):
        raise
    except ollama.ResponseError as error:
        model = os.getenv('JENNA_MCP_MODEL', DEFAULT_CHAT_MODEL)
        if error.status_code == 404:
            raise RuntimeError(f'Local reasoning model {model} is unavailable. Install it with ollama pull {model}.') from None
        raise RuntimeError('The local reasoning model failed. Check Ollama and the model configuration.') from None
    except ConnectionError:
        raise RuntimeError('Cannot reach the local Ollama service. Start Ollama and retry.') from None
    except Exception as error:
        def control_error(value):
            if isinstance(value,(RequestCancelled,DeadlineExceeded)):return value
            for child in getattr(value,'exceptions',()):
                found=control_error(child)
                if found:return found
            return None
        interrupted=control_error(error)
        if interrupted:raise interrupted
        raise RuntimeError('MCP request failed. Check the endpoint and authentication; for Jira run the login command.') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('list')
    for action in ['tools', 'login', 'ask', 'call']:
        child = sub.add_parser(action)
        child.add_argument('server')
        if action == 'ask': child.add_argument('question')
        if action == 'call':
            child.add_argument('tool'); child.add_argument('--arguments', default='{}')
    args = parser.parse_args()
    if args.action == 'list':
        print(json.dumps({name: {'label': config.get('label', name), 'transport': config['transport']}
                          for name, config in load_servers().items()}, indent=2)); return

    async def execute():
        if args.action == 'tools': return await discover(args.server)
        if args.action == 'ask': return await ask(args.server, args.question)
        config = load_servers()[args.server]
        if args.action == 'login':
            if config.get('auth', {}).get('type') != AuthType.OAUTH:
                raise ValueError('This server does not need OAuth login')
            with LoginCallback() as callback:
                auth = oauth_provider(config, token_storage(args.server), callback.redirect, callback.callback)
                async with connect(config, args.server, oauth=auth) as session:
                    await catalog(session, config)
            return {'status': ResultStatus.CONNECTED, 'server': args.server}
        async with connect(config, args.server) as session:
            return await call_read_tool(session, await catalog(session, config), args.tool, json.loads(args.arguments))
    try:
        print(json.dumps(asyncio.run(execute()), indent=2, ensure_ascii=False))
    except Exception:
        # Transport/auth exception groups can include URLs and credentials. Avoid dumping them.
        parser.exit(1, 'MCP connection failed. Check the endpoint, permitted tools and authentication. For Jira run login jira.\n')


if __name__ == '__main__':
    main()
