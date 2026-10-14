"""Cooperative cancellation, deadlines, and read-only retry controls."""
import httpx2
import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
import threading
import time
from main.src.engineering.tracing import event


class RequestCancelled(RuntimeError): pass
class DeadlineExceeded(TimeoutError): pass


@dataclass
class Control:
    timeout: float=180
    cancel_event: threading.Event=field(default_factory=threading.Event)
    progress: object=None
    started: float=field(default_factory=time.monotonic)
    def check(self):
        if self.cancel_event.is_set(): raise RequestCancelled('Request cancelled')
        if time.monotonic()-self.started>self.timeout: raise DeadlineExceeded('Request deadline exceeded')
    def emit(self,stage,**data):
        self.check();event(stage,**data)
        if self.progress:self.progress({'stage':stage,**data})


active_control=ContextVar('jenna_control',default=None)


def checkpoint(stage=None,**data):
    control=active_control.get()
    if control:
        if stage:control.emit(stage,**data)
        else:control.check()
    elif stage:event(stage,**data)


async def retry_read(operation,attempts=2,timeout=45):
    """Retry transient transport failures only; caller must enforce read-only policy."""
    for attempt in range(attempts):
        checkpoint()
        try:return await asyncio.wait_for(operation(),timeout=timeout)
        except (TimeoutError,ConnectionError,httpx2.TransportError) as error:
            event('read_retry',attempt=attempt+1,error_type=type(error).__name__)
            if attempt+1>=attempts:raise
            await asyncio.sleep(.25*2**attempt)
