"""Single-worker local request queue with progress and cooperative cancellation."""
from main.src.utils.enums import Connection, ExecutionStatus, SearchMode
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Lock
import time
import uuid
from main.src.engineering.runtime import Control,active_control,RequestCancelled,DeadlineExceeded
from main.src.engineering.tracing import request_trace
from main.src.agent.assistant_service import run_assistant


class JobManager:
    def __init__(self,handler=None):
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='jenna-inference')
        self.lock=Lock()
        self.jobs={}
        self.handler=handler or self.default_handler
    @staticmethod
    def default_handler(payload):
        return run_assistant(
            payload['question'],
            history=payload.get('history'),
            connection=payload.get('connection', Connection.AUTO),
            mode=payload.get('mode', SearchMode.AUTO),
            filters=payload.get('filters'),
            session_id=payload.get('session_id')
        )
    def submit(self,payload):
        if not isinstance(payload.get('question'),str) or not 1<=len(payload['question'].strip())<=4000:
            raise ValueError('Question must contain 1–4000 characters')
        job_id=uuid.uuid4().hex
        def progress(value):
            with self.lock:
                if value.get('text_delta'):
                    self.jobs[job_id]['partial_text']=(self.jobs[job_id].get('partial_text','')+value['text_delta'])[:32000]
                self.jobs[job_id]['progress']={k:v for k,v in value.items() if k!='text_delta'}
                self.jobs[job_id]['updated']=time.time()
        control=Control(timeout=payload.get('timeout',180),progress=progress)
        with self.lock:
            # Bound retained results; active requests are never evicted.
            finished=[key for key,value in self.jobs.items() if value['status'] in {ExecutionStatus.COMPLETED,ExecutionStatus.FAILED,ExecutionStatus.CANCELLED,ExecutionStatus.TIMED_OUT}]
            for key in finished[:-100]:
                self.jobs.pop(key,None)
            if sum(v['status'] in {ExecutionStatus.QUEUED,ExecutionStatus.RUNNING} for v in self.jobs.values())>=8:
                raise ValueError('Request queue is full')
            self.jobs[job_id]={
                'id':job_id,
                'status':ExecutionStatus.QUEUED,
                'created':time.time(),
                'updated':time.time(),
                'progress':{
                    'stage': ExecutionStatus.QUEUED
                },
                'control':control
            }
        self.pool.submit(self._run,job_id,deepcopy(payload),control)
        return self.get(job_id)
    def _run(self,job_id,payload,control):
        token=active_control.set(control)
        try:
            control.check()
            with self.lock:
                self.jobs[job_id]['status']=ExecutionStatus.RUNNING
                queue_seconds = time.monotonic() - control.started
            with request_trace('job',job_id) as trace:
                result=self.handler(payload)
                control.check()
                result['trace_id']=trace.id
                result.setdefault('metrics', {})['queue_seconds'] = round(queue_seconds, 4)
                trace.status=result.get('status',ExecutionStatus.COMPLETED)
            with self.lock:
                self.jobs[job_id].update(
                    status=ExecutionStatus.COMPLETED,
                    result=result,
                    updated=time.time()
                )
        except (RequestCancelled,DeadlineExceeded) as error:
            with self.lock:
                self.jobs[job_id].update(
                    status=ExecutionStatus.CANCELLED if isinstance(error,RequestCancelled) else ExecutionStatus.TIMED_OUT,
                    error=type(error).__name__,
                    partial_text='',
                    updated=time.time()
                )
        except Exception as error:
            with self.lock:
                self.jobs[job_id].update(
                    status=ExecutionStatus.FAILED,
                    error=type(error).__name__,
                    partial_text='',
                    updated=time.time()
                )
        finally:
            active_control.reset(token)
    def get(self,job_id):
        with self.lock:
            job=self.jobs.get(job_id)
            return deepcopy({key:value for key,value in job.items() if key!='control'}) if job else None
    def cancel(self,job_id):
        with self.lock:
            job=self.jobs.get(job_id)
            if not job:
                return None
            job['control'].cancel_event.set()
            if job['status']==ExecutionStatus.QUEUED:
                job['status']=ExecutionStatus.CANCELLED
        return self.get(job_id)


manager=JobManager()
