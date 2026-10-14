from main.src.utils.enums import ChunkingStrategy, PdfParser
from main.src.utils.diagnostics import debug
from main.src.engineering.runtime import checkpoint
from main.src.engineering.tracing import event
import time
import io
import hashlib
import logging
import os

from main.src.memory.document_memory import load_document_records, save_document
from main.src.utils.common_utils import (
    extract_pages,
    split_text
)
from main.src.rag.search_utils import (
    reciprocal_rank_fusion,
    lexical_search,
    rerank_retrieved,
    section_chunks,
    layout_pages,
)
from main.src.rag.rag_service import (
    MAX_BATCH_SIZE,
    collection,
    create_embedding,
    create_embeddings,
    generate_multi_queries
)
from main.src.utils.constants import DOCUMENT_CHUNKING_VERSION, DOCUMENT_PARSER_VERSION, EMBEDDING_MODEL,CHUNKING_STRATEGY

# Logger
logger = logging.getLogger(__name__)

def index_and_store_document(pdf_bytes, filename):
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()

    existing = collection.get(
        where={"filename": filename},
        include=["metadatas"],
    )

    ids = existing.get("ids") or []
    metadata = existing.get("metadatas") or []

    unchanged_index = (
        bool(ids)
        and len(metadata) == len(ids)
        and all(
            isinstance(item, dict)
            and item.get("content_hash") == content_hash
            and item.get("chunking_version") == DOCUMENT_CHUNKING_VERSION
            and item.get("embedding_model") == EMBEDDING_MODEL
            and item.get('parser_version') == DOCUMENT_PARSER_VERSION
            and item.get("document_chunk_count") == len(ids)
            for item in metadata
        )
    )

    if unchanged_index:
        chunk_count = len(ids)
        indexing_status = "already_indexed"
    else:
        chunk_count = add_document(
            io.BytesIO(pdf_bytes),
            filename,
        )
        indexing_status = "indexed"

    saved_record = load_document_records().get(filename)

    if (
        saved_record is None
        or saved_record["content_hash"] != content_hash
        or saved_record["chunk_count"] != chunk_count
    ):
        save_document(
            filename,
            content_hash,
            pdf_bytes,
            chunk_count,
        )

    return {
        "status": indexing_status,
        "chunk_count": chunk_count,
        "content_hash": content_hash,
    }

def add_document(pdf_file, filename):
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("filename must be a nonempty string")

    position = pdf_file.tell()
    try:
        pdf_file.seek(0)
        pdf_bytes = pdf_file.read()
    finally:
        pdf_file.seek(position)

    if os.getenv('JENNA_PDF_PARSER',PdfParser.LAYOUT)==PdfParser.LAYOUT:
        pages=layout_pages(io.BytesIO(pdf_bytes),ocr=os.getenv('JENNA_OCR','true').lower()=='true')
    else:
        pages = extract_pages(io.BytesIO(pdf_bytes))

    if not pages:
        raise ValueError(
            f"No extractable text found in {filename}. Scanned PDFs may require OCR."
        )

    content_hash = hashlib.sha256(pdf_bytes).hexdigest()
    document_id = hashlib.sha256(filename.encode()).hexdigest()

    all_chunks = []
    all_metadata = []
    for page in pages:
        if CHUNKING_STRATEGY==ChunkingStrategy.SECTIONS:
            chunks=section_chunks(page['text'])
        else:chunks = split_text(page["text"])
        for chunk_index, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            all_metadata.append({
                "filename": filename,
                "page": page["page"],
                "chunk_index": chunk_index,
                "content_hash": content_hash,
                "embedding_model": EMBEDDING_MODEL,
                "chunking_version": DOCUMENT_CHUNKING_VERSION,
                "parser_version": DOCUMENT_PARSER_VERSION,
                "ocr_used": page.get('ocr',False),
                "table_count": page.get('table_count',0),
            })

    for metadata in all_metadata:
        metadata["document_chunk_count"] = len(all_chunks)

    embeddings = create_embeddings(all_chunks)

    new_ids = [
        f"{document_id}:{content_hash}:{i}"
        for i in range(len(all_chunks))
    ]
    old_ids = set(
        collection.get(
            where={"filename": filename},
            include=[],
        )["ids"]
    )

    for start in range(0, len(all_chunks), MAX_BATCH_SIZE):
        end = start + MAX_BATCH_SIZE
        collection.upsert(
            ids=new_ids[start:end], documents=all_chunks[start:end],
            embeddings=embeddings[start:end], metadatas=all_metadata[start:end],
        )

    obsolete_ids = sorted(old_ids - set(new_ids))

    if obsolete_ids:
        collection.delete(ids=obsolete_ids)

    return len(all_chunks)


def delete_document(filename):
    """Remove the saved PDF and index; restore index if SQLite deletion fails."""
    from main.src.memory.memory_service import delete
    snapshot = collection.get(where={"filename": filename},
                              include=["documents", "metadatas", "embeddings"])
    collection.delete(where={"filename": filename})
    try:
        return delete("uploaded_documents", {"filename": filename})
    except Exception:
        if snapshot["ids"]:
            collection.upsert(ids=snapshot["ids"], documents=snapshot["documents"],
                              metadatas=snapshot["metadatas"], embeddings=snapshot["embeddings"])
        raise

def list_documents():
    stored = collection.get(include=["metadatas"])

    return sorted({
        metadata["filename"]
        for metadata in (stored.get("metadatas") or [])
        if isinstance(metadata, dict)
        and isinstance(metadata.get("filename"), str)
    })

def search_documents(
        question, n_results=10, threshold=0.2,
        max_chunks=4, multi_query=False, hybrid=False, rerank=True, filters=None
):
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a nonempty string")

    if n_results <= 0 or max_chunks <= 0:
        raise ValueError("Retrieval depths must be positive")

    if not -1 <= threshold <= 1:
        raise ValueError("Similarity threshold must be between -1 and 1")

    question = question.strip()
    checkpoint('retrieval_started',candidate_k=n_results,context_k=max_chunks,strategy='hybrid' if hybrid else 'dense')
    started=time.perf_counter()
    where=None
    if filters is None:
        from main.src.rag.context import active_document_filter
        filters=active_document_filter.get()
    if filters:
        if set(filters)-{'filename','page'}:raise ValueError('Only filename/page filters are supported')
        conditions=[]
        for key,value in filters.items():
            if key=='filename' and (not isinstance(value,str) or not value):raise ValueError('Invalid filename filter')
            if key=='page' and (not isinstance(value,int) or isinstance(value,bool) or value<1):raise ValueError('Invalid page filter')
            conditions.append({key:value})
        where=conditions[0] if len(conditions)==1 else {'$and':conditions}
    count = collection.count()
    if count == 0:
        return []

    # --------------------------------
    # Generate retrieval queries
    # --------------------------------
    queries = [question]
    if multi_query:
        try:
            queries, elapsed = generate_multi_queries(question)
            debug(f" queries generated - {elapsed}ms")
        except Exception:
            logger.exception(
                "Query generation failed; using original question"
            )

    debug("\nRetrieval queries:")
    for query in queries:
        debug(f" - {query}")

    # --------------------------------
    # Retrieve candidates
    # --------------------------------

    corpus = None

    if hybrid:
        corpus = collection.get(include=["documents", "metadatas"],**({'where':where} if where else {}))

    ranked_lists = []

    for query in queries:

        debug(f"\nSearching: {query}")

        query_embedding = create_embedding(query)

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, collection.count()),
            include=["documents", "metadatas", "distances"],
            **({'where':where} if where else {}),
        )

        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        debug(f"Retrieved: {len(documents)}")
        dense_results = []
        for document, metadata, distance in zip(
            documents,
            metadatas,
            distances
        ):

            similarity = 1 - float(distance)

            if similarity < threshold:
                continue

            dense_results.append({
                "text": document,
                "filename": metadata["filename"],
                "page": metadata["page"],
                "chunk_index": metadata["chunk_index"],
                "similarity": similarity,
            })
        ranked_lists.append(dense_results)

        if hybrid:
            ranked_lists.append(
                lexical_search(
                    query,
                    corpus["documents"],
                    corpus["metadatas"],
                    n_results,
                )
            )

    # --------------------------------
    # Convert dictionary → list
    # --------------------------------

    if len(ranked_lists) == 1:
        candidates = ranked_lists[0]
    else:
        candidates = reciprocal_rank_fusion(
            ranked_lists,
            k=60,
        )[:n_results]

    debug(
        f"\nUnique retrieved chunks: "
        f"{len(candidates)}"
    )

    # --------------------------------
    # Rerank ALL candidates
    # --------------------------------

    if not rerank:
        event('retrieval_finished',seconds=time.perf_counter()-started,candidates=len(candidates))
        return candidates[:max_chunks]

    reranked = rerank_retrieved(
        question,
        candidates,
        max_chunks=max_chunks
    )

    event('retrieval_finished',seconds=time.perf_counter()-started,candidates=len(candidates),context=len(reranked))
    checkpoint()
    return reranked
