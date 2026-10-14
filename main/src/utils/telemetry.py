"""Request-scoped measurements; no user text is recorded by this module."""
from main.src.utils.enums import ExecutionStatus, ModelOperation
from contextvars import ContextVar
from functools import wraps
from time import perf_counter

active_trace = ContextVar("jenna_trace", default=None)


def record_call(kind, seconds, response=None):
    from main.src.engineering.tracing import event
    event('model_call',kind=kind,seconds=seconds,input_tokens=(response or {}).get('prompt_eval_count',0),
          output_tokens=(response or {}).get('eval_count',0))
    trace = active_trace.get()
    if trace is not None:
        response = response or {}
        trace.append({"kind": kind, "seconds": round(seconds, 4),
                      "input_tokens": (response.get("prompt_eval_count", 0) or 0),
                      "output_tokens": (response.get("eval_count", 0) or 0)})


def instrument_request(function):
    @wraps(function)
    def measured(*args, **kwargs):
        from main.src.engineering.tracing import request_trace
        with request_trace(function.__name__) as trace:
            result=execute(*args,**kwargs)
            trace.status=result.get('status',ExecutionStatus.COMPLETED)
            result['trace_id']=trace.id
            return result

    def execute(*args, **kwargs):
        parent = active_trace.get()
        calls = parent if parent is not None else []
        call_start = len(calls)
        token = active_trace.set(calls)
        start = perf_counter()
        try:
            result = function(*args, **kwargs)
            measured_calls = calls[call_start:]
            result["metrics"] = {
                "total_seconds": round(perf_counter() - start, 4),
                "llm_calls": sum(c["kind"] == ModelOperation.CHAT for c in measured_calls),
                "embedding_calls": sum(c["kind"] == ModelOperation.EMBED for c in measured_calls),
                "input_tokens": sum(c["input_tokens"] for c in measured_calls),
                "output_tokens": sum(c["output_tokens"] for c in measured_calls),
                "calls": measured_calls,
            }
            return result
        finally:
            active_trace.reset(token)
    return measured
