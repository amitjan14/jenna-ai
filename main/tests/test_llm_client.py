"""Shared provider lifecycle and request isolation; no inference or network calls."""
import ast
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from main.src.tools import llm
from main.src.utils.telemetry import active_trace

ROOT = Path(__file__).resolve().parents[2]


class SharedClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(llm, '_clients', {}),
                        patch.dict(os.environ, {'OLLAMA_HOST':'http://fixture.local',
                                               'OLLAMA_API_KEY':'fixture-one',
                                               'JENNA_MEMORY_PATH':self.temp.name}),
                        patch.object(llm.ollama, 'Client')]
        self.patches[0].start()
        self.patches[1].start()
        self.sdk = self.patches[2].start()

    def tearDown(self):
        llm.close_clients()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_repeated_and_concurrent_lookups_create_one_wrapped_client(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            clients = list(executor.map(lambda _:llm.get_client(), range(32)))
        self.assertTrue(all(client is clients[0] for client in clients))
        self.assertIsInstance(clients[0], llm.Client)
        self.sdk.assert_called_once_with(host='http://fixture.local', timeout=60)

    def test_timeout_host_and_credential_profiles_are_isolated(self):
        normal = llm.get_client()
        self.assertIsNot(normal, llm.get_client(timeout=3))
        self.assertIsNot(normal, llm.get_client(timeout=180))
        with patch.dict(os.environ, {'OLLAMA_HOST':'http://different.local'}):
            other = llm.get_client()
        with patch.dict(os.environ, {'OLLAMA_API_KEY':'fixture-two'}):
            credential_scope = llm.get_client()
        self.assertIsNot(normal, other)
        self.assertIsNot(normal, credential_scope)
        self.assertIs(llm.get_client(), normal)
        self.assertEqual(self.sdk.call_count, 5)

    def test_shared_chat_preserves_measured_overrides_and_request_options(self):
        self.sdk.return_value.chat.return_value = {'message':{'content':'42'}, 'prompt_eval_count':3, 'eval_count':1}
        options = {'temperature':0}
        messages = [{'role':'user', 'content':'Calculate 6 * 7'}]
        calls = []
        token = active_trace.set(calls)
        try:
            result = llm.get_client().chat(model='qwen3.5:9b', messages=messages, options=options)
        finally:
            active_trace.reset(token)
        request = self.sdk.return_value.chat.call_args.kwargs
        self.assertEqual(result['message']['content'], '42')
        self.assertFalse(request['think'])
        self.assertIn('num_ctx', request['options'])
        self.assertEqual(options, {'temperature':0})
        self.assertEqual(messages, [{'role':'user', 'content':'Calculate 6 * 7'}])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['input_tokens'], 3)
        self.assertEqual(calls[0]['output_tokens'], 1)

    def test_streamed_requests_do_not_share_accumulated_text(self):
        self.sdk.return_value.chat.side_effect = [iter([{'message':{'content':'First'}}]),
                                                 iter([{'message':{'content':'Second'}}])]
        shared = llm.get_client(timeout=120)
        self.assertEqual(shared.stream_chat(model='fixture'), 'First')
        self.assertEqual(llm.get_client(timeout=120).stream_chat(model='fixture'), 'Second')

    def test_shutdown_closes_profiles_and_allows_clean_reinitialization(self):
        first = llm.get_client()
        llm.get_client(timeout=3)
        llm.close_clients()
        self.assertEqual(self.sdk.return_value._client.close.call_count, 2)
        self.assertIsNot(llm.get_client(), first)
        self.assertEqual(self.sdk.call_count, 3)


class ClientArchitectureTests(unittest.TestCase):
    def test_only_llm_module_constructs_ollama_clients(self):
        violations = []
        paths = [*ROOT.glob('main/src/**/*.py'), *ROOT.glob('evaluation/*.py')]
        for path in paths:
            if path == ROOT/'main/src/tools/llm.py':
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom) and node.module == 'ollama':
                    if any(name.name in {'Client','AsyncClient'} for name in node.names):
                        violations.append(f'{path}:{node.lineno}')
                if not isinstance(node, ast.Call):
                    continue
                if isinstance(node.func, ast.Name) and node.func.id == 'Client':
                    violations.append(f'{path}:{node.lineno}')
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    if node.func.value.id == 'ollama' and node.func.attr in {'Client','AsyncClient'}:
                        violations.append(f'{path}:{node.lineno}')
        self.assertEqual(violations, [])


if __name__ == '__main__':
    unittest.main()
