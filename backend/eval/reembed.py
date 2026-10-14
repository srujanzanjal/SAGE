"""Re-embed every stored chunk with another embedding model into the eval-only
table eval_chunk_embeddings (one row per chunk per model), without re-crawling.

Chunk text and metadata come from the Supabase `chunks` table, so production
embeddings (chunks.embedding) stay untouched and the app keeps working while
models are compared.

Usage (from backend/):
    python -m eval.reembed BAAI/bge-small-en-v1.5
"""
from __future__ import annotations

import os
import sys
import time

PAGE_SIZE = 1000  # Supabase caps a select at 1000 rows


def _to_vector_literal(embedding) -> str:
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


def main(model: str) -> None:
    # Must be set before app settings/embedder are first read.
    os.environ["EMBEDDING_MODEL_NAME"] = model

    from app.core.supabase_client import get_supabase_client
    from app.services.embeddings import get_embedding_service

    db = get_supabase_client()
    rows, start = [], 0
    while True:
        page = db.table("chunks").select("id,text").order("id").range(start, start + PAGE_SIZE - 1).execute().data or []
        rows += page
        if len(page) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    embedder = get_embedding_service()
    started = time.perf_counter()
    vectors = embedder.embed_documents([r["text"] for r in rows])
    eval_rows = [{"chunk_id": r["id"], "model": model, "embedding": _to_vector_literal(v)} for r, v in zip(rows, vectors)]
    for i in range(0, len(eval_rows), 100):
        db.table("eval_chunk_embeddings").upsert(eval_rows[i : i + 100], on_conflict="chunk_id,model").execute()
    print(f"{model}: {len(rows)} chunks re-embedded into eval_chunk_embeddings "
          f"in {time.perf_counter() - started:.0f}s")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
