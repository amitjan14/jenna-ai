import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from main.src.tools.mcp_server import build_server

ROOT = Path(__file__).resolve().parents[2]


class MCPProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def connect(self, flags, check):
        with tempfile.TemporaryDirectory(prefix='jenna-mcp-test-') as memory:
            params = StdioServerParameters(command=sys.executable,
                args=[str(ROOT/'main/src/tools/mcp_server.py'),'--memory-path',memory,*flags])
            async with stdio_client(params) as streams:
                async with ClientSession(*streams,read_timeout_seconds=30) as session:
                    initialized = await session.initialize()
                    self.assertEqual(initialized.server_info.name,'Jenna AI')
                    await check(session)

    async def test_discovery_resources_prompt_and_arithmetic(self):
        async def check(session):
            tools = {t.name:t for t in (await session.list_tools()).tools}
            self.assertEqual(set(tools),{'server_status','calculate','list_documents','search_documents','ask_jenna'})
            self.assertTrue(tools['calculate'].annotations.read_only_hint)
            computed = await session.call_tool('calculate',{'expression':'sqrt(81) + 15 / 100 * 200'})
            self.assertFalse(computed.is_error)
            self.assertEqual(computed.structured_content['value'],39)
            invalid = await session.call_tool('calculate',{'expression':'__import__("os")'})
            self.assertTrue(invalid.is_error)
            catalog = await session.call_tool('list_documents',{})
            self.assertEqual(catalog.structured_content['documents'],[])
            resource = await session.read_resource('jenna://status')
            data=json.loads(resource.contents[0].text)
            self.assertFalse(data['capabilities']['memory'])
            self.assertFalse(data['capabilities']['web'])
            prompts = await session.list_prompts()
            self.assertIn('grounded_question',[p.name for p in prompts.prompts])
            prompt = await session.get_prompt('grounded_question',{'question':'What is RAG?'})
            self.assertIn('What is RAG?',prompt.messages[0].content.text)
            for question in ['remember: key = value','forget: key','recall: key','memories']:
                blocked = await session.call_tool('ask_jenna',{'question':question})
                self.assertTrue(blocked.is_error)
            blocked = await session.call_tool('ask_jenna',{'question':'What is RAG?','source_mode':'Web'})
            self.assertTrue(blocked.is_error)
            invalid_k = await session.call_tool('search_documents',{'question':'test','top_k':21})
            self.assertTrue(invalid_k.is_error)
        await self.connect([],check)

    async def test_enabled_memory_write_and_delete(self):
        async def check(session):
            names={t.name:t for t in (await session.list_tools()).tools}
            self.assertIn('remember_note',names)
            self.assertTrue(names['forget_note'].annotations.destructive_hint)
            result=await session.call_tool('remember_note',{'key':' Test key ','value':'blue'})
            self.assertFalse(result.is_error)
            recalled=await session.call_tool('recall_note',{'key':'test key'})
            self.assertEqual(recalled.structured_content['value'],'blue')
            forgotten=await session.call_tool('forget_note',{'key':'test key'})
            self.assertTrue(forgotten.structured_content['deleted'])
            missing=await session.call_tool('recall_note',{'key':'test key'})
            self.assertIsNone(missing.structured_content['value'])
        await self.connect(['--enable-memory','--allow-writes'],check)

    async def test_read_only_memory_cannot_write_via_agent(self):
        async def check(session):
            tools={t.name for t in (await session.list_tools()).tools}
            self.assertIn('recall_note',tools)
            self.assertNotIn('remember_note',tools)
            result=await session.call_tool('ask_jenna',{'question':'remember: color = blue'})
            self.assertTrue(result.is_error)
        await self.connect(['--enable-memory'],check)

    async def test_chat_tools_are_optional_and_validate_ids(self):
        async def check(session):
            tools={t.name for t in (await session.list_tools()).tools}
            self.assertIn('read_chat',tools)
            chats=await session.call_tool('list_chats',{})
            self.assertEqual(chats.structured_content['chats'],[])
            invalid=await session.call_tool('read_chat',{'chat_id':'../../private'})
            self.assertTrue(invalid.is_error)
            absent=await session.call_tool('read_chat',{'chat_id':'0'*32})
            self.assertTrue(absent.is_error)
        await self.connect(['--enable-chats'],check)


class MCPBackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_result_is_forwarded_without_persisting_chat(self):
        from main.src.agent import agent_service
        server=build_server()
        result={'answer':'Supported answer','status':'passages_verified','support':[],
                'tools_used':['search_documents'],'results':[]}
        with patch.object(agent_service,'run_agent',return_value=result) as call:
            # Server-level dispatch invokes the same registered handlers as the protocol.
            output=await server.call_tool('ask_jenna',{'question':'What is RAG?'})
            self.assertEqual(output.structured_content['answer'],'Supported answer')
            self.assertEqual(call.call_args.kwargs['search_mode'],'Documents')



if __name__=='__main__':unittest.main()
