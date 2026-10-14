"""Isolated RAG ablations: chunking, dense/hybrid retrieval, and reranking."""
import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
LABELS=[('policy.pdf',1,'How many annual leave days are allowed?','Annual leave entitlement is 18 days.'),
        ('policy.pdf',2,'What is the training reimbursement limit?','Training reimbursement is capped at 750 dollars per year.'),
        ('operations.pdf',1,'Which port does Aurora use?','Aurora runs on port 9107.'),
        ('operations.pdf',2,'Who owns the Aurora project?','Aurora is owned by Mira Patel.')]


def pdf(pages):
    import pymupdf
    document=pymupdf.open()
    for heading,fact in pages:
        page=document.new_page()
        filler=' '.join(['General background describes standard operational practices and administrative procedures.']*30)
        text=heading+'\n\n'+filler+'\n\nSPECIFIC REQUIREMENT\n\n'+fact+'\n\n'+filler
        remainder=page.insert_textbox(pymupdf.Rect(35,35,560,805),text,fontsize=9)
        if remainder<0:raise ValueError('Synthetic PDF text did not fit')
    raw=document.tobytes();document.close();return raw


def worker(args):
    os.environ['JENNA_MEMORY_PATH']=args.memory
    os.environ['JENNA_CHUNKING_STRATEGY']=args.chunking
    from main.src.rag.document_store import index_and_store_document,search_documents
    from main.src.rag.rag_service import collection
    from main.src.engineering.tracing import request_trace
    index_and_store_document(pdf([('LEAVE POLICY',LABELS[0][3]),('TRAINING POLICY',LABELS[1][3])]),'policy.pdf')
    index_and_store_document(pdf([('NETWORK CONFIGURATION',LABELS[2][3]),('PROJECT OWNERSHIP',LABELS[3][3])]),'operations.pdf')
    stored=collection.get(include=['documents','metadatas']);rows=[]
    normalize=lambda text:' '.join(text.split())
    for filename,page,question,quote in LABELS:
        relevant={(m['filename'],m['page'],m['chunk_index']) for d,m in zip(stored['documents'],stored['metadatas']) if m['filename']==filename and m['page']==page and normalize(quote) in normalize(d)}
        if not relevant:raise ValueError('Gold evidence absent from indexed fixture')
        stamp=time.perf_counter()
        with request_trace('rag_experiment') as trace:
            retrieved=search_documents(question,n_results=12,max_chunks=4,hybrid=args.hybrid,rerank=args.rerank)
        locations=[(r['filename'],r['page'],r['chunk_index']) for r in retrieved]
        ranks=[index+1 for index,loc in enumerate(locations) if loc in relevant]
        rows.append({'question':question,'hit_at_4':bool(ranks),'recall_at_4':len(set(locations)&relevant)/len(relevant),
                     'precision_at_4':len(set(locations)&relevant)/len(locations) if locations else 0,
                     'mrr':1/min(ranks) if ranks else 0,'seconds':time.perf_counter()-stamp,'trace_id':trace.id})
    report={'chunking':args.chunking,'hybrid':args.hybrid,'rerank':args.rerank,'index_chunks':collection.count(),
            'summary':{key:statistics.mean(row[key] for row in rows) for key in ['hit_at_4','recall_at_4','precision_at_4','mrr','seconds']},'rows':rows,
            'limitations':'Four synthetic labeled questions; demonstrates controlled comparison, not general retrieval accuracy.'}
    args.output.write_text(json.dumps(report,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--memory');p.add_argument('--chunking',choices=['words','sections'],default='words')
    p.add_argument('--hybrid',action='store_true');p.add_argument('--rerank',action='store_true');p.add_argument('--output',type=Path,default=ROOT/'reports/rag-ablation.json');args=p.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.worker:worker(args);return
    results=[]
    for chunking in ['words','sections']:
        for hybrid,rerank in [(False,False),(True,False),(True,True)]:
            with tempfile.TemporaryDirectory(prefix='jenna-rag-ablation-') as memory:
                output=Path(memory)/'result.json'
                cmd=[sys.executable,'-m','evaluation.rag_experiments','--worker','--memory',memory,'--chunking',chunking,'--output',str(output)]
                if hybrid:cmd.append('--hybrid')
                if rerank:cmd.append('--rerank')
                run=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
                if run.returncode:raise RuntimeError(run.stderr[-1200:])
                results.append(json.loads(output.read_text()))
                print(chunking,hybrid,rerank,results[-1]['summary'],flush=True)
    args.output.write_text(json.dumps({'experiments':results,'limitations':'Isolated synthetic PDF corpus; no user index was modified.'},indent=2)+'\n')


if __name__=='__main__':main()
