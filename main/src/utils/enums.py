"""Shared string-valued domains. Values are stable JSON/database/API contracts.

Use enums for finite categories; model names, limits and environment settings stay
in constants.py. StrEnum preserves string comparison, hashing and serialization.
"""
from enum import StrEnum, unique


@unique
class SearchMode(StrEnum):
    AUTO = 'Auto'
    DOCUMENTS = 'Documents'
    WEB = 'Web'
    DOCUMENTS_AND_WEB = 'Documents + Web'


@unique
class Connection(StrEnum):
    AUTO = 'auto'
    LOCAL = 'local'


@unique
class Intent(StrEnum):
    TASK = 'task'
    CHAT = 'chat'
    REWRITE = 'rewrite'
    MEMORY_READ = 'memory_read'
    MEMORY_WRITE = 'memory_write'
    MEMORY_DELETE = 'memory_delete'


@unique
class Role(StrEnum):
    USER = 'user'
    ASSISTANT = 'assistant'
    SYSTEM = 'system'
    TOOL = 'tool'


@unique
class Action(StrEnum):
    CONVERSATION = 'conversation'
    REWRITE = 'rewrite'
    MEMORY = 'memory'
    SEARCH_DOCUMENTS = 'search_documents'
    SEARCH_WEB = 'search_web'
    CALCULATOR = 'calculator'
    LIST_DOCUMENTS = 'list_documents'
    ANSWER_DIRECTLY = 'answer_directly'
    SEARCH_AND_CALCULATE = 'search_and_calculate'
    COSINE_SIMILARITY = 'cosine_similarity'
    REMEMBER_NOTE = 'remember_note'
    RECALL_NOTE = 'recall_note'
    FORGET_NOTE = 'forget_note'
    LIST_NOTES = 'list_notes'


@unique
class ResultStatus(StrEnum):
    NEEDS_CLARIFICATION = 'needs_clarification'
    INSUFFICIENT_EVIDENCE = 'insufficient_evidence'
    INVALID_EVIDENCE = 'invalid_evidence'
    INVALID_REQUEST = 'invalid_request'
    INVALID_SEARCH_MODE = 'invalid_search_mode'
    CONVERSATION_COMPLETED = 'conversation_completed'
    PASSAGES_VERIFIED = 'passages_verified'
    REVISION_REJECTED = 'revision_rejected'
    MEMORY_COMPLETED = 'memory_completed'
    ANSWERED = 'answered'
    PARTIAL_ANSWER = 'partial_answer'
    RETRIEVAL_UNAVAILABLE = 'retrieval_unavailable'
    NO_CONTEXT = 'no_context'
    INVALID_CALCULATION_REQUEST = 'invalid_calculation_request'
    CALCULATION_ERROR = 'calculation_error'
    CALCULATION_COMPLETED = 'calculation_completed'
    EXECUTION_ERROR = 'execution_error'
    MEMORY_ERROR = 'memory_error'
    INVALID_MEMORY_REQUEST = 'invalid_memory_request'
    RESOLUTION_ERROR = 'resolution_error'
    RETRY_ERROR = 'retry_error'
    ROUTING_ERROR = 'routing_error'
    TOOL_COMPLETED = 'tool_completed'
    SKIPPED_UNCHANGED_QUERY = 'skipped_unchanged_query'
    CONNECTED = 'connected'


@unique
class ExecutionStatus(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    TIMED_OUT = 'timed_out'


@unique
class FollowupStatus(StrEnum):
    STANDALONE = 'standalone'
    RESOLVED = 'resolved'


@unique
class AnswerKind(StrEnum):
    CONVERSATION = 'conversation'
    REWRITE = 'rewrite'
    GROUNDED_SUMMARY = 'grounded_summary'
    GROUNDED_REWRITE = 'grounded_rewrite'


@unique
class SearchDepth(StrEnum):
    BASIC = 'basic'
    ADVANCED = 'advanced'


@unique
class ModelOperation(StrEnum):
    CHAT = 'chat'
    EMBED = 'embed'
    RERANK = 'rerank'


@unique
class ChunkingStrategy(StrEnum):
    WORDS = 'words'
    SECTIONS = 'sections'


@unique
class PdfParser(StrEnum):
    LAYOUT = 'layout'
    PYPDF = 'pypdf'


@unique
class Transport(StrEnum):
    STDIO = 'stdio'
    STREAMABLE_HTTP = 'streamable-http'


@unique
class AuthType(StrEnum):
    NONE = 'none'
    OAUTH = 'oauth'
    BEARER = 'bearer'
    BASIC = 'basic'


@unique
class SourceKind(StrEnum):
    DOCUMENT = 'document'
    WEB = 'web'
    MEMORY = 'memory'
    MCP = 'mcp'


@unique
class PromptName(StrEnum):
    MCP_LEGACY_ANSWER = 'mcp_legacy_answer_instructions'
    MCP_LEGACY_PLAN = 'mcp_legacy_plan_instructions'
    MCP_REPAIR = 'mcp_repair_instructions'
    MCP_VERIFY = 'mcp_verify_instructions'
    MCP_AGENT = 'mcp_agent_instructions'
    GROUNDED_SUMMARY = 'grounded_summary_instructions'
    GROUNDED_VERIFY = 'grounded_verify_instructions'
    ASSISTANT = 'assistant_instructions'
    PERSONALITY = 'jenna_personality'
    ROUTING = 'routing_instructions'
    RUN_AGENT = 'run_agent_instructions'
    REWRITE = 'rewrite_instructions'
    MULTI_QUERIES = 'multi_queries_instruction'
    GENERATE_DOCUMENT = 'generate_document_instructions'
    GENERATE_REPLY = 'generate_reply_instructions'
    RESOLVE_FOLLOWUP = 'resolve_followup_instructions'
    EVIDENCE = 'evidence_instructions'
    VERIFY_ANSWER = 'verify_answer_instructions'
    PDF_VISION = 'pdf_vision_instructions'
    PDF_VISUAL_VERIFY = 'pdf_visual_verify_instructions'
    SEARCH_AND_CALCULATE = 'search_and_calc_instructions'
    CALCULATION_PLAN = 'calculation_plan_instructions'
    ONLINE_SEARCH = 'online_search_instructions'
