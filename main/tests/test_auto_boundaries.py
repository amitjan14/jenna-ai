"""Source-boundary regressions with intentionally incorrect model routing."""
import unittest
from unittest.mock import patch

from main.src.agent import assistant_service as assistant
from main.src.rag.context import active_document_filter, active_source_request
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

    def test_named_document_subject_cannot_be_replaced_with_full_document(self):
        question = 'what does pale green stars say?'
        candidate = planned('What is the full text of the document named Test Pdf 2?',
                            connection='local', mode='Documents')
        result = assistant.plan_request(question, servers=SERVERS,
                                        model_client=Model(candidate))
        self.assertEqual(result['question'], question)
        self.assertEqual(result['state']['goal'], question)

    def test_filename_stem_scopes_retrieval_without_a_sidebar_filter(self):
        filenames = {'Test PDF.pdf': {}, 'Test Pdf 2.pdf': {}}
        question = 'what does pale green stars say in Test Pdf 2'
        observed = []
        def local(*args, **kwargs):
            observed.append(active_document_filter.get())
            return {'answer': 'Missing evidence.', 'status': 'insufficient_evidence'}
        with patch.object(assistant, 'load_document_records', return_value=filenames), \
             patch.object(assistant, 'load_servers', return_value=SERVERS), \
             patch.object(assistant, 'run_agent', side_effect=local):
            assistant.run_assistant(question, model_client=Model(planned(
                question, connection='local', mode='Documents')))
        self.assertEqual(observed, [{'filename': 'Test Pdf 2.pdf'}])
        self.assertIsNone(active_document_filter.get())

    def test_filename_scope_does_not_collapse_comparisons_or_partial_names(self):
        names = ['Test PDF.pdf', 'Test Pdf 2.pdf', 'Test Pdf 20.pdf', 'Notes.pdf']
        for question, expected in [
            ('Read Test Pdf 2.', {'filename': 'Test Pdf 2.pdf'}),
            ('Read Test Pdf 20.pdf', {'filename': 'Test Pdf 20.pdf'}),
            ('Compare Test PDF with Test Pdf 2', None),
            ('Read my notes', None),
            ('Read Notes.pdf', {'filename': 'Notes.pdf'}),
            ('Read https://example.com/Test%20Pdf%202.pdf', None),
        ]:
            with self.subTest(question=question):
                self.assertEqual(assistant.referenced_document_filter(question, names), expected)

    def test_explicit_caller_filter_wins_over_inferred_filename(self):
        observed = []
        def local(*args, **kwargs):
            observed.append(active_document_filter.get())
            return {'answer': 'Missing evidence.', 'status': 'insufficient_evidence'}
        with patch.object(assistant, 'load_document_records', return_value={'Test Pdf 2.pdf': {}}), \
             patch.object(assistant, 'load_servers', return_value=SERVERS), \
             patch.object(assistant, 'run_agent', side_effect=local):
            assistant.run_assistant('Read Test Pdf 2', filters={'filename': 'other.pdf'},
                model_client=Model(planned('Read Test Pdf 2', connection='local', mode='Documents')))
        self.assertEqual(observed, [{'filename': 'other.pdf'}])

    def test_image_and_note_references_are_contextual_followups(self):
        from main.src.agent.agent_utils import needs_conversation_context
        for question in ["what does that image's data", 'Read that note', 'What is on this page?']:
            with self.subTest(question=question):
                self.assertTrue(needs_conversation_context(question))

    def test_original_source_request_survives_followup_rewriting(self):
        question = "what does that image's data"
        observed = []
        def local(*args, **kwargs):
            observed.append((args[0], active_source_request.get()))
            return {'answer': 'Missing evidence.', 'status': 'insufficient_evidence'}
        with patch.object(assistant, 'load_servers', return_value=SERVERS), \
             patch.object(assistant, 'run_agent', side_effect=local):
            assistant.run_assistant(question, model_client=Model(planned(
                'Text associated with the signed image.', connection='local', mode='Documents')))
        self.assertEqual(observed[0][1], question)
        self.assertIn('Text associated with the signed image.', observed[0][0])
        self.assertIn('including the message body', observed[0][0])
        self.assertIsNone(active_source_request.get())

    def test_source_override_preserves_subject_after_incorrect_interpretation(self):
        question = 'What does the blue box say?'
        candidate = planned('Read the entire document.', connection='local')
        with patch.object(assistant, 'load_servers', return_value=SERVERS), \
             patch.object(assistant, 'run_agent', return_value={
                 'answer': 'Not enough evidence.', 'status': 'insufficient_evidence'}) as local:
            result = assistant.run_assistant(question, filters={'filename': 'notes.pdf'},
                                             model_client=Model(candidate))
        self.assertEqual(local.call_args.args[0], question)
        self.assertEqual(result['interpreted_question'], question)

    def test_document_pronoun_followup_can_still_resolve_its_subject(self):
        for question in ['What did he write?', 'What does her note say?']:
            with self.subTest(question=question):
                resolved = 'What did Morgan write?'
                result = assistant.plan_request(question, servers=SERVERS,
                    model_client=Model(planned(resolved, connection='local', mode='Documents')))
                self.assertEqual(result['question'], resolved)

    def test_new_named_subject_overrides_previous_document_question(self):
        question = 'What does the amber label say?'
        history = [{'role': 'user', 'content': 'Read the blue card.'},
                   {'role': 'assistant', 'content': 'Blue card text.',
                    'connection': 'local', 'source_mode': 'Documents'}]
        result = assistant.plan_request(question, history=history, servers=SERVERS,
            model_client=Model(planned('Read the blue card.', connection='local', mode='Documents')))
        self.assertEqual(result['question'], question)

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
