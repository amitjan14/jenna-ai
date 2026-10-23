"""Failure-injection checks for evidence repair and optional answer summaries."""
import json
import unittest
from unittest.mock import Mock, patch

from main.src.engineering.runtime import RequestCancelled, DeadlineExceeded


def response(value):
    return {'message': {'content': json.dumps(value)}}


class EvidenceResilienceTests(unittest.TestCase):
    def test_repair_transport_failure_preserves_original_abstention(self):
        from main.src.rag import rag_service as rag
        for error in [ConnectionError('offline'), TimeoutError('timeout')]:
            with self.subTest(error=type(error).__name__), \
                 patch.object(rag.get_client(), 'chat', side_effect=[{'message': {'content': '{'}}, error]):
                result = rag.generate_document_answer('What skills?', [{'text': 'Python.'}])
            self.assertFalse(result['answerable'])
            self.assertEqual(result['status'], 'invalid_response')

    def test_repair_respects_cancellation_and_deadline(self):
        from main.src.rag import rag_service as rag
        for error in [RequestCancelled('cancelled'), DeadlineExceeded('deadline')]:
            with self.subTest(error=type(error).__name__), \
                 patch.object(rag.get_client(), 'chat', side_effect=[{'message': {'content': '{'}}, error]):
                with self.assertRaises(type(error)):
                    rag.generate_document_answer('What skills?', [{'text': 'Python.'}])

    def test_optional_summary_transport_failure_keeps_verified_answer(self):
        from main.src.agent.conversation import natural_summary
        original = {'status': 'passages_verified', 'answer': 'Python.',
                    'support': [{'source_id': 0, 'quote': 'Python.'}],
                    'results': [{'filename': 'resume.pdf', 'text': 'Python.'}]}
        for error in [ConnectionError('offline'), TimeoutError('timeout')]:
            client = Mock()
            client.chat.side_effect = error
            with self.subTest(error=type(error).__name__):
                self.assertEqual(natural_summary('What skills?', original, client), original)

    def test_optional_summary_never_swallows_cancellation(self):
        from main.src.agent.conversation import natural_summary
        original = {'status': 'passages_verified', 'answer': 'Python.',
                    'support': [{'source_id': 0, 'quote': 'Python.'}],
                    'results': [{'filename': 'resume.pdf', 'text': 'Python.'}]}
        for error in [RequestCancelled('cancelled'), DeadlineExceeded('deadline')]:
            client = Mock()
            client.chat.side_effect = error
            with self.subTest(error=type(error).__name__), self.assertRaises(type(error)):
                natural_summary('What skills?', original, client)

    def test_numbered_repair_cannot_answer_only_one_required_part(self):
        from main.src.rag import rag_service as rag
        draft = response({'parts': [
            {'part_id': 0, 'answerable': True, 'support': [0]},
            {'part_id': 1, 'answerable': False, 'support': []},
        ]})
        with patch.object(rag.get_client(), 'chat', return_value=draft):
            result = rag.generate_document_answer('What languages and salary?', [{'text': 'Python.'}],
                required_parts=['What languages?', 'What salary?'], _selection_feedback={'reason': 'repair'})
        self.assertEqual(result['status'], 'insufficient_evidence')
        self.assertFalse(result['answerable'])

    def test_repair_reports_confirmed_missing_part_instead_of_original_format_error(self):
        from main.src.rag import rag_service as rag
        malformed = response({'parts': [
            {'part_id': 0, 'answerable': True, 'support': []},
            {'part_id': 1, 'answerable': False, 'support': []}]})
        repaired = response({'parts': [
            {'part_id': 0, 'answerable': True, 'support': [0]},
            {'part_id': 1, 'answerable': False, 'support': []}]})
        with patch.object(rag.get_client(), 'chat', side_effect=[malformed, repaired]):
            result = rag.generate_document_answer('Languages and salary?', [{'text': 'Python.'}],
                required_parts=['What languages?', 'What salary?'])
        self.assertEqual(result['status'], 'insufficient_evidence')
        self.assertIn('every required question part', result['rejection_reason'])
        self.assertFalse(result['answerable'])

    def test_verifier_must_use_booleans_and_complete_every_part(self):
        from main.src.rag import rag_service as rag
        for supported, complete in [('true', True), (True, 'true'), (True, False), (False, True)]:
            verdict = response({'supported': supported, 'complete': complete, 'reason': 'Synthetic verdict'})
            with self.subTest(supported=supported, complete=complete), \
                 patch.object(rag.get_client(), 'chat', return_value=verdict):
                result = rag.verify_document_answer('What skills?', 'Python.', [{'source_id': 0, 'quote': 'Python.'}])
            self.assertFalse(result['supported'] and result['complete'])


if __name__ == '__main__':
    unittest.main()
