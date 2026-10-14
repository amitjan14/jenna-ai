import json
import unittest
from unittest.mock import patch
from mcp.types import Tool
from main.src.integrations.mcp_agent import run, bounded, pending_pages
from main.src.integrations.mcp_client import jira_identifiers_supported

TOOL = Tool(name='lookup', input_schema={'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query'], 'additionalProperties': False})


def tool_message(name='lookup', arguments=None):
    return {'message': {'content': '', 'tool_calls': [{'function': {'name': name, 'arguments': arguments or {'query': 'capital'}}}]}}


def answer(text='Tokyo'):
    return {'message': {'content': text}}


class Model:
    def __init__(self, messages): self.messages = iter(messages); self.requests = []
    def chat(self, **kwargs): self.requests.append(kwargs); return next(self.messages)


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def execute(self, name, arguments):
        self.executions.append((name, arguments))
        if name != 'lookup' or set(arguments) != {'query'}: raise ValueError('Invalid tool or arguments')
        return {'tool': name, 'arguments': arguments, 'is_error': False, 'content': {'capital': 'Tokyo'}}

    async def test_native_tools_and_complete_schemas_are_used(self):
        self.executions = []
        model = Model([tool_message(), answer(), answer(json.dumps({'supported': True, 'complete': True, 'reason': ''}))])
        result = await run('capital?', {}, 'test', [TOOL], self.execute, model)
        self.assertEqual(result['answer'], 'Tokyo')
        self.assertEqual(self.executions, [('lookup', {'query': 'capital'})])
        self.assertEqual(model.requests[0]['tools'][0]['function']['parameters'], TOOL.input_schema)
        self.assertEqual(model.requests[1]['messages'][-1]['role'], 'tool')
        self.assertEqual(result['metrics']['llm_calls'], 3)

    async def test_tool_error_is_fed_back_for_recovery(self):
        self.executions = []
        model = Model([tool_message('delete'), tool_message(), answer(), answer(json.dumps({'supported': True, 'complete': True, 'reason': ''}))])
        result = await run('capital?', {}, 'test', [TOOL], self.execute, model)
        self.assertTrue(result['mcp_evidence'][0]['is_error'])
        self.assertEqual(len(self.executions), 1)
        self.assertEqual(result['status'], 'answered')

    async def test_fabricated_answer_is_rejected(self):
        self.executions = []
        model = Model([tool_message(), answer('Paris'), answer(json.dumps({'supported': False, 'complete': True, 'reason': 'Result says Tokyo'})),
            answer(json.dumps({'answer': 'Paris'})), answer(json.dumps({'supported': False, 'complete': True, 'reason': 'Result says Tokyo'}))])
        result = await run('capital?', {}, 'test', [TOOL], self.execute, model)
        self.assertEqual(result['status'], 'insufficient_evidence')
        self.assertNotIn('Paris', result['answer'])

    async def test_supported_repair_is_independently_verified(self):
        self.executions = []
        model = Model([tool_message(), answer('Paris'),
            answer(json.dumps({'supported': False, 'complete': True, 'reason': 'Evidence says Tokyo'})),
            answer(json.dumps({'answer': 'Tokyo'})),
            answer(json.dumps({'supported': True, 'complete': True, 'reason': ''}))])
        result = await run('whats the captial?', {}, 'test', [TOOL], self.execute, model)
        self.assertEqual(result['answer'], 'Tokyo')
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['metrics']['llm_calls'], 5)

    async def test_read_budget_and_duplicate_calls(self):
        self.executions = []
        model = Model([tool_message(), tool_message(), answer('Partial: Tokyo'), answer(json.dumps({'supported': True, 'complete': False, 'reason': 'More evidence needed'}))])
        with patch.dict('os.environ', {'JENNA_MCP_MAX_STEPS': '2'}):
            result = await run('capital?', {}, 'test', [TOOL], self.execute, model)
        self.assertEqual(len(self.executions), 1)
        self.assertTrue(result['mcp_evidence'][1]['is_error'])
        self.assertEqual(result['status'], 'partial_answer')

    async def test_wrong_identifier_type_is_rejected(self):
        self.assertFalse(jira_identifiers_supported({'boardId': 'SPD-123'}, [], {}, 'history of SPD-123'))
        self.assertFalse(jira_identifiers_supported({'sprintId': 'SPD-123'}, [], {}, 'history of SPD-123'))
        self.assertFalse(jira_identifiers_supported({'nextPageToken': 'null'}, [], {}, 'null'))

    async def test_answer_without_successful_reads_cannot_claim_facts(self):
        self.executions = []
        with patch.dict('os.environ', {'JENNA_MCP_MAX_STEPS': '1'}):
            result = await run('capital?', {}, 'test', [TOOL], self.execute, Model([answer('Paris')]))
        self.assertEqual(result['status'], 'insufficient_evidence')
        self.assertNotIn('Paris', result['answer'])

    async def test_followup_identifier_can_come_from_conversation(self):
        tool = Tool(name='read_issue', input_schema={'type': 'object', 'properties': {'issueIdOrKey': {'type': 'string'}}, 'required': ['issueIdOrKey']})
        recorded = []
        async def execute(name, args):
            recorded.append(args)
            return {'tool': name, 'arguments': args, 'is_error': False, 'content': {'owner': 'Taylor'}}
        model = Model([tool_message('read_issue', {'issueIdOrKey': 'LAB-73'}), answer('Taylor'),
                       answer(json.dumps({'supported': True, 'complete': True, 'reason': ''}))])
        result = await run('Who owns it?', {}, 'jira', [tool], execute, model, jira_identifiers_supported,
                           [{'role': 'user', 'content': 'Tell me about LAB-73'}])
        self.assertEqual(recorded, [{'issueIdOrKey': 'LAB-73'}])
        self.assertEqual(result['status'], 'answered')

    async def test_bounding_keeps_pagination_and_json_shape(self):
        value = bounded({'nextPageToken': 'real-token', 'values': ['x' * 7000] * 31})
        self.assertEqual(value['nextPageToken'], 'real-token')
        self.assertEqual(value['values'][-1]['_truncated_items'], 1)
        self.assertIn('Text truncated', value['values'][0])

    async def test_pagination_tracks_latest_page_for_the_same_query(self):
        first = {'tool': 'history', 'arguments': {'issue': 'LAB-73', 'startAt': 0, 'maxResults': 1},
                 'is_error': False, 'content': {'data': {'isLast': False}}}
        last = {**first, 'arguments': {'issue': 'LAB-73', 'startAt': 1, 'maxResults': 10},
                'content': {'data': {'isLast': True}}}
        self.assertEqual(pending_pages([first]), ['history'])
        self.assertEqual(pending_pages([first, last]), [])

    async def test_missing_tool_can_be_discovered_without_a_question_route(self):
        tools=[Tool(name='unrelated_'+str(i),description='Unrelated metadata',input_schema={'type':'object','properties':{}}) for i in range(9)]
        target=Tool(name='target',description='Fetch the hidden value',input_schema={'type':'object','properties':{}})
        tools.append(target);executed=[]
        async def execute(name,args):
            executed.append(name)
            return {'tool':name,'arguments':args,'is_error':False,'content':{'value':42}}
        model=Model([tool_message('discover_tools',{'query':'hidden value'}),tool_message('target',{}),answer('42'),
                     answer(json.dumps({'supported':True,'complete':True,'reason':''}))])
        result=await run('Help me please',{},'test',tools,execute,model)
        self.assertNotIn('target',[item['function']['name'] for item in model.requests[0]['tools']])
        self.assertEqual(executed,['target']);self.assertEqual(result['metrics']['mcp_reads'],1)
        self.assertEqual(result['answer'],'42')


if __name__ == '__main__': unittest.main()
