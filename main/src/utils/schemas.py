"""Owned model JSON schemas, REST models, MCP types and dynamic schema builders."""
from typing import Annotated, Literal, Any
from pydantic import BaseModel, Field, ConfigDict
from main.src.utils.enums import Connection, Role
from main.src.utils import regex_constants as rx
from main.src.utils.enums import Action, FollowupStatus, Intent, ResultStatus, SearchMode
ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                Action.SEARCH_DOCUMENTS,
                Action.CALCULATOR,
                Action.LIST_DOCUMENTS,
                Action.ANSWER_DIRECTLY,
                Action.SEARCH_AND_CALCULATE,
            ],
        },
        "expression": {"type": "string"},
    },
    "required": ["action", "expression"],
    "additionalProperties": False,
}

CALCULATION_PLAN_SCHEMA = {
    'type': 'object',
    'properties': {
        'ready': {'type': 'boolean'},
        'expression': {'type': 'string', 'maxLength': 200},
        'explanation': {'type': 'string', 'maxLength': 1500},
        'clarification': {'type': 'string', 'maxLength': 500},
    },
    'required': ['ready', 'expression', 'explanation', 'clarification'],
    'additionalProperties': False,
}

REWRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
    },
    "required": ["query"],
    "additionalProperties": False,
}

EVIDENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "answerable": {"type": "boolean"},
        "support": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "integer"},
                    "quote": {"type": "string"},
                },
                "required": ["source_id", "quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answerable", "support"],
    "additionalProperties": False,
}

VERIFY_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "supported": {"type": "boolean"},
        "complete": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["supported", "complete", "reason"],
    "additionalProperties": False,
}

PDF_VISUAL_VERIFY_SCHEMA = {
    'type': 'object',
    'properties': {'reason': {'type': 'string', 'maxLength': 1600}, 'supported': {'type': 'boolean'}},
    'required': ['reason', 'supported'],
    'additionalProperties': False,
}

RESOLVE_FOLLOWUP_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": [
                FollowupStatus.STANDALONE,
                FollowupStatus.RESOLVED,
                ResultStatus.NEEDS_CLARIFICATION,
            ],
        },
        "question": {"type": "string"},
        "clarification": {"type": "string"},
    },
    "required": ["status", "question", "clarification"],
    "additionalProperties": False,
}

SEARCH_AND_CALC_SCHEMA = {
    "type": "object",
    "properties": {
        "ready": {"type": "boolean"},
        "expression": {"type": "string"},
    },
    "required": ["ready", "expression"],
    "additionalProperties": False,
}

STATE_SCHEMA = {
    'type': 'object',
    'properties': {
        'goal': {
            'type': 'string',
            'maxLength': 1000
        },
        'constraints': {
            'type': 'array',
            'items': {
                'type': 'string',
                'maxLength': 300
            },
            'maxItems': 12
        },
        'references': {
            'type': 'array',
            'items': {
                'type': 'string',
                'maxLength': 500
            },
            'maxItems': 12
        }
    },
    'required': ['goal', 'constraints', 'references'],
    'additionalProperties': False
}

def multi_queries_schema(num_queries: int) -> dict:
    return {
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": num_queries,
                "maxItems": num_queries,
            }
        },
        "required": ["queries"],
        "additionalProperties": False,
    }

def generate_answer_schema(required_parts: int) -> dict:
    return {
        "type": "object",
        "properties": {
            "parts": {
                "type": "array",
                "minItems": required_parts,
                "maxItems": required_parts,
                "items": {
                    "type": "object",
                    "properties": {
                        "part_id": {"type": "integer"},
                        "answerable": {"type": "boolean"},
                        "support": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "source_id": {"type": "integer"},
                                    "quote": {"type": "string"},
                                },
                                "required": ["source_id", "quote"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": [
                        "part_id",
                        "answerable",
                        "support",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["parts"],
        "additionalProperties": False,
    }

def generate_passage_choice_schema(required_parts: int, passage_count: int) -> dict:
    schema = generate_answer_schema(required_parts)
    support = schema['properties']['parts']['items']['properties']['support']
    support['maxItems'] = 4
    support['uniqueItems'] = True
    support['items'] = {
        'type': 'integer', 'minimum': 0, 'maximum': passage_count - 1,
    }
    return schema


def assistant_schema(names: list[str]) -> dict:
    return {
        'type': 'object',
        'properties': {
            'connection': {
                'type': 'string',
                'enum': names
            },
            'mode': {
                'type': 'string',
                'enum': [mode.value for mode in SearchMode]
            },
            'question': {
                'type': 'string',
                'maxLength': 4000
            },
            'clarification': {
                'type': 'string',
                'maxLength': 500
            },
            'intent': {
                'type': 'string',
                'enum': [intent.value for intent in Intent]
            },
            'memory_key': {
                'type': 'string',
                'maxLength': 80
            },
            'memory_value': {
                'type': 'string',
                'maxLength': 1000
            },
            'state': STATE_SCHEMA
        },
        'required': [
            'connection',
            'mode',
            'question',
            'clarification',
            'intent',
            'memory_key',
            'memory_value',
            'state'
        ],
        'additionalProperties': False
    }

GROUNDED_VERIFY_SCHEMA = {'type': 'object', 'properties': {'supported': {'type': 'boolean'}, 'complete': {'type': 'boolean'},
               'reason': {'type': 'string'}}, 'required': ['supported', 'complete', 'reason'], 'additionalProperties': False}


GROUNDED_SUMMARY_SCHEMA = {'type': 'object', 'properties': {'answer': {'type': 'string'},
              'source_ids': {'type': 'array', 'items': {'type': 'integer'}, 'minItems': 1}},
              'required': ['answer', 'source_ids'], 'additionalProperties': False}


MCP_VERIFY_SCHEMA = {'type': 'object', 'properties': {'reason': {'type': 'string'},
                 'supported': {'type': 'boolean'}, 'complete': {'type': 'boolean'}},
                 'required': ['supported', 'complete', 'reason'], 'additionalProperties': False}


MCP_REPAIR_SCHEMA = {'type': 'object', 'properties': {'answer': {'type': 'string'}},
                                 'required': ['answer'], 'additionalProperties': False}


DISCOVER_TOOLS_SCHEMA = {'type':'object','properties':{'query':{'type':'string'}},'required':['query'],'additionalProperties':False}


MCP_PLAN_SCHEMA = {
    'type': 'object', 'properties': {
        'action': {'type': 'string', 'enum': ['call_tool', 'answer']},
        'tool_name': {'type': 'string'}},
    'required': ['action', 'tool_name'], 'additionalProperties': False}


MCP_ANSWER_SCHEMA = {'type': 'object', 'properties': {'supported': {'type': 'boolean'}, 'answer': {'type': 'string'}},
                 'required': ['supported', 'answer'], 'additionalProperties': False}


class Calculation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expression:str=Field(min_length=1,max_length=200)
    value:float=Field(strict=True,allow_inf_nan=False)


class Message(BaseModel):
    model_config=ConfigDict(extra='forbid')
    role:Literal[Role.USER,Role.ASSISTANT]
    content:str=Field(max_length=12000)
    connection:str|None=Field(default=None,max_length=80)
    status:str|None=Field(default=None,max_length=80)
    answer_kind:str|None=Field(default=None,max_length=80)
    conversation_state:dict|None=None
    passages:list[dict]=Field(default_factory=list,max_length=16)
    results:list[dict]=Field(default_factory=list,max_length=40)
    support:list[dict]=Field(default_factory=list,max_length=40)
    mcp_evidence:list[dict]=Field(default_factory=list,max_length=40)
    tools_used:list[str]=Field(default_factory=list,max_length=40)
    calculation:Calculation|None=None

class Ask(BaseModel):
    model_config=ConfigDict(extra='forbid')
    question:str=Field(min_length=1,max_length=4000)
    connection:str=Field(default=Connection.AUTO,max_length=80)
    mode:Literal[SearchMode.AUTO,SearchMode.DOCUMENTS,SearchMode.WEB,SearchMode.DOCUMENTS_AND_WEB]=SearchMode.AUTO
    timeout:float=Field(default=180,ge=1,le=600)
    history:list[Message]=Field(default_factory=list,max_length=100)
    filters:dict|None=None
    session_id:str|None=Field(default=None,pattern=rx.SESSION_ID)


Question = Annotated[str, Field(min_length=1, max_length=4000)]
Expression = Annotated[str, Field(min_length=1, max_length=200)]
TopK = Annotated[int, Field(strict=True, ge=1, le=20)]
MemoryKey = Annotated[str, Field(min_length=1, max_length=80)]
MemoryValue = Annotated[str, Field(min_length=1, max_length=1000)]
SourceMode = Literal[SearchMode.DOCUMENTS, SearchMode.AUTO, SearchMode.WEB, SearchMode.DOCUMENTS_AND_WEB]
ChatId = Annotated[str, Field(pattern=rx.CHAT_ID)]
ChatLimit = Annotated[int, Field(strict=True, ge=1, le=100)]


def mcp_selection_schema(names):
    return {**MCP_PLAN_SCHEMA, 'properties': {**MCP_PLAN_SCHEMA['properties'],
            'tool_name': {'type': 'string', 'enum': ['', *names]}}}


def mcp_tool_definition(name, description, input_schema):
    """Wrap a discovered schema without changing its server-provided constraints."""
    return {'type': 'function', 'function': {
        'name': name, 'description': description or '', 'parameters': input_schema}}


def discovery_tool_definition():
    from main.src.utils.instructions import DISCOVER_TOOLS_DESCRIPTION
    return mcp_tool_definition('discover_tools', DISCOVER_TOOLS_DESCRIPTION, DISCOVER_TOOLS_SCHEMA)
