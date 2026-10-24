from main.src.utils.enums import Action, PromptName, ResultStatus, SearchDepth, SourceKind
import json
from main.src.utils.environment import tavily_api_key

from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from main.src.rag.document_store import search_documents
from main.src.rag.rag_service import plan_question_parts, generate_document_answer
from main.src.utils.common_utils import load_prompt, make_result
from main.src.utils.constants import CANDIDATE_K, CONTEXT_K
from main.src.utils.diagnostics import debug


class WebSearchError(RuntimeError):
    pass


def search_web(question, max_results=4, search_depth=SearchDepth.BASIC):
    if search_depth not in {SearchDepth.BASIC, SearchDepth.ADVANCED}:
        raise ValueError("Search depth must be basic or advanced")
    api_key = tavily_api_key()

    if not api_key:
        raise WebSearchError(
            "TAVILY_API_KEY is missing. Set it in the environment or project .env file."
        )

    if not isinstance(question, str) or not question.strip():
        raise WebSearchError("The search question is empty.")

    if len(question) > 2000:
        raise WebSearchError("The search question is too long.")

    payload = {
        "query": question, "search_depth": search_depth, "max_results": max_results,
        "include_answer": False, "include_raw_content": False,
    }
    if search_depth == SearchDepth.ADVANCED:
        payload["chunks_per_source"] = 3

    request = Request(
        "https://api.tavily.com/search",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            body = response.read(2_000_001)

        if len(body) > 2_000_000:
            raise WebSearchError("Web-search response was too large.")

        payload = json.loads(body)

    except HTTPError as error:
        raise WebSearchError(
            f"Web search returned HTTP {error.code}. "
            "Check your key, quota, or service availability."
        ) from None

    except (URLError, TimeoutError):
        raise WebSearchError(
            "Web search could not connect or timed out."
        ) from None

    except (json.JSONDecodeError, UnicodeDecodeError):
        raise WebSearchError(
            "Web search returned an invalid response."
        ) from None

    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("results"), list)
    ):
        raise WebSearchError("Web-search results were malformed.")

    retrieved_at = datetime.now(timezone.utc).isoformat()
    sources = []
    seen_urls = set()

    for item in payload["results"]:
        if not isinstance(item, dict):
            continue

        url = item.get("url")
        content = item.get("content")
        title = item.get("title") or "Web source"

        if not isinstance(url, str) or not isinstance(content, str):
            continue

        if (
            not content.strip()
            or any(character.isspace() for character in url)
            or "<" in url
            or ">" in url
        ):
            continue

        try:
            parsed = urlsplit(url)

            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
            ):
                continue
        except ValueError:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(url)

        sources.append({
            "kind": SourceKind.WEB,
            "filename": str(title),
            "url": url,
            "page": None,
            "chunk_index": len(sources),
            "text": content.strip()[:4000 if search_depth == SearchDepth.ADVANCED else 3000],
            "retrieved_at": retrieved_at,
        })

        if len(sources) >= max_results:
            break

    return sources

def run_online_search(question, mode, system_prompt):
    sources, tools_used, notices, attempts = [], [], [], []
    if mode == "hybrid":
        tools_used.append(Action.SEARCH_DOCUMENTS)
        try:
            for source in search_documents(question, n_results=CANDIDATE_K,
                    max_chunks=CONTEXT_K, hybrid=True, multi_query=False):
                sources.append({**source, "kind": SourceKind.DOCUMENT})
        except Exception as error:
            debug("LOCAL SEARCH ERROR:", type(error).__name__)
            notices.append("Document search failed; only web results are available.")

    def fetch_web(depth):
        tools_used.append(Action.SEARCH_WEB)
        try:
            web_results = search_web(question, search_depth=depth)
        except WebSearchError as error:
            notices.append(str(error))
            return False
        except Exception as error:
            debug("WEB SEARCH ERROR:", type(error).__name__)
            notices.append("Web search failed unexpectedly.")
            return False
        # A deeper search can replace a shorter excerpt at the same URL.
        # Each new selection uses the refreshed source list, keeping IDs valid.
        for source in web_results:
            matching = next((i for i, old in enumerate(sources)
                             if old.get("url") == source.get("url")), None)
            if matching is None:
                sources.append(source)
            else:
                sources[matching] = source
        return True

    evidence_prompt = system_prompt + load_prompt(PromptName.ONLINE_SEARCH)
    required_parts = plan_question_parts(question)

    def select_answer(depth):
        selected = generate_document_answer(question, sources,
            system_prompt=evidence_prompt, required_parts=required_parts)
        attempts.append({"depth": depth, "source_count": len(sources),
                         "status": selected["status"],
                         "reason": selected.get("rejection_reason", "")})
        return selected

    web_available = fetch_web(SearchDepth.BASIC)
    document_answer = select_answer(SearchDepth.BASIC) if sources else {
        "answerable": False, "status": ResultStatus.NO_CONTEXT, "support": [], "answer": "",
        "rejection_reason": "Web search returned no usable excerpts."}
    if not document_answer["answerable"] and web_available:
        notices.append("Initial web excerpts were insufficient; tried a deeper web search.")
        if fetch_web(SearchDepth.ADVANCED) and sources:
            document_answer = select_answer(SearchDepth.ADVANCED)

    if document_answer["answerable"]:
        answer, support = document_answer["answer"], document_answer["support"]
        status = document_answer["status"]
    else:
        answer = ("The retrieved sources don't provide enough evidence."
                  if sources else "I couldn't obtain evidence for this question.")
        support = []
        status = document_answer["status"] if sources else ResultStatus.RETRIEVAL_UNAVAILABLE

    result = make_result(answer, status, mode, tools_used=tools_used,
                         results=sources, support=support)
    result["notices"] = notices
    result["web_attempts"] = attempts
    if not document_answer["answerable"]:
        result["rejection_reason"] = document_answer.get("rejection_reason", "")
        result["retrieved_sources"] = sources
    return result
