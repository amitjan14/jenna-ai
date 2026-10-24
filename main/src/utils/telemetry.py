"""Request-scoped measurements; no user text is recorded by this module."""
from main.src.utils.enums import ExecutionStatus, ModelOperation
from contextvars import ContextVar
from functools import wraps
from time import perf_counter

active_trace = ContextVar("jenna_trace", default=None)


def record_call(kind, seconds, response=None):
    from main.src.engineering.tracing import event, current_trace, active_span
    response = response or {}
    row = {"kind": kind, "seconds": round(seconds, 6),
           "input_tokens": response.get("prompt_eval_count", 0) or 0,
           "output_tokens": response.get("eval_count", 0) or 0,
           "span_id": active_span.get()}
    trace = current_trace.get()
    if trace is not None and active_span.get() is not None:
        row['method'] = trace.spans[active_span.get()]['method']
        row['label'] = trace.spans[active_span.get()]['label']
    for source, target in [('load_duration', 'load_seconds'),
                           ('prompt_eval_duration', 'prompt_seconds'),
                           ('eval_duration', 'generation_seconds')]:
        value = response.get(source)
        if isinstance(value, (int, float)) and value >= 0:
            row[target] = round(value / 1_000_000_000, 6)
    event('model_call', **row)
    calls = active_trace.get()
    if calls is not None:
        calls.append(row)


def instrument_request(function):
    @wraps(function)
    def measured(*args, **kwargs):
        from main.src.engineering.tracing import request_trace, timing_span
        with request_trace(function.__name__) as trace:
            span_start = len(trace.spans)
            with timing_span('Request' if function.__name__ != 'index_and_store_document' else 'PDF upload and indexing',
                             function.__module__ + '.' + function.__qualname__):
                result=execute(*args,**kwargs)
            result['metrics']['steps'] = [dict(row) for row in trace.spans[span_start:]]
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
