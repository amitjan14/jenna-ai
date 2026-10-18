"""Local, content-minimized request traces. No prompts or tool outputs are stored."""
from main.src.utils.enums import ExecutionStatus
from main.src.utils import regex_constants as rx
from contextvars import ContextVar
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid

current_trace = ContextVar('jenna_request_trace', default=None)
SECRET = re.compile(rx.SECRET_FIELD, re.I)
PUBLIC = {'kind','tool','model','status','stage','error_type','server','strategy','digest','prompt_version','cache','reason'}


def safe(value, key=''):
    if SECRET.search(key):
        return '[REDACTED]'
    if isinstance(value, dict):
        return {str(k):safe(v,str(k)) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [safe(v,key) for v in value[:100]]
    if isinstance(value, str) and key not in PUBLIC:
        return {'length':len(value),'sha256':hashlib.sha256(value.encode()).hexdigest()[:16]}
    if isinstance(value,str):
        return re.sub(rx.AUTH_HEADER, '[REDACTED]',value)[:300]
    return value if isinstance(value,(int,float,bool)) or value is None else type(value).__name__


def db_path():
    root=Path(os.getenv('JENNA_MEMORY_PATH','jenna_memory'))
    if not root.is_absolute(): root=Path(__file__).resolve().parents[2]/root
    root.mkdir(parents=True,exist_ok=True)
    return root/'traces.sqlite3'


def connection():
    conn=sqlite3.connect(db_path(),timeout=10)
    conn.execute('CREATE TABLE IF NOT EXISTS traces (id TEXT PRIMARY KEY, created REAL, kind TEXT, status TEXT, seconds REAL, payload TEXT)')
    return conn


class Trace:
    def __init__(self,kind,request_id=None):
        self.id=request_id or uuid.uuid4().hex
        self.kind=kind
        self.events=[]
        self.started=time.time()
        self.status=ExecutionStatus.RUNNING
    def add(self,stage,**attributes):
        if len(self.events)<1000:
            self.events.append({
                'stage':stage,
                'elapsed_seconds':round(time.time()-self.started,4),
                **safe(attributes)
            })
    def save(self):
        seconds=time.time()-self.started
        payload={
            'id':self.id,
            'kind':self.kind,
            'status':self.status,
            'created':self.started,
            'seconds':seconds,
            'events':self.events
        }
        with connection() as conn:
            conn.execute('INSERT OR REPLACE INTO traces VALUES (?,?,?,?,?,?)',(self.id,self.started,self.kind,self.status,seconds,json.dumps(payload)))
            conn.execute('DELETE FROM traces WHERE created < ?', (time.time()-int(os.getenv('JENNA_TRACE_RETENTION_DAYS','30'))*86400,))
        conn.close()


@contextmanager
def request_trace(kind,request_id=None):
    existing=current_trace.get()
    if existing:
        yield existing
        return
    trace=Trace(kind,request_id)
    token=current_trace.set(trace)
    trace.add('request_started',kind=kind)
    try:
        yield trace
        if trace.status==ExecutionStatus.RUNNING:
            trace.status=ExecutionStatus.COMPLETED
    except BaseException as error:
        trace.status=ExecutionStatus.FAILED
        trace.add('request_failed',error_type=type(error).__name__)
        raise
    finally:
        trace.add('request_finished',status=trace.status)
        try:
            trace.save()
        except (OSError,sqlite3.Error):
            import logging
            logging.getLogger(__name__).warning('Could not persist request trace')
        finally:
            current_trace.reset(token)


def event(stage,**attributes):
    trace=current_trace.get()
    if trace:
        trace.add(stage,**attributes)


def list_traces(limit=50):
    if not 1<=limit<=200:
        raise ValueError('Trace limit must be 1–200')
    with connection() as conn:
        rows=conn.execute('SELECT id,created,kind,status,seconds FROM traces ORDER BY created DESC LIMIT ?', (limit,)).fetchall()
    conn.close()
    return [dict(zip(['id','created','kind','status','seconds'],row)) for row in rows]


def read_trace(trace_id):
    with connection() as conn:
        row=conn.execute('SELECT payload FROM traces WHERE id=?',(trace_id,)).fetchone()
    conn.close()
    return json.loads(row[0]) if row else None
