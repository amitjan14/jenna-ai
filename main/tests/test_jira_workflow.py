import unittest
from main.src.integrations.jira_workflow import assigned_work, work_subject
from main.src.integrations.mcp_client import jira_identifiers_supported

CONFIG = {'context': {'site_url': 'https://example.atlassian.net', 'project_key': 'DEMO'}}
CURRENT = {'accountId': 'account-1', 'displayName': 'Alex Example'}


def issue(key='DEMO-1', due='2026-11-12', include_due=True, assignee='account-1'):
    fields = {'summary': 'Implement payments', 'status': {'name': 'In Progress',
              'statusCategory': {'name': 'In Progress'}}, 'assignee': {'accountId': assignee}}
    if include_due: fields['duedate'] = due
    return {'key': key, 'fields': fields}


class JiraWorkTests(unittest.IsolatedAsyncioTestCase):
    def reader(self, search, details=None, users=None, failure=None):
        self.calls = []
        async def execute(name, args):
            self.calls.append((name, args))
            data = {
                'getAccessibleAtlassianResources': {'resources': [{'url': CONFIG['context']['site_url'], 'cloudId': 'cloud-real'}]},
                'getJiraCurrentUser': CURRENT,
                'searchJiraIssuesUsingJql': search,
                'getJiraIssue': details or {},
                'lookupJiraAccountId': users or []}[name]
            return {'tool': name, 'arguments': args, 'is_error': name == failure,
                    'content': [{'type': 'text', 'text': {'data': data}}]}
        return execute

    async def test_real_identity_search_and_detail_due_date(self):
        execute = self.reader({'issues': [issue(include_due=False)], 'isLast': True}, issue())
        result = await assigned_work('what is alex example currently working on and when is the due date', CONFIG, execute)
        self.assertEqual(result['status'], 'answered')
        self.assertIn('12 November 2026', result['answer'])
        self.assertEqual([name for name, _ in self.calls], ['getAccessibleAtlassianResources',
            'getJiraCurrentUser', 'searchJiraIssuesUsingJql', 'getJiraIssue'])
        query = self.calls[2][1]
        self.assertIn('assignee = "account-1"', query['jql'])
        self.assertIn('statusCategory = "In Progress"', query['jql'])
        self.assertEqual(query['fields'], ['summary', 'status', 'duedate', 'assignee'])
        self.assertIn('/browse/DEMO-1', result['answer'])

    async def test_null_due_date_vs_omitted_due_date(self):
        result = await assigned_work('what am I working on?', CONFIG, self.reader({'issues': [issue(due=None)]}))
        self.assertIn('Not set', result['answer'])
        result = await assigned_work('what am I working on?', CONFIG, self.reader({'issues': [issue(include_due=False)]}, issue(include_due=False)))
        self.assertIn('Not returned by Jira', result['answer'])
        self.assertNotIn('Not set', result['answer'])

    async def test_no_active_work_and_search_failure(self):
        result = await assigned_work('my current issues', CONFIG, self.reader({'issues': []}))
        self.assertIn('No active issues', result['answer'])
        self.assertEqual(result['status'], 'answered')
        result = await assigned_work('my current work', CONFIG, self.reader({}, failure='searchJiraIssuesUsingJql'))
        self.assertEqual(result['status'], 'insufficient_evidence')
        self.assertNotIn('No active issues', result['answer'])

    async def test_other_user_not_current_user_and_ambiguity(self):
        target = {'accountId': 'account-2', 'displayName': 'Robin Example'}
        execute = self.reader({'issues': [issue(assignee='account-2')]}, users=[target])
        result = await assigned_work('what is robin example working on?', CONFIG, execute)
        self.assertIn('Robin Example', result['answer'])
        self.assertIn('"account-2"', self.calls[3][1]['jql'])
        execute = self.reader({'issues': []}, users=[target, {**target, 'accountId': 'account-3'}])
        result = await assigned_work('what is robin example working on?', CONFIG, execute)
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertNotIn('searchJiraIssuesUsingJql', [name for name, _ in self.calls])

    async def test_partial_results_and_wrong_assignee(self):
        result = await assigned_work('my tasks', CONFIG, self.reader({'issues': [issue()], 'isLast': False}))
        self.assertIn('more results', result['answer'])
        result = await assigned_work('my tasks', CONFIG, self.reader({'issues': [issue(assignee='wrong')]}))
        self.assertEqual(result['status'], 'insufficient_evidence')

    async def test_unrelated_question_uses_generic_planner(self):
        self.assertIsNone(await assigned_work('List Jira boards', CONFIG, self.reader({})))
        self.assertIsNone(work_subject('what is the capital of Japan?'))


class IdentifierTests(unittest.TestCase):
    def test_unknown_ids_blocked_known_ids_permitted(self):
        evidence = [{'tool': 'listJiraBoards', 'is_error': False, 'content': [{'type':'text', 'text': {'data': {'cloudId': 'real', 'boardId': 42}}}]}]
        self.assertFalse(jira_identifiers_supported({'cloudId': 'real', 'boardId': 1234567890}, evidence, CONFIG, 'List boards'))
        self.assertTrue(jira_identifiers_supported({'cloudId': 'real', 'boardId': 42}, evidence, CONFIG, 'List boards'))
        self.assertTrue(jira_identifiers_supported({'boardId': 13}, [], CONFIG, 'Show board 13'))
        self.assertFalse(jira_identifiers_supported({'boardId': 13}, [], CONFIG, 'Show board 130'))
        evidence[0]['is_error'] = True
        self.assertFalse(jira_identifiers_supported({'boardId': 42}, evidence, CONFIG, 'List boards'))


if __name__ == '__main__': unittest.main()
