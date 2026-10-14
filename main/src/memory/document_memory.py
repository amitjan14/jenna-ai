from main.src.memory.memory_service import upsert, fetch_records, fetch_record


def save_document(filename, content_hash, pdf_bytes, chunk_count):
    upsert(
        "uploaded_documents",
        {
            "filename": filename,
            "content_hash": content_hash,
            "pdf_bytes": pdf_bytes,
            "chunk_count": chunk_count,
        },
        conflict_target="filename",
    )


def load_document_records():
    rows = fetch_records(
        table_name="uploaded_documents",
        columns=["filename", "content_hash", "chunk_count"],
        order_by="filename ASC",
    )

    return {
        filename: {
            "content_hash": content_hash,
            "chunk_count": chunk_count,
        }
        for filename, content_hash, chunk_count in rows
    }


def load_document_pdf(filename):
    row = fetch_record(
        table_name="uploaded_documents",
        columns=["pdf_bytes"],
        where={"filename": filename},
        order_by="filename ASC",
    )

    return bytes(row[0]) if row else None