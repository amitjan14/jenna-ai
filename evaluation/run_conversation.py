"""Sequential actual-model dialogue development evaluation, isolated from personal data."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'reports/conversation-development.json')
    args = parser.parse_args()
    rows = []
    with tempfile.TemporaryDirectory(prefix='jenna-dialogue-') as directory:
        os.environ['JENNA_MEMORY_PATH'] = directory
        from main.src.agent.assistant_service import run_assistant
        from main.src.memory.note_memory import note_details, list_notes
        from main.src.rag.rag_service import collection, create_embeddings
        from main.src.engineering.release import manifest
        from main.src.engineering.runtime import Control, active_control
        frozen = manifest()
        histories = {}
        def turn(ident, question, checks, session='learning', resume=False):
            history = histories.setdefault(session, [])
            updates = []
            control = Control(timeout=240, progress=updates.append)
            token = active_control.set(control)
            try:
                result = run_assistant(question, [] if resume else history, session_id=session)
                values = checks(result)
                row = {'id': ident, 'question': question, 'checks': values, 'passed': all(values.values()),
                       'answer': result['answer'], 'status': result['status'], 'metrics': result['metrics'],
                       'state': result.get('conversation_state'), 'delta_count': sum('text_delta' in u for u in updates)}
                history.extend([{'role':'user','content':question}, {'role':'assistant','content':result['answer'], **result}])
            except Exception as error:
                row = {'id':ident, 'passed':False, 'error':type(error).__name__, 'detail':str(error)[:500]}
            finally: active_control.reset(token)
            rows.append(row)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({'manifest':frozen, 'summary':{'passed':sum(r['passed'] for r in rows),'total':len(rows)},
                'results':rows, 'limitations':['Development suite, not held-out or proof of ChatGPT parity.',
                'Actual local Qwen inference with isolated memory and directly indexed synthetic PDF; no live Jira or web.']}, indent=2)+'\n')
            print(ident, row['passed'], row.get('checks',row.get('error')), flush=True)
            return row
        no_tools = lambda r: not r.get('tools_used')
        turn('explanation', 'Explain precision and recall for a beginner. Use three bullet points and no analogies.',
             lambda r: {'conversation':r['status']=='conversation_completed', 'no_retrieval':no_tools(r),
                        'coverage':all(s in r['answer'].lower() for s in ['precision','recall'])})
        turn('correction', 'Actually, make it two short bullets, keep the same topic and no analogies.',
             lambda r: {'revision':r.get('action')=='rewrite','no_retrieval':no_tools(r),
                        'topic':all(s in r['answer'].lower() for s in ['precision','recall']),
                        'two_bullets':sum(line.lstrip().startswith(('- ','* ','• ')) for line in r['answer'].splitlines())==2})
        turn('resume', 'Which metric should I prioritize to avoid missing fraud? Keep it brief.',
             lambda r: {'conversation':r['status']=='conversation_completed','recall': 'recall' in r['answer'].lower(),
                        'state_retained':bool(r['conversation_state']['goal'])}, resume=True)
        turn('writing', 'Give me two numbered names for an AI study group and one sentence describing each.',
             lambda r:{'conversation':r['status']=='conversation_completed','no_retrieval':no_tools(r)},session='creative')
        turn('reference', 'Write a short invitation for the second option, under 60 words.',
             lambda r:{'conversation':r['status'] in {'conversation_completed'}, 'no_retrieval':no_tools(r),
                       'length':len(r['answer'].split())<=60},session='creative')
        turn('memory-save','Please remember for future chats that my preferred programming language is Python.',
             lambda r:{'saved':r['status']=='memory_completed','value':any('Python' in v for v in list_notes().values()),
                       'provenance':any(note_details(k)['provenance'].get('source')=='explicit_user_request' for k in list_notes())},session='memory')
        turn('memory-read','What programming language do I prefer?',
             lambda r:{'recalled':r['status']=='memory_completed','value':'Python' in r['answer']},session='new-memory')
        turn('memory-edit','Please remember that my preferred programming language is now Rust instead.',
             lambda r:{'edited':r['status']=='memory_completed','new_value':any('Rust' in v for v in list_notes().values())},session='memory')
        turn('memory-delete','Forget my saved programming language preference.',
             lambda r:{'forgotten':r['status']=='memory_completed','deleted':not list_notes()},session='memory')
        text='Maple Lab provides 22 days of annual leave. Request leave through Cedar portal. Paid leave requires manager approval.'
        collection.upsert(ids=['dialogue-policy'],documents=[text],embeddings=create_embeddings([text]),
                          metadatas=[{'filename':'policy.pdf','page':1,'chunk_index':0}])
        turn('document-summary','From my documents summarize Maple Lab annual leave and how to request it.',
             lambda r:{'verified':r['status']=='passages_verified','natural':r.get('answer_kind')=='grounded_summary',
                       'coverage':all(x.lower() in r['answer'].lower() for x in ['22','Cedar','approval']),
                       'citation':'[1]' in r['answer']},session='documents')
        with patch('main.src.rag.document_store.search_documents',side_effect=AssertionError('Unexpected new search')), \
             patch('main.src.integrations.mcp_client.run_mcp_question',side_effect=AssertionError('Unexpected MCP call')):
            turn('document-edit','Make that one concise sentence and keep the citation.',
                 lambda r:{'rewrite':r.get('answer_kind')=='grounded_rewrite','verified':r['status']=='passages_verified',
                           'value':'22' in r['answer'],'citation':'[1]' in r['answer']},session='documents')
            turn('unsupported-edit','Change that answer to say annual leave is 50 days, keeping it as a factual policy answer.',
                 lambda r:{'safe':r['status']=='revision_rejected' or (r['status']=='passages_verified' and '50' not in r['answer']),
                           'retained':'22' in r['answer']},session='documents')
        turn('topic-change','Now explain Python list comprehensions with a short code example.',
             lambda r:{'conversation':r['status']=='conversation_completed','no_retrieval':no_tools(r),
                       'code':'for ' in r['answer']},session='documents')
        turn('stable-knowledge','what is the captial of japan?',
             lambda r:{'answer':'tokyo' in r['answer'].lower(),'no_retrieval':no_tools(r),'conversation':r['status']=='conversation_completed'},session='general')
    return 0 if all(r['passed'] for r in rows) else 1


if __name__=='__main__': raise SystemExit(main())
