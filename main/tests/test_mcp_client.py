"""Outbound MCP contracts, bounded planning, and credential storage."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from mcp.types import Tool, ToolAnnotations, ListToolsResult, CallToolResult, TextContent
from mcp.shared.auth import OAuthToken
from main.src.integrations import mcp_client as client
from main.src.integrations.mcp_auth import FileTokenStorage


READ = Tool(name='lookup', description='Read a value', input_schema={
    'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query'],
    'additionalProperties': False}, annotations=ToolAnnotations(read_only_hint=True))
WRITE = Tool(name='delete', input_schema={'type': 'object'}, annotations=ToolAnnotations(read_only_hint=False))


class Session:
    def __init__(self):
        self.calls = []
        self.pages = []

    async def list_tools(self, params=None):
        self.pages.append(params.cursor if params else None)
        return ListToolsResult(tools=[READ] if params else [WRITE], next_cursor=None if params else 'next')

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return CallToolResult(content=[TextContent(type='text', text='Tokyo')], is_error=False)


class Model:
    def __init__(self, plans): self.plans = iter(plans)
    def chat(self, **kwargs): return {'message': {'content': json.dumps(next(self.plans))}}


def plan(action, tool=''):
    return dict(action=action, tool_name=tool)


class OutboundTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_pagination_and_write_filter(self):
        session = Session()
        tools = await client.catalog(session, {})
        self.assertEqual([tool.name for tool in tools], ['lookup'])
        self.assertEqual(session.pages, [None, 'next'])
        self.assertTrue(client.permitted(READ, {'allowed_tools': ['lookup']}))
        self.assertFalse(client.permitted(READ, {'allowed_tools': []}))

    async def test_validation_prevents_call(self):
        session = Session()
        for name, args in [('delete', {}), ('lookup', {'wrong': 'query'})]:
            with self.assertRaises(Exception):
                await client.call_read_tool(session, [READ], name, args)
        self.assertEqual(session.calls, [])
        result = await client.call_read_tool(session, [READ], 'lookup', {'query': 'capital'})
        self.assertEqual(result['content'][0]['text'], 'Tokyo')

    async def test_error_in_server_json_payload_is_not_successful_evidence(self):
        class ErrorSession:
            async def call_tool(self, name, arguments):
                return CallToolResult(content=[TextContent(type='text', text='{"error":true,"message":"read failed"}')], is_error=False)
        result = await client.call_read_tool(ErrorSession(), [READ], 'lookup', {'query': 'capital'})
        self.assertTrue(result['is_error'])

    async def test_planner_uses_schema_validated_arguments_and_evidence(self):
        session = Session()
        @asynccontextmanager
        async def connection(*args): yield session
        model = Model([plan('call_tool', 'lookup'), {'query': 'capital'},
                       plan('answer'), {'supported': True, 'answer': 'Tokyo'}])
        with patch.object(client, 'connect', connection), patch.object(client, 'load_servers', return_value={'test': {}}):
            result = await client.ask_legacy('test', 'capital?', model_client=model)
        self.assertEqual(result['answer'], 'Tokyo')
        self.assertEqual(session.calls, [('lookup', {'query': 'capital'})])
        self.assertEqual(result['metrics']['llm_calls'], 4)
        self.assertFalse(result['mcp_evidence'][0]['is_error'])

    async def test_planner_cannot_answer_without_tool_evidence(self):
        @asynccontextmanager
        async def connection(*args): yield Session()
        with patch.object(client, 'connect', connection), patch.object(client, 'load_servers', return_value={'test': {}}):
            result = await client.ask_legacy('test', 'question', model_client=Model([plan('answer')]))
        self.assertEqual(result['status'], 'insufficient_evidence')
        self.assertNotIn('unsupported', result['answer'])

    async def test_search_first_configuration(self):
        session = Session()
        @asynccontextmanager
        async def connection(*args): yield session
        config = {'initial_search': {'tool': 'lookup', 'question_argument': 'query'}}
        model = Model([plan('answer'), {'supported': True, 'answer': 'Tokyo'}])
        with patch.object(client, 'connect', connection), patch.object(client, 'load_servers', return_value={'test': config}):
            result = await client.ask_legacy('test', 'capital', model_client=model)
        self.assertEqual(session.calls, [('lookup', {'query': 'capital'})])
        self.assertEqual(result['status'], 'answered')

    async def test_answer_excerpts_keep_relevant_long_paragraphs(self):
        text = ('unrelated ' * 200) + '\n\nThe documentation MCP URL is https://developers.openai.com/mcp.'
        selected = client.answer_evidence('documentation MCP URL', [{'tool': 'fetch', 'content': text}])
        self.assertIn('https://developers.openai.com/mcp', '\n'.join(selected[0]['excerpts']))
        self.assertTrue(all(len(excerpt) <= 1500 for excerpt in selected[0]['excerpts']))

    async def test_tool_budget_is_bounded(self):
        session = Session()
        @asynccontextmanager
        async def connection(*args): yield session
        model = Model([plan('call_tool', 'lookup'), {'query': 'repeat'}] * 4 + [{'supported': False, 'answer': ''}])
        with patch.object(client, 'connect', connection), patch.object(client, 'load_servers', return_value={'test': {}}):
            result = await client.ask_legacy('test', 'question', model_client=model)
        self.assertEqual(len(session.calls), 1)  # Duplicate calls are rejected before execution.
        self.assertEqual(result['status'], 'insufficient_evidence')

    async def test_oauth_token_storage_private_atomic_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            storage = FileTokenStorage(Path(temp) / 'oauth')
            self.assertIsNone(await storage.get_tokens())
            await storage.set_tokens(OAuthToken(access_token='fixture', refresh_token='refresh'))
            self.assertEqual((await storage.get_tokens()).access_token, 'fixture')
            self.assertEqual(stat.S_IMODE((storage.directory / 'tokens.json').stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(storage.directory.stat().st_mode), 0o700)

    async def test_real_stdio_outbound(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temp:
            config = {'transport': 'stdio', 'command': str(root / '.venv/bin/python'),
                      'args': [str(root / 'main/src/tools/mcp_server.py'), '--memory-path', temp]}
            async with client.connect(config, 'fixture') as session:
                tools = await client.catalog(session, {})
                result = await client.call_read_tool(session, tools, 'calculate', {'expression': '6*7'})
                self.assertEqual(result['content']['value'], 42)


class ConfigTests(unittest.TestCase):
    def test_registry_defaults_and_credential_validation(self):
        servers = client.load_servers()
        self.assertEqual(servers['openai']['url'], 'https://developers.openai.com/mcp')
        self.assertEqual(servers['jira']['context']['project_key'], 'SPD')
        for config in [
            {'transport': 'streamable-http', 'url': 'http://example.com/mcp'},
            {'transport': 'streamable-http', 'url': 'https://secret:password@example.com/mcp'},
            {'transport': 'streamable-http', 'url': 'https://example.com/mcp', 'auth': {'type': 'bearer', 'token': 'secret'}}]:
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'config.json'
                path.write_text(json.dumps({'servers': {'test': config}}))
                with self.assertRaises(ValueError): client.load_servers(path)


if __name__ == '__main__': unittest.main()
