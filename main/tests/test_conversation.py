import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from main.src.agent.conversation import load_state, save_state, memory_request, natural_summary, rewrite_reply, context_messages


class Model:
    def __init__(self, *outputs): self.outputs=iter(outputs)
    def chat(self, **kwargs): return {'message': {'content': next(self.outputs)}}


class ConversationTests(unittest.TestCase):
    def setUp(self):
        from main.src.memory import memory_service
        self.temp=tempfile.TemporaryDirectory()
        self.patch=patch.object(memory_service,'DB_PATH',Path(self.temp.name)/'memory.sqlite3');self.patch.start()
    def tearDown(self):self.patch.stop();self.temp.cleanup()

    def test_session_restore_and_chat_clear_remove_compacted_state(self):
        from main.src.memory.chat_memory import create_chat,clear_chat_history
        session=create_chat();state={'goal':'Learn Python','constraints':['No analogies'], 'references':['Option two: iterative solution']}
        save_state(session,state);self.assertEqual(load_state(session),state)
        clear_chat_history(session);self.assertEqual(load_state(session)['goal'],'')

    def test_natural_memory_has_provenance_and_requires_explicit_write(self):
        from main.src.memory.note_memory import note_details,list_notes
        rejected=memory_request('memory_write','language','Python','What language should I use?')
        self.assertEqual(rejected['status'],'needs_clarification');self.assertEqual(list_notes(),{})
        memory_request('memory_write','preferred_language','Python','Please remember I prefer Python','session')
        self.assertEqual(note_details('preferred_language')['provenance']['session_id'],'session')
        recalled=memory_request('memory_read','preferred language','','What language do I prefer?')
        self.assertIn('Python',recalled['answer'])
        memory_request('memory_delete','preferred language','','Forget my language preference')
        self.assertEqual(list_notes(),{})

    def test_legacy_note_schema_migrates_without_losing_data(self):
        import sqlite3
        from main.src.memory import memory_service
        with sqlite3.connect(memory_service.DB_PATH) as db:
            db.execute('CREATE TABLE personal_notes(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)')
            db.execute("INSERT INTO personal_notes(key,value) VALUES ('language','Python')")
        from main.src.memory.note_memory import note_details
        self.assertEqual(note_details('language')['value'],'Python')
        self.assertEqual(note_details('language')['provenance'],{})

    def result(self):
        return {'status':'passages_verified','answer':'Annual leave is 22 days.',
                'results':[{'filename':'policy.pdf','page':1,'chunk_index':0,'text':'Annual leave is 22 days.'}],
                'support':[{'source_id':0,'quote':'Annual leave is 22 days.'}]}

    def test_summary_requires_valid_citations_and_support_verification(self):
        draft=json.dumps({'answer':'You receive 22 days of annual leave [1].','source_ids':[0]})
        verdict=json.dumps({'supported':True,'complete':True,'reason':''})
        result=natural_summary('How much leave?',self.result(),Model(draft,verdict))
        self.assertEqual(result['answer_kind'],'grounded_summary')
        invalid=json.dumps({'answer':'Leave is 22 days [9].','source_ids':[8]})
        self.assertEqual(natural_summary('leave?',self.result(),Model(invalid))['answer'],'Annual leave is 22 days.')

    def test_unsupported_summary_and_revision_do_not_replace_evidence(self):
        draft=json.dumps({'answer':'Leave is 50 days [1].','source_ids':[0]})
        verdict=json.dumps({'supported':False,'complete':True,'reason':'Evidence says 22'})
        self.assertEqual(natural_summary('leave?',self.result(),Model(draft,verdict))['answer'],'Annual leave is 22 days.')
        history=[{'role':'assistant','content':'Annual leave is 22 days.',**self.result()}]
        result=rewrite_reply('make it say 50',history,client=Model('Leave is 50 days.',verdict))
        self.assertEqual(result['status'],'revision_rejected');self.assertIn('22',result['answer'])

    def test_grounded_revision_reuses_evidence_without_tool_calls(self):
        history=[{'role':'assistant','content':'Annual leave is 22 days.',**self.result()}]
        verdict=json.dumps({'supported':True,'complete':True,'reason':''})
        with patch('main.src.rag.document_store.search_documents') as search,patch('main.src.integrations.mcp_client.run_mcp_question') as mcp:
            result=rewrite_reply('make it shorter',history,client=Model('22 days of annual leave [1].',verdict))
        search.assert_not_called();mcp.assert_not_called();self.assertEqual(result['answer_kind'],'grounded_rewrite')

    def test_context_keeps_relevant_old_turn_and_bounds_input(self):
        history=[{'role':'user','content':'Option two is the iterative approach.'}]+[{'role':'assistant','content':'unrelated '*1000}]*20
        context=context_messages(history,'Explain option two iterative approach',max_chars=12000)
        self.assertTrue(any('Option two' in m['content'] for m in context))
        self.assertLessEqual(sum(len(m['content']) for m in context),12000)

    def test_invalid_or_removed_citations_reject_grounded_rewrite(self):
        history=[{'role':'assistant','content':'Annual leave is 22 days [1].',**self.result()}]
        verdict=json.dumps({'supported':True,'complete':True,'reason':''})
        for answer in ['22 days [9].','22 days.']:
            result=rewrite_reply('make it shorter',history,client=Model(answer,verdict))
            self.assertEqual(result['status'],'revision_rejected')

    def test_malformed_history_support_requires_evidence_again(self):
        previous={'role':'assistant','content':'Annual leave is 22 days.',**self.result()}
        previous['support']=[{'source_id':-1,'quote':'Invented quote'}]
        result=rewrite_reply('make it shorter',[previous])
        self.assertEqual(result['status'],'needs_clarification')

    def test_real_stream_deltas_are_accumulated_and_cancel_closes_generator(self):
        from main.src.tools.llm import Client
        from main.src.engineering.runtime import Control,active_control,RequestCancelled
        updates=[];closed=[]
        def chunks():
            try:
                yield {'message':{'content':'Hello '}}
                yield {'message':{'content':'world'},'eval_count':2}
            finally:closed.append(True)
        client=Client();control=Control(progress=updates.append);token=active_control.set(control)
        try:
            with patch.object(client.client,'chat',return_value=chunks()):
                self.assertEqual(client.stream_chat(model='test'),'Hello world')
        finally:active_control.reset(token)
        self.assertEqual([u['text_delta'] for u in updates if 'text_delta' in u],['Hello ','world']);self.assertTrue(closed)
        def cancelled_chunks():
            try:
                yield {'message':{'content':'first'}}
                control.cancel_event.set()
                yield {'message':{'content':'must not appear'}}
            finally:closed.append(True)
        token=active_control.set(control)
        try:
            with patch.object(client.client,'chat',return_value=cancelled_chunks()),self.assertRaises(RequestCancelled):
                client.stream_chat(model='test')
        finally:active_control.reset(token)
        self.assertEqual(len(closed),2)

    def test_sse_endpoint_reports_deltas_and_terminal_result(self):
        from fastapi.testclient import TestClient
        from main.src.tools import api
        from main.src.engineering.jobs import JobManager
        from main.src.engineering.runtime import checkpoint
        def handler(payload):
            checkpoint('answer_delta',text_delta='Hello ');time.sleep(.2)
            checkpoint('answer_delta',text_delta='world')
            return {'answer':'Hello world','status':'conversation_completed'}
        jobs=JobManager(handler)
        with patch.object(api, 'manager', jobs):
            client=TestClient(api.app);job=client.post('/jobs', json={'question': 'hello', 'session_id': 'test-session'}).json()
            response=client.get('/jobs/'+job['id']+'/events')
            self.assertIn('event: delta',response.text);self.assertIn('event: result',response.text)
            self.assertIn('Hello',response.text);self.assertEqual(client.get('/jobs/missing/events').status_code,404)
        jobs.pool.shutdown()


if __name__=='__main__':unittest.main()
