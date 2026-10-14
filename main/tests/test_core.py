import json
import os
import tempfile
import unittest
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory(prefix='jenna-test-')
os.environ['JENNA_MEMORY_PATH'] = TEMP.name
from main.src.tools.calculator import calculate, cosine_similarity
from main.src.utils.common_utils import split_text
from main.src.memory.note_memory import remember_note, recall_note, forget_note
from main.src.memory.chat_memory import create_chat, save_message, load_messages, delete_chat
from main.src.utils.telemetry import instrument_request, record_call


class CoreTests(unittest.TestCase):
    def test_arithmetic_and_sqrt(self):
        self.assertEqual(calculate('sqrt(81) + (15 / 100 * 200)'),39)
        self.assertAlmostEqual(calculate('-3 + 8 / 2'),1)

    def test_arithmetic_rejects_code_and_excess(self):
        for expr in ['__import__("os").system("echo unsafe")','2**100','True + 1','sqrt(-1)','1e16','sqrt(x=4)']:
            with self.subTest(expr=expr), self.assertRaises((ValueError,TypeError)):
                calculate(expr)
        with self.assertRaises(ZeroDivisionError): calculate('1 / 0')

    def test_chunk_boundaries_and_validation(self):
        words=[str(i) for i in range(500)]
        chunks=split_text(' '.join(words))
        self.assertEqual(chunks[0].split()[-40:],chunks[1].split()[:40])
        self.assertEqual(chunks[-1].split()[-1],'499')
        for size, overlap in [(0,0),(200,200),(-1,0),(2,3)]:
            with self.assertRaises(ValueError): split_text('a b',size,overlap)

    def test_cosine(self):
        self.assertEqual(cosine_similarity([1,0],[0,1])['similarity'],0)
        with self.assertRaises(ValueError): cosine_similarity([0,0],[1,0])

    def test_persistent_memory_and_chat(self):
        remember_note(' Test key ','value')
        self.assertEqual(recall_note('test key'),'value')
        self.assertTrue(forget_note('test key'))
        self.assertIsNone(recall_note('test key'))
        chat=create_chat();save_message(chat,{'role':'user','content':'test'})
        self.assertEqual(load_messages(chat)[0]['content'],'test')
        self.assertTrue(delete_chat(chat))
        self.assertEqual(load_messages(chat),[])

    def test_request_metrics_do_not_leak(self):
        @instrument_request
        def f():
            record_call('chat',.1,{'prompt_eval_count':8,'eval_count':3})
            return {}
        self.assertEqual(f()['metrics']['llm_calls'],1)
        self.assertEqual(f()['metrics']['input_tokens'],8)


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from main.src.rag import rag_service
        cls.rag=rag_service

    def answer(self,parts,required=None):
        response={'message':{'content':json.dumps({'parts':parts})}}
        with patch.object(self.rag.ollama_client,'chat',side_effect=[response, {'message':{'content':json.dumps({'supported':True,'complete':True,'reason':'Direct evidence'})}}]):
            return self.rag.generate_document_answer('What is the budget?', [{'text':'The budget is 40 chunks.'}],required_parts=required)

    def test_valid_quote(self):
        r=self.answer([{'part_id':0,'answerable':True,'support':[{'source_id':0,'quote':'The budget is 40 chunks.'}]}])
        self.assertTrue(r['answerable'])

    def test_fabricated_quote_rejected(self):
        r=self.answer([{'part_id':0,'answerable':True,'support':[{'source_id':0,'quote':'The budget is 90 chunks.'}]}])
        self.assertEqual(r['status'],'invalid_evidence')

    def test_missing_multipart_evidence_refuses(self):
        r=self.answer([{'part_id':0,'answerable':True,'support':[{'source_id':0,'quote':'The budget is 40 chunks.'}]},
                       {'part_id':1,'answerable':False,'support':[]}],['What is the budget?','What is the GPU?'])
        self.assertEqual(r['status'],'insufficient_evidence')

    def test_duplicate_part_rejected(self):
        p={'part_id':0,'answerable':False,'support':[]}
        self.assertEqual(self.answer([p,p],['A','B'])['status'],'invalid_response')

    def test_general_decomposition(self):
        with patch.object(self.rag.ollama_client,'chat',return_value={'message':{'content':json.dumps({'parts':['What is the port?','Who is the owner?']})}}):
            self.assertEqual(len(self.rag.plan_question_parts('What is the port and who is the owner?')),2)





class IngestionTests(unittest.TestCase):
    def test_large_document_uses_multiple_batches(self):
        import io
        from unittest.mock import Mock
        from main.src.rag import document_store as store
        collection=Mock();collection.get.return_value={'ids':[]}
        pages=[{'page':1,'text':' '.join('word'+str(i) for i in range(450))}]
        with patch.object(store,'collection',collection),patch.object(store,'MAX_BATCH_SIZE',2), \
             patch.dict('os.environ',{'JENNA_PDF_PARSER':'pypdf'}), \
             patch.object(store,'extract_pages',return_value=pages), \
             patch.object(store,'create_embeddings',side_effect=lambda texts:[[1.,0.] for _ in texts]):
            count=store.add_document(io.BytesIO(b'pdf bytes'),'large.pdf')
        self.assertEqual(count,3)
        self.assertEqual(collection.upsert.call_count,2)
        sizes=[len(c.kwargs['ids']) for c in collection.upsert.call_args_list]
        self.assertEqual(sizes,[2,1])
        self.assertEqual(collection.upsert.call_args_list[0].kwargs['metadatas'][0]['document_chunk_count'],3)

    def test_failed_pdf_deletion_restores_index(self):
        from unittest.mock import Mock
        from main.src.rag import document_store as store
        snapshot={'ids':['a'],'documents':['evidence'],'metadatas':[{'filename':'a.pdf'}],'embeddings':[[1.,0.]]}
        collection=Mock();collection.get.return_value=snapshot
        with patch.object(store,'collection',collection), \
             patch('main.src.memory.memory_service.delete',side_effect=RuntimeError('disk failure')):
            with self.assertRaises(RuntimeError):store.delete_document('a.pdf')
        self.assertEqual(collection.upsert.call_args.kwargs['documents'],['evidence'])




class RoutingTests(unittest.TestCase):
    def test_factual_question_cannot_become_invented_arithmetic(self):
        from main.src.agent import agent_service as agent
        response={'message':{'content':json.dumps({'action':'calculator','expression':'24'})}}
        with patch.object(agent.client,'chat',return_value=response):
            self.assertEqual(agent.decide_action('What is my exact GPU model?')['action'],'search_documents')

    def test_current_compound_subject_preserves_all_clauses(self):
        from main.src.agent import agent_service as agent
        question='What port does Aurora use, and who owns it?'
        result=agent.resolve_followup(question,[])
        self.assertEqual(result['question'],question)
        self.assertEqual(result['status'],'standalone')





class AutoSearchTests(unittest.TestCase):
    def run_question(self, question, mode="Auto", local_status="invalid_evidence", local_answerable=False):
        from contextlib import ExitStack
        from main.src.agent import agent_service as agent
        local={'answerable':local_answerable,'answer':'Local answer','support':[], 'status':local_status}
        online={'answerable':True,'answer':'Tokyo is the capital of Japan.',
                'support':[{'source_id':0,'quote':'Tokyo is the capital of Japan.'}], 'status':'passages_verified'}
        with ExitStack() as stack:
            stack.enter_context(patch.object(agent,'resolve_followup',return_value={'status':'standalone','question':question,'clarification':''}))
            stack.enter_context(patch.object(agent,'decide_action',return_value={'action':'search_documents','expression':''}))
            stack.enter_context(patch.object(agent,'search_and_answer',return_value=([],local)))
            stack.enter_context(patch.object(agent,'rewrite_search_query',return_value=question))
            stack.enter_context(patch('main.src.tools.web_tools.generate_document_answer',return_value=online))
            web=stack.enter_context(patch('main.src.tools.web_tools.search_web',return_value=[{
                'kind':'web','filename':'Japan','text':'Tokyo is the capital of Japan.',
                'url':'https://example.com/japan','retrieved_at':'2026-10-12'}]))
            result=agent.run_agent(question,search_mode=mode)
            return result,web.call_count

    def test_auto_falls_back_after_failed_verification(self):
        result,calls=self.run_question('What is the capital of Japan?')
        self.assertEqual(calls,1)
        self.assertIn('Tokyo',result['answer'])
        self.assertEqual(result['tools_used'],['search_documents','search_web'])
        self.assertEqual(result['support'][0]['source_id'],0)
        self.assertEqual(result['results'][0]['kind'],'web')

    def test_documents_mode_never_searches_online(self):
        result,calls=self.run_question('What is the capital of Japan?',mode='Documents')
        self.assertEqual(calls,0)
        self.assertEqual(result['status'],'invalid_evidence')

    def test_supported_local_answer_does_not_search_online(self):
        result,calls=self.run_question('What is the capital of Japan?',local_status='passages_verified',local_answerable=True)
        self.assertEqual(calls,0)
        self.assertEqual(result['answer'],'Local answer')

    def test_private_question_stays_local(self):
        result,calls=self.run_question('What is my exact GPU model?',local_status='insufficient_evidence')
        self.assertEqual(calls,0)
        self.assertEqual(result['status'],'insufficient_evidence')

    def test_missing_web_key_is_explained(self):
        from main.src.agent import agent_service as agent
        local={'answerable':False,'answer':'','support':[], 'status':'no_context'}
        with patch.dict(os.environ,{'TAVILY_API_KEY':''}), \
             patch.object(agent,'resolve_followup',return_value={'status':'standalone','question':'What is the capital of Japan?','clarification':''}), \
             patch.object(agent,'decide_action',return_value={'action':'search_documents','expression':''}), \
             patch.object(agent,'search_and_answer',return_value=([],local)):
            result=agent.run_agent('What is the capital of Japan?',search_mode='Auto')
        self.assertEqual(result['status'],'retrieval_unavailable')
        self.assertIn('TAVILY_API_KEY',result['answer'])
        self.assertEqual(result['support'],[])





class WebEvidenceRecoveryTests(unittest.TestCase):
    def test_deeper_search_replaces_excerpt_and_keeps_citations_valid(self):
        from main.src.tools import web_tools as agent
        basic={'kind':'web','filename':'Japan','url':'https://example.com/japan','text':'Japan is in Asia.'}
        advanced={**basic,'text':'Tokyo is the capital of Japan.'}
        failed={'answerable':False,'status':'insufficient_evidence','answer':'','support':[],
                'rejection_reason':'Capital is not stated.'}
        passed={'answerable':True,'status':'passages_verified','answer':'Tokyo is the capital of Japan.',
                'support':[{'source_id':0,'quote':'Tokyo is the capital of Japan.'}]}
        with patch.object(agent,'search_web',side_effect=[[basic],[advanced]]) as web, \
             patch.object(agent,'generate_document_answer',side_effect=[failed,passed]):
            result=agent.run_online_search('What is the capital of Japan?','web','')
        self.assertEqual([call.kwargs['search_depth'] for call in web.call_args_list],['basic','advanced'])
        self.assertEqual(result['status'],'passages_verified')
        self.assertEqual(len(result['results']),1)
        self.assertIn(result['support'][0]['quote'],result['results'][0]['text'])
        self.assertEqual(result['tools_used'],['search_web','search_web'])

    def test_failed_recovery_exposes_sources_and_reason(self):
        from main.src.tools import web_tools as agent
        source={'kind':'web','filename':'Japan','url':'https://example.com/japan','text':'Japan is in Asia.'}
        failed={'answerable':False,'status':'insufficient_evidence','answer':'','support':[],
                'rejection_reason':'Capital is not stated.'}
        with patch.object(agent,'search_web',return_value=[source]) as web, \
             patch.object(agent,'generate_document_answer',return_value=failed):
            result=agent.run_online_search('What is the capital of Japan?','web','')
        self.assertEqual(web.call_count,2)
        self.assertEqual(result['rejection_reason'],'Capital is not stated.')
        self.assertEqual(result['retrieved_sources'][0]['text'],source['text'])
        self.assertEqual(result['support'],[])

    def test_transport_failure_is_not_retried(self):
        from main.src.tools import web_tools as agent
        with patch.object(agent,'search_web',side_effect=agent.WebSearchError('HTTP 401')) as web:
            result=agent.run_online_search('What is the capital of Japan?','web','')
        self.assertEqual(web.call_count,1)
        self.assertEqual(result['status'],'retrieval_unavailable')





class TableRelationTests(unittest.TestCase):
    def test_table_value_must_match_requested_relation(self):
        from main.src.rag.rag_service import table_relation_error
        self.assertTrue(table_relation_error('What is the capital of Japan?','Tokyo','Currency\nTokyo'))
        self.assertEqual(table_relation_error('What is the capital of Japan?','Tokyo','Capital\nTokyo'),'')
        self.assertTrue(table_relation_error('What is the capital of Japan?','Currency Tokyo','Currency Tokyo'))

    def test_one_supported_occurrence_is_sufficient(self):
        from main.src.rag.rag_service import table_relation_error
        self.assertEqual(table_relation_error('What is the capital of Japan?','Tokyo','Currency\nTokyo\nCapital\nTokyo'),'')


if __name__ == '__main__': unittest.main()
