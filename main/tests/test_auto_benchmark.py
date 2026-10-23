"""The benchmark must not reward crashes, refusals, or another person's resume."""
import unittest
from evaluation.run_auto_documents import flow_checks, MORGAN, ROBIN


class AutoBenchmarkScoringTests(unittest.TestCase):
    def test_invalid_json_is_not_counted_as_appropriate_abstention(self):
        result = {'connection': 'local', 'source_mode': 'Documents',
                  'status': 'invalid_response', 'answer': 'Could not verify.'}
        checks = flow_checks({'refusal': True}, result, [], [])
        self.assertFalse(all(checks.values()))

    def test_another_persons_verified_resume_cannot_pass(self):
        case = {'contains': ['Python'], 'source': MORGAN}
        result = {'connection': 'local', 'source_mode': 'Documents', 'status': 'passages_verified',
                  'answer': 'Python.', 'results': [{'filename': ROBIN, 'text': 'Python.'}],
                  'support': [{'source_id': 0, 'quote': 'Python.'}]}
        checks = flow_checks(case, result, [], [])
        self.assertTrue(checks['coverage'])
        self.assertFalse(checks['correct_cited_file'])

    def test_external_dispatch_fails_even_when_answer_is_correct(self):
        case = {'contains': ['Python'], 'source': MORGAN}
        result = {'connection': 'local', 'source_mode': 'Documents', 'status': 'passages_verified',
                  'answer': 'Python.', 'results': [{'filename': MORGAN, 'text': 'Python.'}],
                  'support': [{'source_id': 0, 'quote': 'Python.'}]}
        self.assertTrue(all(flow_checks(case, result, [], []).values()))
        self.assertFalse(all(flow_checks(case, result, ['jira'], []).values()))
        self.assertFalse(all(flow_checks(case, result, [], ['web']).values()))

    def test_language_name_substrings_do_not_satisfy_coverage(self):
        case = {'contains': ['Java'], 'source': MORGAN}
        result = {'connection': 'local', 'source_mode': 'Documents', 'status': 'passages_verified',
                  'answer': 'JavaScript.', 'results': [{'filename': MORGAN, 'text': 'JavaScript.'}],
                  'support': [{'source_id': 0, 'quote': 'JavaScript.'}]}
        self.assertFalse(flow_checks(case, result, [], [])['coverage'])


if __name__ == '__main__':
    unittest.main()
