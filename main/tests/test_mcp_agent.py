import json
import unittest
from unittest.mock import patch
from mcp.types import Tool
from main.src.integrations.mcp_agent import run, bounded, pending_pages
from main.src.integrations.mcp_client import jira_identifiers_supported
from main.src.integrations.jira_workflow import prepare_due_date_read, due_date_facts

TOOL = Tool(name='lookup', input_schema={'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query'], 'additionalProperties': False})


def tool_message(name='lookup', arguments=None):
    return {'message': {'content': '', 'tool_calls': [{'function': {'name': name, 'arguments': arguments or {'query': 'capital'}}}]}}


def answer(text='Tokyo'):
    return {'message': {'content': text}}


class Model:
    def __init__(self, messages): self.messages = iter(messages); self.requests = []
    def chat(self, **kwargs): self.requests.append(kwargs); return next(self.messages)


class AgentTests(unittest.IsolatedAsyncioTestCase):
    def test_due_date_reads_request_explicit_field_and_preserve_other_fields(self):
        tool = Tool(name='getJiraIssue', input_schema={'type': 'object', 'properties': {
            'view': {'type': 'string', 'enum': ['compact', 'evidence', 'full']},
            'fields': {'type': 'array'}}})
        original = {'issueIdOrKey': 'LAB-73', 'view': 'evidence', 'fields': ['customfield_42']}
        result = prepare_due_date_read('When is LAB-73 due?', tool, original)
        self.assertEqual(result['view'], 'full')
        self.assertEqual(result['fields'], ['customfield_42', 'duedate'])
        self.assertEqual(original['fields'], ['customfield_42'])
        self.assertEqual(prepare_due_date_read('Who owns LAB-73?', tool, original), original)

    def test_due_date_observations_distinguish_omission_null_and_value(self):
        def evidence(fields, key='LAB-73'):
            return {'tool': 'getJiraIssue', 'is_error': False, 'content': [
                {'type': 'text', 'text': {'data': {'key': key, 'fields': fields}}}]}
        missing, null, dated = evidence({}), evidence({'duedate': None}), evidence({'duedate': '2026-10-23'})
        self.assertEqual(due_date_facts([missing])[0], {'issue': 'LAB-73', 'field': 'duedate', 'returned': False})
        self.assertIsNone(due_date_facts([null])[0]['value'])
        self.assertTrue(due_date_facts([null])[0]['returned'])
        self.assertEqual(due_date_facts([dated, missing])[0]['value'], '2026-10-23')
        self.assertEqual(due_date_facts([{**dated, 'is_error': True}]), [])

    async def test_current_verification_excludes_previous_assistant_verdict(self):
        self.executions = []
        old = 'The previous ticket had no due date and only closed sprints.'
        model = Model([tool_message(), answer(), answer(json.dumps({
            'supported': True, 'complete': True, 'reason': ''}))])
        await run('capital?', {}, 'test', [TOOL], self.execute, model,
                  history=[{'role': 'user', 'content': 'Earlier question'},
                           {'role': 'assistant', 'content': old}])
        verification = json.loads(model.requests[-1]['messages'][-1]['content'])
        self.assertNotIn(old, verification['conversation'])
        self.assertIn('Earlier question', verification['conversation'])

    async def test_jira_due_date_model_call_is_enriched_before_execution(self):
        tool = Tool(name='getJiraIssue', input_schema={'type': 'object', 'properties': {
            'issueIdOrKey': {'type': 'string'}, 'view': {'type': 'string'},
            'fields': {'type': 'array'}}, 'required': ['issueIdOrKey']})
        seen = []
        async def execute(name, args):
            seen.append(args)
            return {'tool': name, 'arguments': args, 'is_error': False,
                    'content': {'key': 'LAB-73', 'fields': {'duedate': '2026-10-23'}}}
        model = Model([tool_message('getJiraIssue', {'issueIdOrKey': 'LAB-73', 'view': 'evidence'}),
                       answer('The due date is 23 October 2026.'),
                       answer(json.dumps({'supported': True, 'complete': True, 'reason': ''}))])
        result = await run('What is the due date of LAB-73?', {}, 'jira', [tool], execute, model)
        self.assertIn('duedate', seen[0]['fields'])
        self.assertEqual(seen[0]['view'], 'full')
        payload = json.loads(model.requests[-1]['messages'][-1]['content'])
        self.assertEqual(payload['requested_field_facts'][0]['value'], '2026-10-23')
        self.assertEqual(result['status'], 'answered')

    async def test_omitted_due_date_cannot_be_reported_as_unset(self):
        tool = Tool(name='getJiraIssue', input_schema={'type': 'object', 'properties': {
            'issueIdOrKey': {'type': 'string'}, 'view': {'type': 'string'},
            'fields': {'type': 'array'}}, 'required': ['issueIdOrKey']})
        async def execute(name, args):
            return {'tool': name, 'arguments': args, 'is_error': False,
                    'content': {'key': 'LAB-73', 'fields': {'summary': 'Example'}}}
        model = Model([tool_message('getJiraIssue', {'issueIdOrKey': 'LAB-73'}),
                       answer('The due date is not set (null).')])
        result = await run('What is the due date of LAB-73?', {}, 'jira', [tool], execute, model)
        self.assertEqual(result['status'], 'partial_answer')
        self.assertIn('did not return', result['answer'])
        self.assertNotIn('null', result['answer'])
        self.assertNotIn('not set', result['answer'])

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
