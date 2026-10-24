"""Source locations are metadata, not words that may be invented inside quotations."""
import json
import unittest
from unittest.mock import patch
from main.src.rag.citations import add_source_details, requests_source_details
from main.src.rag.context import active_source_request


class SourceCitationTests(unittest.TestCase):
    question = 'Use only 02 Scanned Printed Notes.pdf. What is the validation accuracy? Include the supporting quotation and page number.'
    quote = 'Validation accuracy: 87 percent.'

    def source(self, **updates):
        return {'filename': '02 Scanned Printed Notes.pdf', 'page': 1,
                'text': self.quote, **updates}

    def test_locations_and_quotes_are_rendered_without_modifying_evidence(self):
        support = [{'source_id': 0, 'quote': self.quote}]
        answer = add_source_details(self.question, self.quote, support, [self.source()])
        self.assertIn('> ' + self.quote, answer)
        self.assertIn('02 Scanned Printed Notes.pdf, page 1 [1]', answer)
        self.assertEqual(answer.count(self.quote), 1)
        self.assertEqual(support[0]['quote'], self.quote)
        self.assertEqual(self.source()['text'], self.quote)

    def test_each_quote_keeps_its_own_source_and_page(self):
        support = [{'source_id': 0, 'quote': 'Budget: 740.'}, {'source_id': 1, 'quote': 'Owner: Mira.'}]
        sources = [{'filename': 'one.pdf', 'page': 2}, {'filename': 'two.pdf', 'page': 7}]
        answer = add_source_details('Include supporting quotations and page numbers.', 'Facts', support, sources)
        self.assertIn('one.pdf, page 2 [1]', answer)
        self.assertIn('two.pdf, page 7 [2]', answer)
        self.assertNotIn('one.pdf, page 7', answer)

    def test_missing_page_is_not_invented_from_the_question(self):
        from main.src.rag import rag_service as rag
        support = [{'source_id': 0, 'quote': self.quote}]
        for invalid in [None, 0, True, '1']:
            with self.subTest(page=invalid), patch.object(rag, 'get_client') as model:
                verdict = rag.verify_document_answer('What accuracy? Include page number.', self.quote,
                                                     support, [self.source(page=invalid)])
                self.assertFalse(verdict['complete'])
                model.assert_not_called()

    def test_metadata_reaches_verifier_and_no_quote_is_rewritten(self):
        from main.src.rag import rag_service as rag
        selection = {'message': {'content': json.dumps({'parts': [{'part_id': 0, 'answerable': True,
                      'support': [{'source_id': 0, 'quote': self.quote}]}]})}}
        verdict = {'message': {'content': json.dumps({'supported': True, 'complete': True, 'reason': ''})}}
        with patch.object(rag.get_client(), 'chat', side_effect=[selection, verdict]) as model:
            result = rag.generate_document_answer(self.question, [self.source()])
        self.assertTrue(result['answerable'])
        self.assertIn('page 1', result['answer'])
        payload = json.loads(model.call_args.kwargs['messages'][-1]['content'])
        self.assertEqual(payload['source_contexts'][0]['page'], 1)
        self.assertEqual(payload['quotations'], [self.quote])
        self.assertIn('page 1', payload['answer'])

    def test_original_request_controls_citation_details_after_question_resolution(self):
        from main.src.rag import rag_service as rag
        selection = {'message': {'content': json.dumps({'parts': [{'part_id': 0, 'answerable': True,
                      'support': [{'source_id': 0, 'quote': self.quote}]}]})}}
        verdict = {'message': {'content': json.dumps({'supported': True, 'complete': True, 'reason': ''})}}
        token = active_source_request.set(self.question)
        try:
            with patch.object(rag.get_client(), 'chat', side_effect=[selection, verdict]):
                result = rag.generate_document_answer('What is the validation accuracy?', [self.source()])
        finally:
            active_source_request.reset(token)
        self.assertIn('page 1', result['answer'])

    def test_source_details_do_not_override_failed_fact_verification(self):
        from main.src.rag import rag_service as rag
        selection = {'message': {'content': json.dumps({'parts': [{'part_id': 0, 'answerable': True,
                      'support': [{'source_id': 0, 'quote': self.quote}]}]})}}
        verdict = {'message': {'content': json.dumps({'supported': False, 'complete': False, 'reason': 'Wrong field'})}}
        with patch.object(rag.get_client(), 'chat', side_effect=[selection, verdict]):
            result = rag.generate_document_answer(self.question, [self.source()])
        self.assertFalse(result['answerable'])
        self.assertEqual(result['support'], [])

    def test_optional_summary_cannot_remove_requested_exact_source_details(self):
        from main.src.agent import assistant_service as assistant
        support = [{'source_id': 0, 'quote': self.quote}]
        answer = add_source_details(self.question, self.quote, support, [self.source()])
        plan = {'connection': 'local', 'mode': 'Documents', 'question': self.question,
                'intent': 'task', 'clarification': '', 'memory_key': '', 'memory_value': '',
                'state': {'goal': '', 'constraints': [], 'references': []}}
        result = {'answer': answer, 'status': 'passages_verified', 'support': support,
                  'results': [self.source()], 'tools_used': ['search_documents']}
        with patch.object(assistant, 'plan_request', return_value=plan), \
             patch.object(assistant, 'run_agent', return_value=result), \
             patch.object(assistant, 'load_servers', return_value={}), \
             patch.object(assistant, 'load_document_records', return_value={}), \
             patch.object(assistant, 'save_state'), \
             patch.object(assistant, 'natural_summary') as summarize:
            final = assistant.run_assistant(self.question)
        summarize.assert_not_called()
        self.assertEqual(final['answer'], answer)

    def test_ordinary_requests_keep_their_existing_answer(self):
        self.assertFalse(requests_source_details('What is the validation accuracy?'))
        self.assertEqual(add_source_details('What accuracy?', '87 percent.', [], []), '87 percent.')
