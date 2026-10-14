"""Actual PDF ingestion and local-app evaluation on new documents, tables, and OCR."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
ROOT=Path(__file__).resolve().parents[1]


def make_pdf(spec):
    import pymupdf
    document=pymupdf.open();page=document.new_page()
    if spec['parser']=='scan':
        from PIL import Image,ImageDraw,ImageFont
        image=Image.new('RGB',(1800,600),'white');draw=ImageDraw.Draw(image)
        fontpath='/System/Library/Fonts/Supplemental/Arial.ttf'
        font=ImageFont.truetype(fontpath if Path(fontpath).exists() else 'DejaVuSans.ttf',50)
        for index,line in enumerate(spec['text'].split('. ')):draw.text((40,70+index*90),line,fill='black',font=font)
        stream=io.BytesIO();image.save(stream,format='PNG');page.insert_image(pymupdf.Rect(40,40,560,220),stream=stream.getvalue())
    elif spec['parser']=='table':
        page.insert_text((50,40),'EXPENSE CAPS')
        for y in [60,100,140,180]:page.draw_line((50,y),(500,y))
        for x in [50,270,500]:page.draw_line((x,60),(x,180))
        for y,(name,amount) in zip([85,125,165],[('Meals','35 dollars per day'),('Hotels','140 dollars per night'),('Taxi','60 dollars per trip')]):
            page.insert_text((60,y),name);page.insert_text((280,y),amount)
    else:page.insert_textbox(pymupdf.Rect(40,40,550,800),spec['text'],fontsize=12)
    raw=document.tobytes();document.close();return raw


def main():
    p=argparse.ArgumentParser();p.add_argument('--split',choices=['development','heldout'],default='development');p.add_argument('--limit',type=int);p.add_argument('--output',type=Path,default=ROOT/'reports/pdf-generalization-development.json');args=p.parse_args()
    data=json.loads((ROOT/'evaluation/datasets/pdf_generalization.json').read_text());cases=[c for c in data['cases'] if c['split']==args.split]
    from main.src.engineering.release import manifest,sha
    frozen=manifest();dataset_hash=sha(ROOT/'evaluation/datasets/pdf_generalization.json')
    if args.limit:cases=cases[:args.limit]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='jenna-pdf-eval-') as memory:
        os.environ['JENNA_MEMORY_PATH']=memory
        from main.src.rag.document_store import index_and_store_document
        from main.src.agent.agent_service import run_agent
        personality=(ROOT/'main/instructions/jenna_personality.md').read_text()
        with args.output.with_suffix('.log').open('w') as log,contextlib.redirect_stdout(log):
            for name,spec in data['corpus'].items():index_and_store_document(make_pdf(spec),name)
        rows=[]
        for case in cases:
            try:
                with args.output.with_suffix('.log').open('a') as log,contextlib.redirect_stdout(log):
                    result=run_agent(case['question'],system_prompt=personality,search_mode='Documents',history=case['history'])
                checks={'coverage':all(fragment.casefold() in result['answer'].casefold() for fragment in case['expected'])}
                checks['status']=result['status'] in {'no_context','insufficient_evidence'} if case['refusal'] else result['status']=='passages_verified'
                from main.src.engineering.tracing import read_trace
                row={'id':case['id'],'passed':all(checks.values()),'checks':checks,'answer':result['answer'],'status':result['status'],'metrics':result['metrics'],
                     'support':result.get('support',[]),'sources':result.get('results',[]),'trace':read_trace(result['trace_id'])}
            except Exception as error:row={'id':case['id'],'passed':False,'error':type(error).__name__}
            rows.append(row);print(row['id'],row['passed'],flush=True)
            args.output.write_text(json.dumps({'split':args.split,'manifest':frozen,'dataset_sha256':dataset_hash,'summary':{'passed':sum(row['passed'] for row in rows),'total':len(rows),'planned':len(cases),'complete':len(rows)==len(cases)},'results':rows,'limitations':'Authored synthetic PDFs, including real table extraction and OCR; not broad document accuracy.'},indent=2)+'\n')
    return 0 if rows and all(row['passed'] for row in rows) else 1


if __name__=='__main__':raise SystemExit(main())
