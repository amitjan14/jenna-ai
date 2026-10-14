"""Runtime regex definitions; call sites retain flags and capture-group behavior.

Dynamic builders escape literal identifiers rather than accepting regex fragments.
"""
import re

SESSION_ID = r'^[A-Za-z0-9_-]{1,80}$'
CHAT_ID = r'^[a-f0-9]{32}$'
PRIVATE_DOCUMENT_SCOPE = r'\b(?:from|in|according to)\s+(?:my|our|the uploaded)\s+(?:pdfs?|documents?|notes?)\b'
REQUEST_IDENTIFIER = r'https?://[^\s<>]+|\b[\w.-]+\.pdf\b|\b[A-Z][A-Z0-9_]*-\d+\b'
REQUEST_ANCHOR = REQUEST_IDENTIFIER + r'|\d+(?:\.\d+)?'
LOCAL_ONLY_REQUEST = r'\b(?:offline|local only)\b'
CONTEXT_WORD = r'\w{3,}'
CITATION_MARKER = r'\[(\d+)\]'
MEMORY_SAVE_REQUEST = r'\b(?:remember|save|store|retain)\b|keep (?:this|that|it|in mind)|make (?:a )?note'
MEMORY_DELETE_REQUEST = r'\b(?:forget|delete|remove|erase)\b|stop remembering'
DOCUMENT_REFERENCE = r'\b(?:notes|documents?|pdfs?)\b'
SEARCH_REQUEST = r'\b(?:find|search|retrieve|look up)\b'
CALCULATION_REQUEST = r'\b(?:calculate|compute|evaluate)\b'
DOCUMENT_INVENTORY_REFERENCE = r'\b(documents?|pdfs?|files?|filenames?)\b'
DOCUMENT_INVENTORY_REQUEST = r'\b(list|filenames?|how many|count)\b|\b(?:what|which)\s+(?:documents?|pdfs?|files?)\s+(?:are|have)\b'
DOCUMENT_CONTENT_FILTER = r'\b(about|discuss(?:es|ing)?|contain(?:s|ing)?|mention(?:s|ing)?|cover(?:s|ing)?)\b'
CALCULATOR_INTENT = r'\b(?:calculate|compute|evaluate|plus|minus|times|divide|multiply|subtract|sum|sqrt|square root|percent|average|mean|bmi|body mass index)\b|[%+*/]'
INLINE_CODE = r'```|\bdef\s+\w+\s*\(|\bfunction\s+\w+\s*\(|Traceback \(most recent call last\)'
CODE_HELP_REQUEST = r'\b(?:debug|fix|repair|explain|review|refactor|correct)\b'
CODE_SOURCE_REQUEST = r'\b(?:jira|confluence|uploaded|pdfs?|documents?)\b|\b(?:search|browse|look up)\b|\b(?:from|in|according to)\s+(?:my|our)\s+notes\b'
CLARIFICATION_CHOICES = r'\s*Do you mean (.+?) or (.+?)\?\s*'
FOLLOWUP_REFERENCE = r'\b(?:it|one|they|them|that|this)\b'
MULTIPART_CONJUNCTION = r'\b(?:and|;)\b'
NAMED_SUBJECT_QUESTION = r'\b(?:does|do|is|are)\s+[A-Z][a-zA-Z]+'
QUESTION_PREFIX = r'^(?:what|who|where|when|why|how|explain|describe|compare|calculate|list|show)\b'
MULTIPART_REQUEST = r'\b(?:and|compare|differ)\b'
PRIVATE_SOURCE_REFERENCE = r'\b(?:my|our|uploaded|pdfs?|documents?|notes?)\b|according to'
QUESTION_CLAUSE_SEPARATOR = r'(?:,\s*)?\band\s+(?=(?:what|who|where|when|why|how|can|does|do|is|are|should|could|would)\b)|;\s*(?=(?:what|who|where|when|why|how)\b)'
NAMED_SUBJECT = r'\b(?:does|do|is|are)\s+([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)'
WHAT_SUBJECT = r'^what (?:is|are) (.+)$'
POSSESSIVE_REFERENCE = r'\b(?:its|their)\b'
PERSONAL_REFERENCE = r'\b(?:it|they|them)\b'
NUMBER = r'(-?\d+(?:\.\d+)?)'
ARITHMETIC_ROOT = r'(?:calculate|compute|what is)\s+(?:the\s+)?square root of\s+' + NUMBER
ARITHMETIC_PERCENTAGE = r'(?:calculate|compute|what is)\s+' + NUMBER + r'\s*%\s+of\s+' + NUMBER
ARITHMETIC_PREFIX = r'^(?:calculate|compute|evaluate|what is)\s+'
ARITHMETIC_EXPRESSION = r'[\d\s.+*/%()\-]+'
COSINE_FORMULA = r'cos\s*\(\s*a\s*,\s*b\s*\)\s*=\s*\(\s*a\s*[·⋅]\s*b\s*\)\s*/\s*\(\s*\|\|\s*a\s*\|\|\s*\|\|\s*b\s*\|\|\s*\)'
COSINE_FORMULA_PROSE = r'cosine similarity formula is\s+dot\(\s*A\s*,\s*B\s*\)\s+divided by the product of the vector norms'
COSINE_REQUEST = r'\bcosine\s+similarity\b'
SPEECH_CONTROL = r'\[\[.*?]]'
FENCED_CODE = r'```.*?```'
MARKDOWN_LINK = r'\[([^]]+)]\([^)]+\)'
MARKDOWN_HEADING = r'(?m)^\s*#{1,6}\s*'
SPEECH_LINE_BREAK = r'\n+'
MARKDOWN_LINK_REPLACEMENT = r'\1'
CAMEL_CASE_REPLACEMENT = r'\1 \2'

DIRECT_CONVERSATION_PATTERNS = (
    r'(?:hi|hello|hey)(?: jenna)?', r'good (?:morning|afternoon|evening)(?: jenna)?',
    r'(?:thanks|thank you)(?: jenna)?', r'how are you(?: doing)?(?: jenna)?',
    r'what can you do', r'what are your capabilities', r'how can you help(?: me)?', r'who are you',
)
CONTEXT_REFERENCE_PATTERNS = (
    r'\b(?:it|its|they|them|their|those|these)\b', r'\b(?:this|that)\s*[.!?]*$',
    r'\b(?:this|that)\s+(?:model|tool|approach|method|answer|document|concept|result|calculation)\b',
    r'\b(?:one|ones)\s*[.!?]*$', r'^(?:explain|expand|elaborate|continue|summarize|simplify)\s*[.!?]*$',
    r'^(?:tell me more|give me an example|give another example|why|why not)\s*[.!?]*$',
    r'^(?:make|keep)\s+(?:it\s+)?(?:shorter|simpler|more detailed)\b', r'^(?:and|also)\b',
)
TABLE_FIELD_PATTERNS = {
    'capital':r'\bcapital\b', 'currency':r'\bcurrenc(?:y|ies)\b', 'population':r'\bpopulation\b',
    'area':r'\barea\b', 'language':r'\blanguages?\b', 'owner':r'\b(?:owner|owns|owned)\b',
    'port':r'\bports?\b', 'version':r'\bversions?\b',
}


def vector_pattern(label):
    return r'\b' + re.escape(label) + r'\s*=\s*(\[[^\[\]]*\])'


def exact_anchor_pattern(value):
    return r'(?<![\w])' + re.escape(value) + r'(?![\w])'


def identifier_pattern(value):
    return r'(?<![\w-])' + re.escape(value) + r'(?![\w-])'


def typed_id_pattern(key, value):
    return r'\b' + re.escape(key[:-2]) + r'\s*(?:id\s*)?[#:]?\s*' + re.escape(value) + r'\b'


def table_field_pattern(field):
    return r'\s*' + re.escape(field) + r'\s*[:\-]?\s+(.{1,100})'

# Retrieval, Jira and tracing patterns.
WORD = '\\w+'
SEARCH_TERM = '[a-z0-9]{3,}'
PARAGRAPH_BREAK = '\\n\\s*\\n'
JIRA_PERSON_WORK = '\\b(?:what|which)\\s+(?:is|are)\\s+(.+?)\\s+(?:currently\\s+)?working\\s+on\\b'
JIRA_OWN_WORK = '\\b(?:my|our)\\s+(?:current\\s+|active\\s+)?(?:work|tasks|issues)\\b'
JIRA_OUR_WORK = '\\bour\\b'
JIRA_MY_WORK = '\\b(?:what\\s+am\\s+i|what\\s+am\\s+I)\\s+(?:currently\\s+)?working\\s+on'
JIRA_PROJECT = '\\b(?:project|in)\\s+([A-Z][A-Z0-9_]{1,15})\\b'
JIRA_ISSUE_KEY = '[A-Za-z][A-Za-z0-9_]*-\\d+'
JIRA_SPRINT = '\\bspr(?:int|imt)s?\\b'
JIRA_ACTIVE = '\\b(?:active|current|ongoing|running)\\b'
JIRA_IN_SPRINT = '\\b(?:we|i)\\s+(?:are\\s+)?in\\b'
JIRA_WORK_DETAIL = '\\b(?:issues|tasks|assignee|assigned|working)\\b'
JIRA_PROJECT_FOR = '\\b(?:project|in|for)\\s+([A-Z][A-Z0-9_]{1,15})\\b'
JIRA_BOARD = '\\bboard\\s+(\\d+)\\b'
JIRA_ISSUE_KEY_REFERENCE = '\\b[A-Za-z][A-Za-z0-9_]*-\\d+\\b'
JIRA_RELATED_ISSUE_REQUEST = '\\b(?:sprint|sprimt|board|compare|related|linked)\\b'
JIRA_ISSUE_DETAIL = '\\b(?:due|date|status|summary|details|show|tell|about|when)\\b'
SECRET_FIELD = 'token|secret|password|authorization|api.?key|cookie'
AUTH_HEADER = '(?i)(bearer|basic)\\s+\\S+'
TOOL_TOKEN = '[a-z0-9_]+'
CAMEL_CASE_BOUNDARY = '([a-z])([A-Z])'
HISTORY_IDENTIFIER = '\\b[A-Z][A-Z0-9_]+-\\d+\\b|https://[^\\s<>]+|\\b\\d{4}-\\d{2}-\\d{2}\\b'
