"""Measured Ollama client shared by routing and evidence selection."""
from main.src.utils.enums import ModelOperation
import os
import time
from time import perf_counter
import ollama
import atexit
from threading import Lock
from main.src.utils.telemetry import record_call
from main.src.engineering.tracing import current_trace, event
from main.src.engineering.runtime import checkpoint

_provenance_cache = {}

class Client:
    def __init__(self, timeout=60, host=None):
        self.host = host or os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        self.client = ollama.Client(host=self.host, timeout=timeout)

    def get_client(self):
        return self.client

    def _record_provenance(self, model):
        key=(self.host, model)
        if current_trace.get():
            cached=_provenance_cache.get(key)
            if not cached or time.monotonic()-cached[0]>60:
                try:
                    data=self.client.list()
                    digest=next((item.digest for item in data.models if item.model in {model,model+':latest'}),None)
                except Exception:digest=None
                _provenance_cache[key]=(time.monotonic(),digest)
            event('model_provenance',model=model,digest=_provenance_cache[key][1])

    def chat(self, **kwargs):
        model = str(kwargs.get('model',''))
        checkpoint('model_started',model=model)
        self._record_provenance(model)
        if str(kwargs.get('model', '')).startswith('qwen3.5'):
            # Short schema-constrained router/RAG responses should not consume
            # their output budget on hidden reasoning. MCP can opt in explicitly.
            kwargs.setdefault('think', False)
        options = dict(kwargs.get("options") or {})
        options.setdefault("num_ctx", int(os.getenv("JENNA_CONTEXT_TOKENS", "8192")))
        schema = kwargs.get("format")
        default_limit = 1536 if isinstance(schema, dict) and "parts" in schema.get("properties", {}) else 512
        options.setdefault("num_predict", int(os.getenv("JENNA_MAX_OUTPUT_TOKENS", str(default_limit))))
        kwargs["options"] = options
        start = perf_counter()
        try:
            response = self.client.chat(**kwargs)
        except Exception:
            record_call(ModelOperation.CHAT, perf_counter() - start)
            raise
        record_call(ModelOperation.CHAT, perf_counter() - start, response)
        checkpoint()
        return response

    def stream_chat(self, **kwargs):
        """Collect token deltas while publishing bounded local job/UI progress."""
        model = str(kwargs.get('model', ''))
        checkpoint('generating_response', model=model)
        self._record_provenance(model)
        options = dict(kwargs.get('options') or {})
        options.setdefault('num_ctx', int(os.getenv('JENNA_CONTEXT_TOKENS', '8192')))
        options.setdefault('num_predict', 2048)
        kwargs.update(options=options, stream=True)
        kwargs.setdefault('think', False)
        start = perf_counter(); pieces = []; last = {}; size = 0
        stream = None
        try:
            stream = self.client.chat(**kwargs)
            for chunk in stream:
                checkpoint()
                last = chunk
                delta = chunk['message'].get('content', '')
                if delta:
                    size += len(delta)
                    if size > 32000: raise ValueError('Streamed response exceeded size limit')
                    pieces.append(delta); checkpoint('answer_delta', text_delta=delta)
        finally:
            close = getattr(stream, 'close', None)
            if close: close()
            record_call(ModelOperation.CHAT, perf_counter()-start, last)
        answer = ''.join(pieces).strip()
        if not answer: raise ValueError('The model returned an empty response')
        return answer

    def embed(self, **kwargs):
        checkpoint('embedding_started',model=str(kwargs.get('model','')))
        start = perf_counter()
        try:
            return self.client.embed(**kwargs)
        finally:
            record_call(ModelOperation.EMBED, perf_counter() - start)

    def list(self):
        return self.client.list()

    def show(self, *args, **kwargs):
        return self.client.show(*args, **kwargs)

    def ps(self):
        return self.client.ps()

    def generate(self, **kwargs):
        """Administrative generation, used to unload models in benchmarks."""
        return self.client.generate(**kwargs)

    def close(self):
        self.client._client.close()


_clients = {}
_clients_lock = Lock()


def get_client(timeout=60):
    """Reuse the measured wrapper per host, timeout and Ollama credential scope.

    Request messages/options and metrics remain request-local. Different timeout
    profiles use separate connection pools without mutating a shared transport.
    """
    host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
    key = (host, timeout, os.getenv('OLLAMA_API_KEY'))
    with _clients_lock:
        if key not in _clients:
            _clients[key] = Client(timeout=timeout, host=host)
        return _clients[key]


def close_clients():
    """Close pooled transports at process shutdown or explicit service teardown."""
    with _clients_lock:
        clients = list(_clients.values())
        _clients.clear()
    for client in clients:
        client.close()


atexit.register(close_clients)
