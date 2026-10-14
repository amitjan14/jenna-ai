"""Explicit cold-model and warmed-model latency measurements with local inference."""
import argparse,asyncio,json,os,statistics
from pathlib import Path
from evaluation.run_mcp_agent import Fixture,TOOLS,CONFIG
from main.src.integrations.mcp_agent import run
from main.src.integrations.mcp_client import jira_identifiers_supported
from main.src.tools.llm import Client


async def benchmark(args):
    import ollama
    os.environ['JENNA_MCP_MODEL']=args.model
    connection=ollama.Client(timeout=180);rows=[]
    async def request():
        fixture=Fixture()
        return await run('What is the due date of LAB-73?',CONFIG,'jira',TOOLS,fixture.execute,Client(timeout=180),jira_identifiers_supported)
    await request() # Warm-up is recorded separately from measured warm samples.
    for mode in ['warm','cold_model']:
        for index in range(args.repeats):
            if mode=='cold_model':await asyncio.to_thread(connection.generate,model=args.model,prompt='',keep_alive=0)
            result=await request()
            memory=[{'model':m.name,'bytes':m.size,'context_length':m.context_length} for m in connection.ps().models if m.name==args.model]
            rows.append({'mode':mode,'sample':index+1,'status':result['status'],'metrics':result['metrics'],'memory':memory})
            print(mode,index+1,result['metrics']['total_seconds'],flush=True)
    summary={}
    for mode in ['warm','cold_model']:
        values=sorted(row['metrics']['total_seconds'] for row in rows if row['mode']==mode)
        summary[mode]={'samples':len(values),'p50':statistics.median(values),'p95':values[max(0,__import__('math').ceil(.95*len(values))-1)]}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps({'model':args.model,'summary':summary,'rows':rows,
        'limitations':['Synthetic MCP data with actual local inference, not live service latency.','Cold-model unloads Ollama residency; OS file caches are not cleared.','Few samples are smoke measurements, not stable production percentiles.']},indent=2)+'\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',default='qwen3.5:9b');p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--output',type=Path,default=Path('reports/performance.json'));args=p.parse_args()
    if not 1<=args.repeats<=20:p.error('Repeats must be 1–20')
    asyncio.run(benchmark(args))


if __name__=='__main__':main()
