"""Re-embed every stored chunk with another embedding model into its own Chroma
collection (sage_chunks_<model-slug>), without re-crawling anything.

Chunk text and metadata come from the Supabase `chunks` table, so the original
collection is untouched and the app keeps working while models are compared.

Usage (from backend/):
    python -m eval.reembed BAAI/bge-small-en-v1.5
"""
from __future__ import annotations

import os
import sys
import time
from collections import defaultdict

from eval.run_eval import model_slug

PAGE_SIZE = 1000  # Supabase caps a select at 1000 rows


def main(model: str) -> None:
    # Must be set before app settings are first read.
    os.environ["EMBEDDING_MODEL_NAME"] = model
    os.environ["CHROMA_COLLECTION_NAME"] = f"sage_chunks_{model_slug(model)}"

    from app.core.supabase_client import get_supabase_client
    from app.services.chunker import TextChunk
    from app.services.embeddings import get_embedding_service
    from app.services.vector_store import get_vector_store

    db = get_supabase_client()
    rows, start = [], 0
    while True:
        page = db.table("chunks").select("*").order("id").range(start, start + PAGE_SIZE - 1).execute().data or []
        rows += page
        if len(page) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    by_source: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_source[row["source_id"]].append(row)

    embedder, store = get_embedding_service(), get_vector_store()
    started = time.perf_counter()
    for source_id, source_rows in by_source.items():
        source_rows.sort(key=lambda r: r["chunk_index"])
        chunks = [
            TextChunk(
                index=r["chunk_index"],
                text=r["text"],
                token_estimate=r["token_estimate"],
                page_number=r.get("page_number"),
                section_title=r.get("section_title"),
                extra_metadata=r.get("metadata") or {},
            )
            for r in source_rows
        ]
        first = source_rows[0]
        store.upsert_chunks(
            knowledgebase_id=first["knowledgebase_id"],
            source_id=source_id,
            source_type=(first.get("metadata") or {}).get("source_type", "website"),
            source_ref=first["source_ref"],
            chunks=chunks,
            embeddings=embedder.embed_documents([c.text for c in chunks]),
            chunk_ids=[r["id"] for r in source_rows],
        )
    print(f"{model}: {len(rows)} chunks from {len(by_source)} sources re-embedded "
          f"into {os.environ['CHROMA_COLLECTION_NAME']} in {time.perf_counter() - started:.0f}s")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
