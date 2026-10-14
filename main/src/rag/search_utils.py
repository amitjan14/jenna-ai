from main.src.utils.enums import ModelOperation
from main.src.utils import regex_constants as rx
import os
import re
import math
import torch
import pymupdf
from pathlib import Path
from time import perf_counter
from main.src.utils.telemetry import record_call
from collections import Counter
from main.src.utils.common_utils import split_text

def reciprocal_rank_fusion(ranked_results, k=60):
    """
    Combine multiple ranked retrieval lists using
    Reciprocal Rank Fusion (RRF).

    ranked_results:
        List of ranked result lists.
        Each result list should contain dictionaries with:
        - text
        - filename
        - page
        - chunk_index
        - similarity

    k:
        RRF constant. 60 is the standard starting value.
    """

    fused = {}

    for results in ranked_results:

        for rank, result in enumerate(results, start=1):

            chunk_id = (
                f"{result['filename']}_"
                f"{result['page']}_"
                f"{result['chunk_index']}"
            )

            rrf_score = 1 / (k + rank)

            if chunk_id not in fused:
                fused[chunk_id] = {
                    "text": result["text"],
                    "filename": result["filename"],
                    "page": result["page"],
                    "chunk_index": result["chunk_index"],
                    "similarity": result["similarity"],
                    "rrf_score": rrf_score,
                }

            else:
                fused[chunk_id]["rrf_score"] += rrf_score

                # Keep the strongest embedding similarity
                fused[chunk_id]["similarity"] = max(
                    fused[chunk_id]["similarity"],
                    result["similarity"]
                )

    fused_results = list(fused.values())

    fused_results.sort(
        key=lambda x: x["rrf_score"],
        reverse=True
    )

    return fused_results


def rerank_retrieved(question, retrieved, max_chunks=4):
    from main.src.rag.rag_service import get_reranker
    if max_chunks <= 0:
        raise ValueError("max_chunks must be positive")

    if not retrieved:
        return []

    pairs = [
        (question, retrievedData["text"])
        for retrievedData in retrieved
    ]

    start = perf_counter()
    scores = get_reranker().predict(
        pairs,
        activation_fn=torch.nn.Sigmoid(),
        show_progress_bar=False
    )
    record_call(ModelOperation.RERANK, perf_counter() - start)
    if len(scores) != len(retrieved):
        raise RuntimeError("Reranker response count mismatch")

    ranked = []

    for retrievedData, score in zip(retrieved, scores):
        score = float(score)
        if not math.isfinite(score):
            raise RuntimeError("Invalid reranker score")

        ranked.append({**retrievedData, "rerank_score": score})

    ranked.sort(key=lambda x: x["rerank_score"], reverse=True)
    return ranked[:max_chunks]


def lexical_search(question, documents, metadatas , n_results):
    def tokenize(text):
        return re.findall(rx.WORD, text.casefold())

    if not documents:
        return []

    counts = [Counter(tokenize(text)) for text in documents]
    lengths = [sum(count.values()) for count in counts]
    average_length = sum(lengths) / len(lengths) or 1

    document_frequency = Counter(
        term
        for count in counts
        for term in count
    )

    results = []

    for text, metadata, count, length in zip(documents, metadatas, counts, lengths):
        score = 0.0
        for term in set(tokenize(question)):
            frequency = count[term]

            if not frequency:
                continue

            df = document_frequency[term]
            idf = math.log(1 + (len(documents) - df + 0.5) / (df + 0.5))
            denominator = frequency + 1.5 * (0.25 + (0.75 * length/average_length))
            score = score + idf * frequency * 2.5 / denominator

        if score > 0:
            results.append({
                "text": text,
                **metadata,
                "similarity": 0.0,
                "lexical_score": score,
            })
    results.sort(
        key=lambda result: result["lexical_score"],
        reverse=True,
    )

    return results[:n_results]


def section_chunks(text,chunk_size=200,overlap=20):
    sections=[];heading='';parts=[]
    for line in text.splitlines():
        stripped=line.strip()
        is_heading=bool(stripped) and (stripped.startswith('#') or len(stripped.split())<=12 and stripped.isupper())
        if is_heading:
            if parts:sections.append((heading,'\n'.join(parts)));parts=[]
            heading=stripped.lstrip('#').strip()
        elif stripped:parts.append(stripped)
    if parts:sections.append((heading,'\n'.join(parts)))
    if not sections:return split_text(text,chunk_size,overlap)
    result=[]
    for heading,body in sections:
        prefix=heading+'\n' if heading else ''
        capacity=max(20,chunk_size-len(heading.split()))
        result.extend(prefix+chunk for chunk in split_text(body,capacity,min(overlap,capacity-1)))
    return result


def layout_pages(pdf_file,ocr=True,tables=True):
    position=pdf_file.tell();pdf_file.seek(0)
    try:raw=pdf_file.read()
    finally:pdf_file.seek(position)
    pages=[]
    tessdata=os.getenv('TESSDATA_PREFIX')
    if not tessdata:
        for candidate in ['/opt/homebrew/share/tessdata','/usr/share/tesseract-ocr/5/tessdata']:
            if Path(candidate).exists():tessdata=candidate;break
    with pymupdf.open(stream=raw,filetype='pdf') as document:
        for number,page in enumerate(document,start=1):
            text=page.get_text(sort=True)
            used_ocr=False
            if not text.strip() and ocr:
                try:
                    textpage=page.get_textpage_ocr(language='eng',dpi=200,full=True,tessdata=tessdata)
                    text=page.get_text(textpage=textpage,sort=True);used_ocr=True
                except Exception as error:
                    raise ValueError('Local OCR failed. Install Tesseract and set TESSDATA_PREFIX to its language-data directory.') from error
            table_text=[]
            if tables and not used_ocr:
                for table in page.find_tables().tables:
                    rows=table.extract()
                    if not rows:continue
                    clean=lambda row:' | '.join(str(cell or '').replace('\n',' ') for cell in row)
                    table_text.append('Table:\n'+ '\n'.join(clean(row) for row in rows))
            if table_text:text+='\n\n'+'\n\n'.join(table_text)
            if text.strip():pages.append({'page':number,'text':text,'ocr':used_ocr,'table_count':len(table_text)})
    return pages

