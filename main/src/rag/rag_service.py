from main.src.utils.enums import PromptName, ResultStatus, Role, SourceKind
from main.src.utils import regex_constants as rx
import re
import time
import json
import math
from main.src.tools.llm import get_client
import logging
import chromadb

from pathlib import Path
from sentence_transformers import CrossEncoder
from functools import lru_cache
from main.src.utils.common_utils import load_prompt
from main.src.utils.diagnostics import debug
from main.src.utils.constants import (
    JENNA_MEMORY,
    EMBEDDING_MODEL,
    RERANKER_MODEL,
    CHAT_MODEL,
    JENNA_DOCUMENTS_PATH,
    JENNA_DOCUMENT_CONFIGURATION,
)
from main.src.utils.schemas import REWRITE_SCHEMA, multi_queries_schema, EVIDENCE_SCHEMA, generate_answer_schema, \
    VERIFY_ANSWER_SCHEMA

# Logger
logger = logging.getLogger(__name__)
# Client
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(JENNA_MEMORY)
if not DB_PATH.is_absolute():
    DB_PATH = (BASE_DIR / "../.." / DB_PATH).resolve()
client = chromadb.PersistentClient(path=str(DB_PATH))

# collection
collection = client.get_or_create_collection(
    name=JENNA_DOCUMENTS_PATH,
    configuration=JENNA_DOCUMENT_CONFIGURATION
)

@lru_cache(maxsize=1)
def get_reranker():
    return CrossEncoder(RERANKER_MODEL)

MAX_BATCH_SIZE = client.get_max_batch_size()

def create_embeddings(texts, batch_size=16):
    if not isinstance(batch_size, int) or batch_size <= 0:
        raise ValueError("Require batch_size > 0")

    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("Embedding inputs must be nonempty strings")

    embeddings = []
    dimension = None

    for start in range(0, len(texts), batch_size):
        text = texts[start:start+batch_size]

        response = get_client().embed(
            model=EMBEDDING_MODEL,
            input=text
        )
        vectors = response["embeddings"]

        if len(vectors) != len(text):
            raise RuntimeError("Embedding inputs must have the same length")

        for vector in vectors:
            if not vector or not all(math.isfinite(value) for value in vector):
                raise RuntimeError("Invalid embedding vector")

            if not any(value != 0 for value in vector):
                raise RuntimeError("Zero embedding vector")

            if dimension is None:
                dimension = len(vector)
            elif len(vector) != dimension:
                raise RuntimeError("Invalid embedding vector")

            embeddings.append(vector)
    return embeddings


def create_embedding(text):
    return create_embeddings([text])[0]

def rewrite_search_query(question):
    response = get_client().chat(
        model=CHAT_MODEL,
        messages=[
            {
                "role": Role.SYSTEM,
                "content": load_prompt(PromptName.REWRITE),
            },
            {"role": Role.USER, "content": question},
        ],
        format=REWRITE_SCHEMA,
        options={"temperature": 0},
    )

    payload = json.loads(response["message"]["content"])

    if not isinstance(payload, dict) or set(payload) != {"query"}:
        raise ValueError("Invalid query-rewrite response.")

    query = payload["query"]

    if not isinstance(query, str):
        raise ValueError("Rewritten query must be text.")

    query = query.strip()

    if not query or len(query) > 1000:
        raise ValueError("Rewritten query has an invalid length.")

    return query

def generate_multi_queries(question, num_queries=2):
    if num_queries < 1:
        raise ValueError("num_queries must be positive")

    start = time.perf_counter()

    response = get_client().chat(
        model=CHAT_MODEL,
        format=multi_queries_schema(num_queries),
        options={"temperature": 0},
        messages=[{
            "role": Role.USER,
            "content": load_prompt(
                PromptName.MULTI_QUERIES,
                num_queries=num_queries,
                question=question,
            ),
        }],
    )

    alternatives = json.loads(
        response["message"]["content"]
    )["queries"]

    if (
            not isinstance(alternatives, list)
            or len(alternatives) != num_queries
            or any(
        not isinstance(query, str) or not query.strip()
        for query in alternatives
    )
    ):
        raise ValueError("Invalid generated search queries")

    # Always include the original question
    queries = [question] + [query.strip() for query in alternatives]

    # Remove duplicates
    queries = list(dict.fromkeys(queries))

    return queries, time.perf_counter() - start

def evidence_can_answer(question, results):
    if not results:
        return False

    sources = [
        {"source_id": index, "text": result["text"]}
        for index, result in enumerate(results)
    ]

    response = get_client().chat(
        model=CHAT_MODEL,
        format=EVIDENCE_SCHEMA,
        options={"temperature": 0},
        messages=[
            {
                "role": Role.SYSTEM,
                "content": load_prompt(PromptName.EVIDENCE),
            },
            {
                "role": Role.USER,
                "content": json.dumps({
                    "question": question,
                    "sources": sources,
                }),
            },
        ],
    )

    decision = json.loads(response["message"]["content"])

    debug("EVIDENCE DECISION:")
    debug(json.dumps(decision, indent=2))

    if decision.get("answerable") is not True:
        return False

    support = decision.get("support")

    if not isinstance(support, list) or not support:
        return False

    def normalize(text):
        return " ".join(text.casefold().split())

    for item in support:
        source_id = item.get("source_id")
        quote = item.get("quote")

        if (
            type(source_id) is not int
            or not 0 <= source_id < len(results)
            or not isinstance(quote, str)
            or not quote.strip()
        ):
            return False
        source_text = results[source_id]["text"]
        if normalize(quote) not in normalize(results[source_id]["text"]):
            debug("QUOTE VALIDATION FAILED")
            debug("Source ID:", source_id)
            debug("Generated quote:", repr(quote))
            debug("Source text:", repr(source_text))
            debug("Full decision:", json.dumps(decision, indent=2))
            return False

    debug("Evidence validation passed")
    return True

def plan_question_parts(question):
    """Preserve explicit question clauses without asking a model to omit any."""
    clauses = re.split(
        rx.QUESTION_CLAUSE_SEPARATOR,
        question, flags=re.I)
    if not 1 < len(clauses) <= 6:
        return [question]
    first = clauses[0].strip(" ,?")
    subject_match = re.search(rx.NAMED_SUBJECT, first)
    if not subject_match:
        subject_match = re.search(rx.WHAT_SUBJECT, first, re.I)
    subject = subject_match[1] if subject_match else None
    parts = [first + "?"]
    for clause in clauses[1:]:
        clause = clause.strip(" ,?")
        if subject:
            clause = re.sub(rx.POSSESSIVE_REFERENCE, subject + "'s", clause, flags=re.I)
            clause = re.sub(rx.PERSONAL_REFERENCE, subject, clause, flags=re.I)
        else:
            # The original question remains available as context to the selector.
            clause += " (in the context of the original question)"
        parts.append(clause[0].upper() + clause[1:] + "?")
    return parts


def table_relation_error(question, quote, source_text):
    """Check short table values against their labels without model knowledge."""
    fields = rx.TABLE_FIELD_PATTERNS
    requested = {field for field, pattern in fields.items() if re.search(pattern, question, re.I)}
    if not requested:
        return ""
    normalize = lambda value: " ".join(value.casefold().split())
    lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    matched_fields = set()
    for index, line in enumerate(lines):
        if normalize(line) == normalize(quote) and index:
            label = normalize(lines[index - 1]).strip(" :#")
            if label in fields:
                matched_fields.add(label)
        for field in fields:
            entry = re.fullmatch(rx.table_field_pattern(field), line, re.I)
            if entry and normalize(quote) in {normalize(line), normalize(entry[1])}:
                matched_fields.add(field)
    if matched_fields and not matched_fields & requested:
        return ("Selected table value describes " + ", ".join(sorted(matched_fields))
                + ", but the question asks about " + ", ".join(sorted(requested)) + ".")
    return ""


def generate_document_answer(
    question,
    results,
    system_prompt="",
    required_parts=None,
):
    def reject(status, reason=""):
        return {
            "answerable": False,
            "answer": "",
            "support": [],
            "status": status,
            "rejection_reason": reason or status.replace("_", " "),
        }

    if not results:
        return reject(ResultStatus.NO_CONTEXT)

    if required_parts is None:
        required_parts = [question]

    if (
        not isinstance(required_parts, list)
        or not required_parts
        or any(
            not isinstance(part, str) or not part.strip()
            for part in required_parts
        )
    ):
        raise ValueError("required_parts must contain nonempty strings")

    response = get_client().chat(
        model=CHAT_MODEL,
        format=generate_answer_schema(len(required_parts)),
        options={"temperature": 0},
        messages=[
            {
                "role": Role.SYSTEM,
                "content": system_prompt + "\n\n" + load_prompt(PromptName.GENERATE_DOCUMENT),
            },
            {
                "role": Role.USER,
                "content": json.dumps({
                    "question": question,
                    "required_parts": [
                        {"part_id": index, "question": part}
                        for index, part in enumerate(required_parts)
                    ],
                    "sources": [
                        {"source_id": index, "title": source.get("filename", ""),
                         "kind": source.get("kind", SourceKind.DOCUMENT), "text": source["text"]}
                        for index, source in enumerate(results)
                    ],
                }),
            },
        ],
    )

    try:
        draft = json.loads(response["message"]["content"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return reject("invalid_response")

    debug("PASSAGE SELECTION:")
    debug(json.dumps(draft, indent=2))

    if (
        not isinstance(draft, dict)
        or set(draft) != {"parts"}
        or not isinstance(draft["parts"], list)
        or len(draft["parts"]) != len(required_parts)
    ):
        return reject("invalid_response")

    def normalize(text):
        # Allow whitespace differences; preserve wording and case.
        return " ".join(text.split())

    selected_parts = {}
    all_support = []
    seen_support = set()

    for part in draft["parts"]:
        if (
            not isinstance(part, dict)
            or set(part) != {"part_id", "answerable", "support"}
            or type(part["part_id"]) is not int
            or not 0 <= part["part_id"] < len(required_parts)
            or part["part_id"] in selected_parts
            or type(part["answerable"]) is not bool
            or not isinstance(part["support"], list)
        ):
            return reject("invalid_response")

        part_id = part["part_id"]

        if not part["answerable"]:
            # A negative decision is always safe to abstain on; discard any
            # stray quotes rather than treating them as an answer.
            selected_parts[part_id] = None
            continue

        if not part["support"]:
            return reject(ResultStatus.INVALID_EVIDENCE)

        passages = []

        for item in part["support"]:
            if (
                not isinstance(item, dict)
                or set(item) != {"source_id", "quote"}
                or type(item["source_id"]) is not int
                or not isinstance(item["quote"], str)
                or not item["quote"].strip()
            ):
                return reject(ResultStatus.INVALID_EVIDENCE)

            quote = item["quote"].strip()

            matching_ids = [
                index
                for index, source in enumerate(results)
                if normalize(quote) in normalize(source["text"])
            ]

            if not matching_ids:
                debug("QUOTE NOT FOUND:", repr(quote))
                return reject(ResultStatus.INVALID_EVIDENCE)

            source_id = item["source_id"]

            if source_id not in matching_ids:
                corrected_id = matching_ids[0]
                debug(
                    "CORRECTED QUOTE SOURCE:",
                    source_id,
                    "->",
                    corrected_id,
                )
                source_id = corrected_id

            relation_error = table_relation_error(
                required_parts[part_id], quote, results[source_id]["text"])
            if relation_error:
                return reject(ResultStatus.INVALID_EVIDENCE, relation_error)

            if quote not in passages:
                passages.append(quote)

            key = (source_id, normalize(quote))

            if key not in seen_support:
                all_support.append({
                    "source_id": source_id,
                    "quote": quote,
                })
                seen_support.add(key)

        selected_parts[part_id] = passages

    expected_ids = set(range(len(required_parts)))

    if set(selected_parts) != expected_ids:
        return reject("missing_question_part")

    if any(passages is None for passages in selected_parts.values()):
        return reject(ResultStatus.INSUFFICIENT_EVIDENCE, "No supporting passage was selected for every required question part.")

    sections = []

    for part_id, question_part in enumerate(required_parts):
        passages = selected_parts[part_id]
        text = "\n\n".join(passages)

        if len(required_parts) > 1:
            sections.append(f"**{question_part}**\n\n{text}")
        else:
            sections.append(text)

    answer_text = "\n\n".join(sections)
    verdict = verify_document_answer(question, answer_text, all_support, results=results)
    if not verdict["supported"] or not verdict["complete"]:
        return reject(ResultStatus.INSUFFICIENT_EVIDENCE, verdict["reason"])

    return {
        "answerable": True,
        "answer": answer_text,
        "support": all_support,
        "status": ResultStatus.PASSAGES_VERIFIED,
    }


def verify_document_answer(question, answer, support, results=None):


    response = get_client().chat(
        model=CHAT_MODEL,
        format=VERIFY_ANSWER_SCHEMA,
        options={"temperature": 0},
        messages=[
            {
                "role": Role.SYSTEM,
                "content": load_prompt(PromptName.VERIFY_ANSWER),
            },
            {
                "role": Role.USER,
                "content": json.dumps({
                    "question": question,
                    "answer": answer,
                    "quotations": [
                        item["quote"] for item in support
                    ],
                    "source_contexts": [
                        {"source_id": source_id,
                         "title": results[source_id].get("filename", ""),
                         "text": results[source_id]["text"]}
                        for source_id in sorted({item["source_id"] for item in support})
                    ] if results else [],
                }),
            },
        ],
    )

    try:
        verdict = json.loads(response["message"]["content"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return {
            "supported": False,
            "complete": False,
            "reason": "Invalid verification response",
        }

    if (
        not isinstance(verdict, dict)
        or set(verdict) != {"supported", "complete", "reason"}
        or type(verdict["supported"]) is not bool
        or type(verdict["complete"]) is not bool
        or not isinstance(verdict["reason"], str)
    ):
        return {
            "supported": False,
            "complete": False,
            "reason": "Invalid verification response",
        }

    return verdict
