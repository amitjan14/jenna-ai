"""Source-boundary regressions with intentionally incorrect model routing."""
import unittest
from unittest.mock import patch

from main.src.agent import assistant_service as assistant
from main.src.rag.context import active_document_filter
from main.tests.test_assistant import Model, SERVERS, planned


class AutoBoundaryTests(unittest.TestCase):
    def setUp(self):
        for target, value in [('load_document_records', {'Resume - Morgan Ellis.pdf': {}}),
                              ('list_notes', {})]:
            mock = patch.object(assistant, target, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def test_explicit_web_search_is_not_overridden_by_matching_filename(self):
        question = 'Search the web for Morgan Ellis programming tutorials'
        result = assistant.plan_request(question, servers=SERVERS,
            model_client=Model(planned(question, connection='local', mode='Web')))
        self.assertEqual((result['connection'], result['mode']), ('local', 'Web'))

    def test_public_pdf_url_is_not_treated_as_an_uploaded_filename(self):
        question = 'Search the web for https://example.com/programming-guide.pdf'
        result = assistant.plan_request(question, servers=SERVERS,
            model_client=Model(planned(question, connection='local', mode='Web')))
        self.assertEqual((result['connection'], result['mode']), ('local', 'Web'))

    def test_unverified_document_search_never_falls_through_to_external_tools(self):
        from main.src.agent import agent_service as agent
        question = 'What programming skills does Morgan have?'
        for status in ['invalid_response', 'invalid_evidence', 'no_context', 'insufficient_evidence', 'retrieval_unavailable']:
            answer = {'answerable': False, 'answer': '', 'support': [], 'status': status}
            with self.subTest(status=status), \
                 patch.object(assistant, 'load_servers', return_value=SERVERS), \
                 patch.object(assistant, 'run_mcp_question') as remote, \
                 patch.object(agent, 'resolve_followup', return_value={'status': 'standalone', 'question': question, 'clarification': ''}), \
                 patch.object(agent, 'decide_action', return_value={'action': 'search_documents', 'expression': ''}), \
                 patch.object(agent, 'search_and_answer', return_value=([], answer)), \
                 patch.object(agent, 'rewrite_search_query', return_value=question), \
                 patch('main.src.tools.web_tools.search_web') as web:
                result = assistant.run_assistant(question, model_client=Model(planned(question)))
            remote.assert_not_called()
            web.assert_not_called()
            self.assertEqual(result['status'], status)
            self.assertEqual(result['source_mode'], 'Documents')

    def test_uploaded_or_attached_file_scope_overrides_jira_topic(self):
        for prefix in ['Use the uploaded file only:', 'According to the attached PDF,',
                       'In the attached resume,', 'From the uploaded résumé,',
                       'Based on my CV,', 'I uploaded a file.', 'What does this file say?',
                       'From my handwritten notes,', 'According to computerized notes,',
                       'In the uploaded typed notes,', 'Use the uploaded handwritten notes only:']:
            question = prefix + ' explain Jira experience'
            with self.subTest(prefix=prefix):
                result = assistant.plan_request(question, servers=SERVERS,
                    model_client=Model(planned(question)))
                self.assertEqual((result['connection'], result['mode']), ('local', 'Documents'))

    def test_user_can_forbid_jira_without_naming_a_file(self):
        for prefix in ['Do not use Jira.', "Don't search Jira.", 'Without Jira,']:
            question = prefix + ' What programming skills does Morgan have?'
            with self.subTest(prefix=prefix):
                result = assistant.plan_request(question, servers=SERVERS,
                    model_client=Model(planned(question)))
                self.assertEqual((result['connection'], result['mode']), ('local', 'Documents'))

    def test_fresh_profile_question_does_not_inherit_old_jira_intent(self):
        history = [{'role': 'user', 'content': 'Show OPS-42'},
                   {'role': 'assistant', 'content': 'Morgan owns OPS-42.', 'connection': 'jira'}]
        question = 'What programming skills does Morgan have with it?'
        result = assistant.plan_request(question, history=history, servers=SERVERS,
            model_client=Model(planned(question)))
        self.assertEqual((result['connection'], result['mode']), ('local', 'Documents'))

    def test_current_work_routes_to_jira_even_if_model_chooses_resume(self):
        question = 'What is Morgan working on?'
        result = assistant.plan_request(question, servers=SERVERS,
            model_client=Model(planned(question, connection='local', mode='Documents')))
        self.assertEqual((result['connection'], result['mode']), ('jira', 'Auto'))

    def test_assigned_tasks_are_jira_intent_without_ticket_keys(self):
        question = 'Show the tasks assigned to Morgan'
        result = assistant.plan_request(question, servers=SERVERS,
            model_client=Model(planned(question)))
        self.assertEqual(result['connection'], 'jira')

    def test_new_subject_after_jira_does_not_reuse_stale_references(self):
        history = [{'role': 'user', 'content': 'Show OPS-42'},
                   {'role': 'assistant', 'content': 'In progress.', 'connection': 'jira'},
                   {'role': 'user', 'content': 'Let us discuss resumes instead.'},
                   {'role': 'assistant', 'content': 'What would you like to know?',
                    'connection': 'local', 'source_mode': 'Auto'}]
        result = assistant.plan_request('And what skills does Morgan have?', history=history,
            servers=SERVERS, model_client=Model(planned('What skills does Morgan have?')))
        self.assertEqual((result['connection'], result['mode']), ('local', 'Documents'))

    def test_pdf_filter_is_reset_after_backend_failure(self):
        with patch.object(assistant, 'load_servers', return_value=SERVERS), \
             patch.object(assistant, 'run_agent', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic failure'):
                assistant.run_assistant('Morgan skills', filters={'filename': 'a.pdf'},
                    model_client=Model(planned('Morgan skills')))
        self.assertIsNone(active_document_filter.get())

    def test_private_scopes_block_remote_dispatch_for_every_search_mode(self):
        for mode in ['Auto', 'Documents', 'Web', 'Documents + Web']:
            question = 'From my PDF, explain Jira workflows'
            with self.subTest(mode=mode), \
                 patch.object(assistant, 'load_servers', return_value=SERVERS), \
                 patch.object(assistant, 'run_mcp_question') as remote, \
                 patch.object(assistant, 'run_agent', return_value={'status': 'no_context', 'answer': 'No evidence.'}) as local:
                result = assistant.run_assistant(question, mode=mode,
                    model_client=Model(planned(question)))
            remote.assert_not_called()
            self.assertEqual(result['connection'], 'local')
            self.assertEqual(local.call_args.kwargs['search_mode'], 'Documents')


if __name__ == '__main__':
    unittest.main()
