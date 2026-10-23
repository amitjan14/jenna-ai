import json
import math
import asyncio


def precision_at_k(retrieved, relevant, k):
    if not relevant or not retrieved or k <= 0:
        return 0

    top_k = retrieved[:min(k, len(retrieved))]
    retrieved_relevant = set(top_k) & set(relevant)

    return len(retrieved_relevant) / len(top_k)

def recall(retrieved, relevant, k):
    if not relevant or not retrieved or k <= 0:
        return 0

    top_k = retrieved[:min(k, len(retrieved))]
    retrieved_relevant = set(top_k) & set(relevant)

    return len(retrieved_relevant) / len(relevant)

def rr(retrieved, relevant):
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1 / rank

    return 0

def mrr(query_results):
    results = []
    for retrieved, relevant in query_results:
        results.append(rr(retrieved, relevant))

    return sum(results)/ len(results)

def deduplicate(vector_results, bm25_results):
    seenValue = set()
    for bm25 in vector_results:
        if bm25 not in seenValue:
            seenValue.add(bm25)

    for bm25 in bm25_results:
        if bm25 not in seenValue:
            seenValue.add(bm25)

    return seenValue

def rrf(vector_results, bm25_results, k=60):
    results = {}

    for ranked_list in (vector_results, bm25_results):
        for rank, doc in enumerate(ranked_list, start=1):
            score = 1 / (k + rank)
            results[doc] = results.get(doc, 0) + score

    return sorted(results.items(), key=lambda x: x["rrf_score"], reverse=True)

def filter_rag(results, threshold=0.5):
    unique_results = {}

    for result in results:
        chunk_id = result["chunk_id"]
        score = result["score"]

        if score < threshold:
            continue

        if (
            chunk_id not in unique_results
            or score > unique_results[chunk_id]["score"]
        ):
            unique_results[chunk_id] = result

    return sorted(
        unique_results.values(),
        key=lambda x: x["score"],
        reverse=True
    )

def filter_rag_text(results, threshold=0.5):
    unique_results = {}

    for result in results:
        chunk_id = result["chunk_id"]
        text = result["text"]
        score = result["score"]

        if score is None:
            continue

        if score < threshold:
            continue

        if not text.strip():
            continue

        if (
            chunk_id not in unique_results
            or score > unique_results[chunk_id]["score"]
        ):
            unique_results[chunk_id] = result

    return sorted(
        unique_results.values(),
        key=lambda x: x["score"],
        reverse=True
    )

def filter_rag_budget(results, budget=800):
    sortedList = sorted(
        results,
        key=lambda x: x["score"],
        reverse=True
    )

    budgetList = []
    for result in sortedList:
        if result["tokens"] <= budget:
            budgetList.append(result)
            budget -= result["tokens"]

    return budgetList

def rank_chunks(chunks):
    return sorted(
        chunks,
        key=lambda x: (-x["score"], x["tokens"])
    )

def prepare_context(chunks, threshold=0.5, budget=700):
    unique_results = {}

    for result in chunks:
        chunk_id = result["chunk_id"]
        score = result["score"]

        if score < threshold:
            continue

        if (
                chunk_id not in unique_results
                or score > unique_results[chunk_id]["score"]
        ):
            unique_results[chunk_id] = result

    sortedList =  sorted(
        unique_results.values(),
        key=lambda x: x["score"],
        reverse=True
    )

    budgetList = []
    for result in sortedList:
        if result["tokens"] <= budget:
            budgetList.append(result)
            budget -= result["tokens"]

    return budgetList

def safe_filter(results, threshold=0.5):
    unique_results = {}

    for result in results:
        chunk_id = result.get("chunk_id")
        score = result.get("score")

        if not isinstance(chunk_id, str) or not chunk_id.strip():
            continue

        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or score < threshold
        ):
            continue

        if (
            chunk_id not in unique_results
            or score > unique_results[chunk_id]["score"]
        ):
            unique_results[chunk_id] = result

    return sorted(
        unique_results.values(),
        key=lambda x: x["score"],
        reverse=True
    )

def rrf_score(vector_results, bm25_results, k=60):
    results = {}

    for ranked_list in (vector_results, bm25_results):
        for rank, item in enumerate(ranked_list, start=1):
            results[item] = results.get(item, 0) + 1 / (k + rank)

    return sorted(
        results.items(),
        key=lambda x: x[1],
        reverse=True
    )

async def semantic_search(query):
    ...

async def bm25_search(query):
    ...

async def hybrid_search(query):
    vector_results, bm25_results = await asyncio.gather(
        semantic_search(query),
        bm25_search(query)
    )

    return vector_results, bm25_results

async def get_embedding(text):
    ...

async def get_embedding_with_retry(text, max_retries=3):
    for attempt in range(max_retries + 1):
        try:
            return await get_embedding(text)
        except Exception:
            if attempt == max_retries:
                raise

            await asyncio.sleep(2 ** attempt)
    return None

async def embed_chunks(chunks, concurrency=5):
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")

    semaphore = asyncio.Semaphore(concurrency)

    async def parallel_embed(text):
        async with semaphore:
            return await get_embedding(text)

    tasks = [parallel_embed(text) for text in chunks]

    return await asyncio.gather(*tasks)


def merge_results(semantic_results, bm25_results):
    results = {}

    for ranked_list in (semantic_results, bm25_results):
        for rank, item in enumerate(ranked_list, start=1):
            chunk_id = item.get("chunk_id")
            score = item.get("score")

            if not isinstance(chunk_id, str) or not chunk_id.strip():
                continue

            if (
                    isinstance(score, bool)
                    or not isinstance(score, (int, float))
            ):
                continue

            if (
                    chunk_id not in results
                    or score > results[chunk_id]["score"]
            ):
                results[chunk_id] = item

    return sorted(
        results.values(),
        key=lambda x: x["score"],
        reverse=True
    )

def filter_results(results, threshold=0.5):
    return [
        result for result in results
        if result["score"] >= threshold
    ]

def test_filter_results():
    results = [
        {"chunk_id": "B", "score": 0.70},
        {"chunk_id": "D", "score": 0.50},
        {"chunk_id": "E", "score": 0.60},
        {"chunk_id": "A", "score": 0.40},
    ]

    original = [item.copy() for item in results]

    filtered = filter_results(results, threshold=0.5)

    assert [item["chunk_id"] for item in filtered] == ["B", "D", "E"]
    assert all(item["score"] >= 0.5 for item in filtered)
    assert results == original


def parse_llm_response(response):
    try:
        json_response = json.loads(response)
        if not isinstance(json_response, dict):
            raise ValueError

        if not isinstance(json_response.get("answer"), str) or not json_response.get("answer").strip():
            raise ValueError

        confidence = json_response.get("confidence")
        if (isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence)
                or not 0 <= confidence <= 1):
            raise ValueError
        return json_response
    except Exception:
        return None

async def embed_batch(chunks, concurrency=5):

  semaphore = asyncio.Semaphore(concurrency)

  async def safe_embed(chunk):
    async with semaphore:
      try:
        # Attempt the embedding call
        return await get_embedding(chunk)
      except Exception:
        # Requirements 3 & 5: Catch failure, return None, do not crash the batch
        return None

  tasks = [safe_embed(chunk) for chunk in chunks]

  return await asyncio.gather(*tasks)

def evaluate_retrieval(retrieved, relevant, k):
    if k <= 0 or not relevant:
        return {"precision": 0, "recall": 0, "results": []}

    top_k = retrieved[:k]

    # Deduplicate while preserving first-occurrence order
    unique_retrieved = list(dict.fromkeys(top_k))

    if not unique_retrieved:
        return {"precision": 0, "recall": 0}

    relevant_retrieved = set(unique_retrieved) & set(relevant)

    precision_score = len(relevant_retrieved) / len(unique_retrieved)
    recall_score = len(relevant_retrieved) / len(relevant)

    return {
        "precision": precision_score,
        "recall": recall_score,
        "results": relevant_retrieved,
    }

def test_evaluate_retrieval():
    retrieved = ["A", "B", "F", "C", "D"]
    relevant = {"A", "C", "D", "F"}
    k=3
    results = evaluate_retrieval(retrieved, relevant, k)

    print(f"{k}: {results}")

if __name__ == "__main__":
    test_evaluate_retrieval()
