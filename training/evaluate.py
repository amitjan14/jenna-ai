"""Compare the same MLX base weights with and without local adapters."""
import argparse
import gc
import json
import math
import statistics
import time
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def score(row,text):
    target=row['messages'][-1]['content']
    if row['task']=='conversation':
        # Automated syntax/length checks are not a personality-quality rating.
        return {'usable':bool(text.strip()) and len(text)<2000}
    try:
        actual=json.loads(text)
        expected=json.loads(target)
    except (ValueError,TypeError):
        return {'valid_json':False,'correct':False}
    if row['task']=='routing':
        correct=actual.get('action')==expected['action'] and set(actual)=={'action','expression'}
        if expected['action']=='calculator':
            import sys
            sys.path.insert(0,str(ROOT))
            from main.src.tools.calculator import calculate
            try:
                correct=correct and math.isclose(calculate(actual['expression']),calculate(expected['expression']),rel_tol=1e-9)
            except Exception:
                correct=False
        else:
            correct=correct and actual.get('expression')==''
        return {'valid_json':True,'correct':correct}
    if row['task']=='evidence':
        request=json.loads(row['messages'][1]['content'])
        try:
            parts=actual['parts']; gold=expected['parts']
            correct=len(parts)==len(gold)
            for part, target_part in zip(parts,gold):
                correct=correct and part['part_id']==target_part['part_id'] and part['answerable']==target_part['answerable']
                if part['answerable']:
                    correct=correct and bool(part['support'])
                    for item in part['support']:
                        sid=item['source_id']; quote=item['quote']
                        correct=correct and type(sid) is int and 0<=sid<len(request['sources']) and bool(quote.strip())
                        correct=correct and ' '.join(quote.split()) in ' '.join(request['sources'][sid]['text'].split())
                    expected_quotes={i['quote'] for i in target_part['support']}
                    actual_quotes={i['quote'] for i in part['support']}
                    correct=correct and expected_quotes==actual_quotes
                else:
                    correct=correct and part['support']==[]
            return {'valid_json':True,'correct':bool(correct)}
        except (KeyError,TypeError,IndexError):
            return {'valid_json':True,'correct':False}
    raise ValueError('Unknown task')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',default=str(ROOT/'training/base_model'))
    parser.add_argument('--adapters',default=str(ROOT/'training/adapters'))
    parser.add_argument('--data',type=Path,default=ROOT/'training/data/test.jsonl')
    parser.add_argument('--output',type=Path,default=ROOT/'reports/finetuning-comparison.json')
    parser.add_argument('--limit',type=int)
    args=parser.parse_args()
    from mlx_lm import load,generate
    from mlx_lm.sample_utils import make_sampler
    import mlx.core as mx
    rows=[json.loads(line) for line in args.data.read_text().splitlines()][:args.limit]
    reports=[]
    for label,adapter in [('base',None),('finetuned',args.adapters)]:
        model,tokenizer=load(args.model,adapter_path=adapter)
        results=[]
        for row in rows:
            messages=[dict(m) for m in row['messages'][:-1]]
            # Both models receive the output contract; baseline must not have
            # to infer an undocumented schema from training targets.
            if row['task']=='routing':
                import sys
                sys.path.insert(0,str(ROOT))
                from main.src.utils.schemas import ROUTE_SCHEMA
                schema=ROUTE_SCHEMA
            elif row['task']=='evidence':
                schema={'type':'object','properties':{'parts':{'type':'array','items':{
                    'type':'object','properties':{'part_id':{'type':'integer'},'answerable':{'type':'boolean'},
                    'support':{'type':'array','items':{'type':'object','properties':{
                    'source_id':{'type':'integer'},'quote':{'type':'string'}},'required':['source_id','quote']}}},
                    'required':['part_id','answerable','support']}}},'required':['parts']}
            else:
                schema=None
            if schema:
                messages[0]['content']+='\nReturn only JSON matching this schema: '+json.dumps(schema)
            prompt=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
            start=time.perf_counter()
            output=generate(model,tokenizer,prompt=prompt,max_tokens=768,sampler=make_sampler(temp=0),verbose=False)
            measured=score(row,output)
            results.append({'task':row['task'],'group':row['group'],'checks':measured,
                            'seconds':time.perf_counter()-start,'output':output})
            print(label,row['task'],measured,flush=True)
        tasks=defaultdict(list)
        for r in results: tasks[r['task']].append(r)
        summary={task:{'count':len(items),'correct':sum(r['checks'].get('correct',r['checks'].get('usable',False)) for r in items),
                       'rate':statistics.mean(r['checks'].get('correct',r['checks'].get('usable',False)) for r in items)} for task,items in tasks.items()}
        summary['mean_seconds']=statistics.mean(r['seconds'] for r in results)
        reports.append({'model':label,'summary':summary,'rows':results})
        del model,tokenizer
        gc.collect();mx.clear_cache()
    base,tuned=[r['summary'] for r in reports]
    objective_tasks=[t for t in base if t in ['routing','evidence']]
    task_gates={t: tuned[t]['rate'] >= base[t]['rate'] for t in ['routing','evidence','conversation'] if t in base}
    promote=bool(objective_tasks) and all(task_gates.values()) and any(tuned[t]['rate']>base[t]['rate'] for t in objective_tasks)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    report={'comparisons':reports,'promotion_recommended':promote,'non_regression_by_task':task_gates,
            'limitations':['Small local development holdout; no independent generalization claim.',
                           'Unconstrained MLX generation differs from Ollama schema-constrained runtime.',
                           'Conversation usability is a smoke check, not a personality-quality score.',
                           'Private model outputs: do not publish this report.']}
    args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps({'promotion_recommended':promote,'base':base,'finetuned':tuned},indent=2))


if __name__=='__main__':main()
