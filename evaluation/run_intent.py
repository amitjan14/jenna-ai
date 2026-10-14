"""Actual local-model intent/typo checks, with isolated document and MCP fixtures."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    {'id': 'jira-overview', 'question': 'whats going on with OPS-42', 'connection': 'jira', 'mode': 'Auto'},
    {'id': 'jira-typo', 'question': 'show the histroy of OPS-42', 'connection': 'jira', 'mode': 'Auto'},
    {'id': 'jira-implicit', 'question': 'who is assigned OPS-42 and whens it due', 'connection': 'jira', 'mode': 'Auto'},
    {'id': 'jira-named', 'question': 'serch jira for the checkout ticket', 'connection': 'jira', 'mode': 'Auto'},
    {'id': 'jira-followup', 'question': 'when is it du?', 'connection': 'jira', 'mode': 'Auto',
     'history': [{'role': 'user', 'content': 'Tell me about OPS-42'}, {'role': 'assistant', 'content': 'OPS-42 is in progress.', 'connection': 'jira'}]},
    {'id': 'jira-ambiguous', 'question': 'search jira about a ticket', 'clarification': True},
    {'id': 'documents-typo', 'question': 'from my pdf whats the annal leav allowence at Maple Lab?', 'connection': 'local', 'mode': 'Documents'},
    {'id': 'documents-vague', 'question': 'give me the gist of the leave policy in my documents', 'connection': 'local', 'mode': 'Documents'},
    {'id': 'documents-jira-topic', 'question': 'from my notes explain Jira workflows', 'connection': 'local', 'mode': 'Documents'},
    {'id': 'web-typo', 'question': 'what is the captial of japan?', 'connection': 'local', 'modes': ['Auto', 'Web']},
    {'id': 'web-current', 'question': 'look online for the latest weather in Chennai', 'connection': 'local', 'mode': 'Web'},
    {'id': 'documentation', 'question': 'look up official OpenAI docs for native tool calling', 'connection': 'openai', 'mode': 'Auto'},
    {'id': 'ambiguous-followup', 'question': 'what happened to that one?', 'clarification': True},
]


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, default=ROOT/'reports/intent-development.json')
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory(prefix='jenna-intent-') as memory:
        os.environ['JENNA_MEMORY_PATH'] = memory
        from main.src.agent.assistant_service import plan_request, run_assistant
        from main.src.integrations.mcp_client import load_servers, jira_identifiers_supported
        from main.src.integrations.mcp_agent import run
        from main.src.tools.llm import Client
        from main.src.rag.rag_service import collection, create_embeddings
        from evaluation.generalization import Scenario, CONFIG, TOOLS
        from main.src.engineering.release import manifest
        frozen = manifest()
        text = 'Maple Lab allows 22 days of annual leave. Request leave through Cedar portal. Paid leave requires manager approval.'
        collection.upsert(ids=['policy'], documents=[text], embeddings=create_embeddings([text]),
                          metadatas=[{'filename': 'policy.pdf', 'page': 1, 'chunk_index': 0}])
        for case in CASES:
            try:
                plan = plan_request(case['question'], case.get('history'), load_servers())
                if case.get('clarification'):
                    checks = {'clarification': bool(plan['clarification']) and not plan['question']}
                else:
                    checks = {'source': plan['connection'] == case['connection'],
                              'mode': plan['mode'] in case.get('modes', [case.get('mode')]),
                              'no_unnecessary_clarification': bool(plan['question']) and not plan['clarification']}
                row = {'id': case['id'], 'kind': 'interpretation', 'passed': all(checks.values()), 'checks': checks, 'plan': plan}
            except Exception as error: row = {'id': case['id'], 'passed': False, 'error': type(error).__name__}
            rows.append(row); print(row['id'], row['passed'], flush=True)
        fixture_case = {'variant': 'normal'}
        def remote(question, server, history=None):
            fixture = Scenario(fixture_case)
            return asyncio.run(run(question, CONFIG, server, TOOLS, fixture.execute, Client(timeout=180),
                                   jira_identifiers_supported, history))
        end_to_end = [
            ('flow-jira-vague', 'whats up with OPS-42', None, 'jira', ['Launch checkout API', 'In Progress']),
            ('flow-jira-typo', 'histroy of OPS-42 plz', None, 'jira', ['In Progress']),
            ('flow-jira-followup', 'when is it du?', CASES[4]['history'], 'jira', ['2026', '19']),
            ('flow-documents-typo', 'from my pdf whats the annal leav allowence at Maple Lab?', None, 'local', ['22']),
            ('flow-documents-vague', 'give me the gist of the leave policy in my documents', None, 'local', ['22', 'Cedar']),
        ]
        with patch('main.src.integrations.mcp_client.run_mcp_question', side_effect=remote):
            for ident, question, history, expected_connection, fragments in end_to_end:
                try:
                    result = run_assistant(question, history)
                    checks = {'source': result['connection'] == expected_connection,
                              'usable': result['status'] in {'answered', 'partial_answer', 'passages_verified'},
                              'coverage': all(f.casefold() in result['answer'].casefold() for f in fragments)}
                    row = {'id': ident, 'kind': 'end_to_end', 'passed': all(checks.values()), 'checks': checks,
                           'status': result['status'], 'answer': result['answer'], 'metrics': result['metrics']}
                except Exception as error: row = {'id': ident, 'passed': False, 'error': type(error).__name__}
                rows.append(row); print(ident, row['passed'], flush=True)
        args.output.write_text(json.dumps({'manifest': frozen, 'summary': {'passed': sum(r['passed'] for r in rows), 'total': len(rows)},
            'results': rows, 'limitations': ['Development suite authored for this change; no held-out claims.',
                'Actual Qwen inference; synthetic MCP and directly indexed document fixtures, not live Jira/web.']}, indent=2)+'\n')
    return 0 if all(r['passed'] for r in rows) else 1


if __name__ == '__main__': raise SystemExit(main())
