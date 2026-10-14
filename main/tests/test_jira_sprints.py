import unittest
from main.src.integrations.jira_workflow import active_sprints, active_sprint_request, issue_details

CONFIG = {'context': {'site_url': 'https://example.atlassian.net', 'project_key': 'DEMO', 'timezone': 'Asia/Calcutta'}}
SPRINT = {'id': 80, 'name': 'Demo Sprint 8', 'state': 'active',
          'startDate': '2026-10-07T06:50:00Z', 'endDate': '2026-10-20T13:30:00Z'}


class SprintTests(unittest.IsolatedAsyncioTestCase):
    def reader(self, boards=None, sprints=None, fail=None, partial=False):
        self.calls = []
        async def execute(name, args):
            self.calls.append((name, args))
            data = {'getAccessibleAtlassianResources': {'resources': [{'cloudId': 'real-cloud', 'url': CONFIG['context']['site_url']}]},
                    'listJiraBoards': {'values': boards if boards is not None else [{'id': 4, 'name': 'Demo', 'type': 'scrum'}], 'isLast': not partial},
                    'listJiraBoardSprints': {'values': [SPRINT] if sprints is None else sprints, 'isLast': True},
                    'getJiraIssue': {'key': 'DEMO-12', 'fields': {'summary': 'Example', 'status': {'name': 'In Progress'}, 'duedate': '2026-10-16'}}}[name]
            return {'tool': name, 'arguments': args, 'is_error': name == fail,
                    'content': [{'type': 'text', 'text': {'data': data}}]}
        return execute

    async def test_typo_query_discovers_board_before_active_sprint(self):
        result = await active_sprints('what is the current active sprimt ?', CONFIG, self.reader())
        self.assertEqual(result['status'], 'answered')
        self.assertIn('Demo Sprint 8', result['answer'])
        self.assertIn('20 October 2026, 19:00 IST', result['answer'])
        self.assertEqual([name for name, _ in self.calls], ['getAccessibleAtlassianResources', 'listJiraBoards', 'listJiraBoardSprints'])
        self.assertEqual(self.calls[1][1], {'cloudId': 'real-cloud', 'maxResults': 20, 'projectKeyOrId': 'DEMO'})
        self.assertEqual(self.calls[2][1]['boardId'], 4)
        self.assertEqual(self.calls[2][1]['state'], 'active')
        self.assertNotIn('getJiraBoardIssueData', [name for name, _ in self.calls])

    async def test_multiple_boards_and_duplicate_sprints(self):
        boards = [{'id': 4, 'name': 'A', 'type': 'scrum'}, {'id': 5, 'name': 'B', 'type': 'scrum'}]
        result = await active_sprints('current sprint', CONFIG, self.reader(boards=boards))
        self.assertEqual(len(result['jira_sprints']), 1)
        self.assertIn('A, B', result['answer'])

    async def test_no_active_sprint_vs_failed_or_incomplete_reads(self):
        result = await active_sprints('active sprint', CONFIG, self.reader(sprints=[]))
        self.assertIn('No active sprint', result['answer'])
        self.assertEqual(result['status'], 'answered')
        for execute in [self.reader(fail='listJiraBoardSprints'), self.reader(sprints=[], partial=True),
                        self.reader(sprints=[{**SPRINT, 'state': 'closed'}])]:
            result = await active_sprints('active sprint', CONFIG, execute)
            self.assertEqual(result['status'], 'insufficient_evidence')
            self.assertNotIn('No active sprint', result['answer'])

    async def test_kanban_and_unknown_board(self):
        result = await active_sprints('active sprint', CONFIG, self.reader(boards=[{'id': 3, 'type': 'kanban'}]))
        self.assertIn('No active sprint', result['answer'])
        self.assertEqual(len(self.calls), 2)
        result = await active_sprints('active sprint for board 99', CONFIG, self.reader())
        self.assertEqual(result['status'], 'insufficient_evidence')
        self.assertEqual(len(self.calls), 2)

    async def test_sprint_intent_excludes_issue_and_future_questions(self):
        for text in ['what is current active sprimt?', 'what sprint are we in?', 'when does the current sprint end?']:
            self.assertTrue(active_sprint_request(text))
        for text in ['list future sprints', 'what issues are assigned in the current sprint?', 'my current work']:
            self.assertFalse(active_sprint_request(text))
        self.assertIsNone(await active_sprints('future sprints', CONFIG, self.reader()))

    async def test_specific_issue_gets_full_due_fields_without_board_scan(self):
        result = await issue_details('when is DEMO-12 due?', CONFIG, self.reader())
        self.assertEqual(result['status'], 'answered')
        self.assertIn('16 October 2026', result['answer'])
        self.assertEqual([name for name, _ in self.calls], ['getAccessibleAtlassianResources', 'getJiraIssue'])
        self.assertEqual(self.calls[1][1]['view'], 'full')
        self.assertIn('duedate', self.calls[1][1]['fields'])
        self.assertIsNone(await issue_details('compare DEMO-12 and DEMO-13', CONFIG, self.reader()))


if __name__ == '__main__': unittest.main()
