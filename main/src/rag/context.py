from contextvars import ContextVar
active_document_filter=ContextVar('jenna_document_filter',default=None)
active_source_request=ContextVar('jenna_source_request',default=None)
