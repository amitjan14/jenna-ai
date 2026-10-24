"""Timing accounting must identify costs without double counting nested work."""
import asyncio
import json
import unittest
from unittest.mock import patch
from main.src.engineering.tracing import Trace, request_trace, timed_step
from main.src.utils.telemetry import instrument_request, record_call
from main.src.utils.timing_summary import timing_rows, slowest_steps


class TimingTests(unittest.TestCase):
    def test_nested_costs_reconcile_and_repeated_calls_stay_separate(self):
        clock = [100.0]
        @timed_step('Evidence selection')
        def select():
            clock[0] += 2
        @instrument_request
        def request():
            clock[0] += 1
            select()
            select()
            clock[0] += 3
            return {'status': 'answered'}
        with patch.object(Trace, 'save'), patch('time.perf_counter', side_effect=lambda: clock[0]), \
                patch('main.src.utils.telemetry.perf_counter', side_effect=lambda: clock[0]):
            metrics = request()['metrics']
        root, first, second = metrics['steps']
        self.assertEqual(metrics['total_seconds'], 8)
        self.assertEqual(root['seconds'], 8)
        self.assertEqual(root['self_seconds'], 4)
        self.assertEqual(first['seconds'], 2)
        self.assertEqual(second['parent_id'], root['id'])
        self.assertEqual(sum(row['self_seconds'] for row in metrics['steps']), 8)
        self.assertEqual(len(timing_rows(metrics)), 3)
        self.assertEqual(slowest_steps(metrics)[0]['Own (s)'], 4)

    def test_model_breakdown_and_method_attribution(self):
        @timed_step('Ollama chat')
        def chat(secret):
            record_call('chat', .8, {'load_duration': 100_000_000,
                'prompt_eval_duration': 200_000_000, 'eval_duration': 400_000_000})
        @instrument_request
        def request():
            chat('private source text')
            return {'status': 'answered'}
        with patch.object(Trace, 'save'):
            result = request()
        call = result['metrics']['calls'][0]
        self.assertEqual(call['load_seconds'], .1)
        self.assertEqual(call['prompt_seconds'], .2)
        self.assertEqual(call['generation_seconds'], .4)
        self.assertIn('chat', call['method'])
        self.assertNotIn('private source text', json.dumps(result))

    def test_failed_async_step_records_duration_and_resets_parent(self):
        @timed_step('MCP read')
        async def read():
            raise ValueError('sensitive content')
        @timed_step('Next step')
        def next_step():
            return 42
        with patch.object(Trace, 'save'), request_trace('test') as trace:
            with self.assertRaises(ValueError):
                asyncio.run(read())
            next_step()
        self.assertEqual(trace.spans[0]['status'], 'failed')
        self.assertEqual(trace.spans[0]['error_type'], 'ValueError')
        self.assertIsNone(trace.spans[1]['parent_id'])
        self.assertNotIn('sensitive content', json.dumps(trace.events))

    def test_nested_request_metrics_do_not_drop_outer_steps_or_calls(self):
        @instrument_request
        def inner():
            record_call('chat', .02)
            return {'status': 'answered'}
        @instrument_request
        def outer():
            record_call('chat', .01)
            return inner()
        with patch.object(Trace, 'save'):
            metrics = outer()['metrics']
        self.assertEqual(metrics['llm_calls'], 2)
        self.assertEqual(len(metrics['steps']), 2)
        self.assertEqual(metrics['steps'][1]['parent_id'], metrics['steps'][0]['id'])

    def test_legacy_metrics_have_no_fabricated_breakdown(self):
        self.assertEqual(timing_rows({'total_seconds': 5}), [])
