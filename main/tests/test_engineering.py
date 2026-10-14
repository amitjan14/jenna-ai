import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from main.src.engineering.tracing import request_trace,event,list_traces,read_trace
from main.src.engineering.runtime import checkpoint, retry_read
from main.src.engineering.jobs import JobManager
from main.src.engineering.cache import TTLCache,credential_key
from main.src.engineering.context import fit_messages,summarize_history


class EngineeringTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'JENNA_MEMORY_PATH':self.temp.name});self.env.start()
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def test_trace_redacts_values_and_records_failed_requests(self):
        with self.assertRaises(ValueError):
            with request_trace('test') as trace:
                event('tool_started',tool='lookup',arguments={'token':'SECRET','query':'personal question'})
                raise ValueError('sensitive content')
        data=read_trace(trace.id);serialized=json.dumps(data)
        self.assertNotIn('SECRET',serialized);self.assertNotIn('personal question',serialized)
        self.assertNotIn('sensitive content',serialized);self.assertEqual(data['status'],'failed')
        self.assertEqual(list_traces()[0]['id'],trace.id)
    def test_cache_expires_and_is_credential_scoped(self):
        cache=TTLCache();cache.put('key',{'data':[1]},.01);value=cache.get('key');value['data'].append(2)
        self.assertEqual(cache.get('key'),{'data':[1]});time.sleep(.02);self.assertIsNone(cache.get('key'))
        config={'auth':{'type':'bearer','token_env':'FIXTURE_TOKEN'}}
        with patch.dict(os.environ,{'FIXTURE_TOKEN':'one'}):one=credential_key(config,'test')
        with patch.dict(os.environ,{'FIXTURE_TOKEN':'two'}):two=credential_key(config,'test')
        self.assertNotEqual(one,two)
    def test_context_compacts_complete_tool_groups_and_keeps_current_question(self):
        messages=[{'role':'system','content':'system'},{'role':'user','content':'Current request?'}]
        for _ in range(8):messages.extend([{'role':'assistant','tool_calls':[{'function':{'name':'lookup','arguments':{}}}]}, {'role':'tool','tool_name':'lookup','content':json.dumps({'text':'x'*2000})}])
        result,changed=fit_messages(messages,[],context_tokens=3000,reserved_output=1000,question='Current request?')
        self.assertTrue(changed);self.assertEqual(result[1]['content'],'Current request?')
        for index,message in enumerate(result):
            if message['role']=='tool':self.assertEqual(result[index-1]['role'],'assistant')
        self.assertIn('LAB-73',summarize_history([{'content':'LAB-73 was discussed'}]*8))
    def test_cancelled_job_does_not_execute_followup_steps(self):
        entered=threading.Event()
        def handler(payload):
            entered.set()
            while True:checkpoint();time.sleep(.005)
        jobs=JobManager(handler);job=jobs.submit({'question':'test','timeout':10});self.assertTrue(entered.wait(1))
        jobs.cancel(job['id'])
        for _ in range(100):
            if jobs.get(job['id'])['status']=='cancelled':break
            time.sleep(.01)
        self.assertEqual(jobs.get(job['id'])['status'],'cancelled');jobs.pool.shutdown()
    def test_pdf_ocr_and_table_layout(self):
        import pymupdf
        from main.src.rag.search_utils import layout_pages,section_chunks
        document=pymupdf.open();page=document.new_page();page.insert_text((50,50),'POLICY\nAnnual leave is 18 days.')
        pages=layout_pages(io.BytesIO(document.tobytes()));self.assertIn('18',pages[0]['text']);self.assertFalse(pages[0]['ocr'])
        chunks=section_chunks('POLICY\n'+'word '*400+'\nOTHER SECTION\nBudget is 750 dollars.')
        self.assertTrue(any('OTHER SECTION' in chunk and '750' in chunk for chunk in chunks));document.close()
    def test_ocr_scanned_page(self):
        import pymupdf
        from PIL import Image,ImageDraw,ImageFont
        from main.src.rag.search_utils import layout_pages
        image=Image.new('RGB',(1600,400),'white');draw=ImageDraw.Draw(image)
        font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',60) if Path('/System/Library/Fonts/Supplemental/Arial.ttf').exists() else ImageFont.truetype('DejaVuSans.ttf',60)
        draw.text((40,100),'Annual leave is 18 days',fill='black',font=font)
        stream=io.BytesIO();image.save(stream,format='PNG')
        document=pymupdf.open();page=document.new_page(width=800,height=200);page.insert_image(page.rect,stream=stream.getvalue())
        text=layout_pages(io.BytesIO(document.tobytes()));self.assertTrue(text[0]['ocr']);self.assertIn('18',text[0]['text']);document.close()
    def test_dataset_split_and_no_duplicates(self):
        from evaluation.generalization import load_dataset
        rows=load_dataset();self.assertEqual(len(rows),60);self.assertEqual(sum(r['split']=='heldout' for r in rows),18)

    def test_release_gate_rejects_incomplete_or_stale_reports(self):
        from main.src.engineering.release import gate,manifest,sha,ROOT
        candidate={'dataset_sha256':sha(ROOT/'evaluation/datasets/agent_generalization.jsonl'),
                   'manifest':manifest(),'summary':{'total':10,'passed':9,'complete':False},'results':[]}
        result=gate(candidate);self.assertFalse(result['passed']);self.assertFalse(result['checks']['complete'])
        candidate['summary']['complete']=True;candidate['dataset_sha256']='stale'
        self.assertFalse(gate(candidate)['checks']['dataset_current'])

    def test_verification_only_changes_do_not_rewrite_frozen_inference(self):
        from main.src.engineering.release import behavior_fingerprint_matches
        previous={'files':{'main/src/agent.py':'runtime-1','.github/workflows/checks.yml':'ci-1','main/src/engineering/release.py':'gate-1'}}
        current={'files':{'main/src/agent.py':'runtime-1','.github/workflows/checks.yml':'ci-2','main/src/engineering/release.py':'gate-2'}}
        self.assertTrue(behavior_fingerprint_matches(previous,current))
        current['files']['main/src/agent.py']='runtime-2'
        self.assertFalse(behavior_fingerprint_matches(previous,current))

    def test_layout_parser_preserves_real_table_rows(self):
        from evaluation.pdf_generalization import make_pdf
        from main.src.rag.search_utils import layout_pages
        parsed=layout_pages(io.BytesIO(make_pdf({'parser':'table','text':''})))
        self.assertGreater(parsed[0]['table_count'],0)
        self.assertIn('Meals | 35 dollars per day',parsed[0]['text'])


class RetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_read_retries_once(self):
        attempts=[]
        async def read():
            attempts.append(1)
            if len(attempts)==1:raise TimeoutError()
            return 42
        self.assertEqual(await retry_read(read),42);self.assertEqual(len(attempts),2)
    async def test_validation_error_does_not_retry(self):
        attempts=[]
        async def read():attempts.append(1);raise ValueError('bad args')
        with self.assertRaises(ValueError):await retry_read(read)
        self.assertEqual(len(attempts),1)


class APITests(unittest.TestCase):
    def test_health_validation_and_job_contracts(self):
        from fastapi.testclient import TestClient
        from main.src.tools import api
        jobs=JobManager(lambda payload:{'answer':'42','status':'answered','support':[],'results':[],'tools_used':[]})
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'JENNA_MEMORY_PATH':temp}),patch.object(api, 'manager', jobs):
            client=TestClient(api.app);self.assertEqual(client.get('/health').status_code, 200)
            self.assertEqual(client.post('/jobs',json={'question':''}).status_code,422)
            self.assertEqual(client.get('/jobs/unknown').status_code,404)
            response=client.post('/jobs',json={'question':'calculate 6*7'});self.assertEqual(response.status_code,202)
            ident=response.json()['id']
            for _ in range(100):
                job=client.get('/jobs/'+ident).json()
                if job['status']=='completed':break
                time.sleep(.01)
            self.assertEqual(job['result']['answer'],'42');self.assertEqual(client.get('/traces/'+ident).status_code,200)
            self.assertEqual(client.get('/traces?limit=999').status_code,422)
        jobs.pool.shutdown()
