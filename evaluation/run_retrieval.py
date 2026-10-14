"""Evaluate the application's actual Chroma retrieval and reranker separately."""
import argparse
import contextlib
import json
import statistics
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dataset',type=Path,default=ROOT/'backup/test/benchmark/zeno_rag_benchmark_80_relevance.json')
    p.add_argument('--output',type=Path,default=ROOT/'reports/retrieval-current.json')
    p.add_argument('--candidate-k',type=int,default=40);p.add_argument('--context-k',type=int,default=8)
    p.add_argument('--dense-only',action='store_true');p.add_argument('--limit',type=int)
    args=p.parse_args()
    if not 1<=args.context_k<=args.candidate_k: p.error('Require candidate_k >= context_k >= 1')
    from main.src.rag.document_store import search_documents
    from main.src.rag.rag_service import collection
    from main.src.rag.search_utils import rerank_retrieved
    data=json.loads(args.dataset.read_text());questions=data['questions'][:args.limit]
    metadata=collection.get(include=['metadatas'])['metadatas']
    available={(m['filename'],m['page'],m['chunk_index']) for m in metadata}
    rows=[];excluded=[]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.with_suffix('.log').open('w') as log:
        for q in questions:
            key=(q.get('expected_filename'),q.get('expected_page'),q.get('expected_chunk_index'))
            pages=q.get('relevant_pages')
            relevant={loc for loc in available if loc[0]==key[0] and loc[1] in pages} if pages else {key}&available
            if not relevant:
                excluded.append({'id':q['id'],'reason':'No matching labeled evidence in current corpus'})
                continue
            start=time.perf_counter()
            with contextlib.redirect_stdout(log):
                candidates=search_documents(q['question'],n_results=args.candidate_k,max_chunks=args.candidate_k,
                                            hybrid=not args.dense_only,rerank=False)
            retrieval=time.perf_counter()-start
            stamp=time.perf_counter();context=rerank_retrieved(q['question'],candidates,max_chunks=args.context_k)
            rerank_seconds=time.perf_counter()-stamp
            def locations(items):return [(r['filename'],r['page'],r['chunk_index']) for r in items]
            candidate_locs=locations(candidates);context_locs=locations(context)
            ranks=[i+1 for i,loc in enumerate(context_locs) if loc in relevant]
            rows.append({'id':q['id'],'candidate_hit':bool(set(candidate_locs)&relevant),
                         'context_hit':bool(ranks),'reciprocal_rank':1/min(ranks) if ranks else 0,
                         'precision':len(set(context_locs)&relevant)/len(context_locs) if context_locs else 0,
                         'recall':len(set(context_locs)&relevant)/len(relevant),
                         'retrieval_seconds':retrieval,'rerank_seconds':rerank_seconds,
                         'context_locations':context_locs})
    summary={'evaluated':len(rows),'excluded':len(excluded)}
    for field in ['candidate_hit','context_hit','reciprocal_rank','precision','recall','retrieval_seconds','rerank_seconds']:
        summary[field]=statistics.mean(r[field] for r in rows) if rows else None
    report={'candidate_k':args.candidate_k,'context_k':args.context_k,'hybrid':not args.dense_only,
            'summary':summary,'rows':rows,'excluded':excluded,
            'limitations':['Legacy evidence labels may be stale; missing locations are explicitly excluded.',
                           'Page-level labels treat every chunk on a labeled page as relevant.',
                           'Unanswerable questions need the agent suite; this suite evaluates labeled retrieval only.',
                           'Development benchmark; not held-out production accuracy.']}
    args.output.write_text(json.dumps(report,indent=2));print(json.dumps(summary,indent=2))
    return 0 if rows else 1


if __name__=='__main__':raise SystemExit(main())
