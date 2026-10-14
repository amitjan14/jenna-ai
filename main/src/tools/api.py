"""Loopback REST API for Jenna jobs, traces, and readiness."""
from main.src.tools.llm import get_client
from main.src.utils.enums import Connection, ExecutionStatus
from main.src.utils.constants import DEFAULT_CHAT_MODEL
import os
from fastapi import FastAPI,HTTPException
from main.src.utils.schemas import Ask, Message
from fastapi.responses import JSONResponse, StreamingResponse
from main.src.engineering.jobs import manager
from main.src.engineering.tracing import list_traces,read_trace

app=FastAPI(title='Jenna local API',version='0.2.0')








@app.get('/health')
def health():return {'status':'ok','version':'0.2.0','inference':Connection.LOCAL}


@app.get('/ready')
def ready():
    from main.src.utils.constants import CHAT_MODEL,ROUTER_MODEL,EMBEDDING_MODEL
    required={CHAT_MODEL,ROUTER_MODEL,EMBEDDING_MODEL,os.getenv('JENNA_MCP_MODEL',DEFAULT_CHAT_MODEL)}
    try:
        installed={m.model for m in get_client(timeout=3).list().models}
        missing=sorted(model for model in required if model not in installed and model+':latest' not in installed)
        return JSONResponse({'ready':not missing,'missing_models':missing},status_code=503 if missing else 200)
    except Exception:return JSONResponse({'ready':False,'reason':'Ollama unavailable'},status_code=503)


@app.post('/jobs',status_code=202)
def submit(payload:Ask):
    if payload.filters:
        if set(payload.filters)-{'filename','page'} or 'filename' in payload.filters and not isinstance(payload.filters['filename'],str) or 'page' in payload.filters and (not isinstance(payload.filters['page'],int) or isinstance(payload.filters['page'],bool) or payload.filters['page']<1):
            raise HTTPException(422,'Invalid document filter')
    if payload.connection not in {Connection.AUTO,Connection.LOCAL}:
        from main.src.integrations.mcp_client import load_servers
        if payload.connection not in load_servers():raise HTTPException(422,'Unknown MCP connection')
    try:return manager.submit(payload.model_dump())
    except ValueError as error:raise HTTPException(429 if 'queue' in str(error) else 422,str(error))


@app.get('/jobs/{job_id}')
def job(job_id:str):
    result=manager.get(job_id)
    if result is None:raise HTTPException(404,'Job not found')
    return result


@app.post('/jobs/{job_id}/cancel')
def cancel(job_id:str):
    result=manager.cancel(job_id)
    if result is None:raise HTTPException(404,'Job not found')
    return result


@app.get('/jobs/{job_id}/events')
def job_events(job_id:str):
    if manager.get(job_id) is None:raise HTTPException(404,'Job not found')
    async def events():
        import asyncio,json
        sent=0;stage=None
        while True:
            current=manager.get(job_id)
            if current is None:break
            text=current.get('partial_text','')
            if len(text)>sent:
                yield 'event: delta\ndata: '+json.dumps({'text':text[sent:]})+'\n\n';sent=len(text)
            progress=current.get('progress',{}).get('stage')
            if progress!=stage:
                yield 'event: progress\ndata: '+json.dumps({'stage':progress})+'\n\n';stage=progress
            if current['status'] not in {ExecutionStatus.QUEUED,ExecutionStatus.RUNNING}:
                yield 'event: result\ndata: '+json.dumps(current)+'\n\n';break
            await asyncio.sleep(.15)
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache'})


@app.get('/traces')
def traces(limit:int=50):
    if not 1<=limit<=200:raise HTTPException(422,'Limit must be 1–200')
    return list_traces(limit)


@app.get('/traces/{trace_id}')
def trace(trace_id:str):
    result=read_trace(trace_id)
    if result is None:raise HTTPException(404,'Trace not found')
    return result


def main():
    import argparse,uvicorn
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8767);args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('Invalid port')
    uvicorn.run(app,host='127.0.0.1',port=args.port)


if __name__=='__main__':main()
