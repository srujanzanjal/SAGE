from typing import Any, Optional

from app.core.config import get_settings
from app.core.supabase_client import get_supabase_client
from app.models.schemas import SourceType
from app.services.chunker import TextChunk
from app.services.retrieval_types import RetrievedChunk

# Columns to read back for a chunk (everything except the large embedding vector).
_CHUNK_COLUMNS = (
    "id,knowledgebase_id,source_id,chunk_index,text,token_estimate,"
    "source_ref,page_number,section_title,metadata"
)


def _to_vector_literal(embedding: list[float]) -> str:
    # pgvector accepts a text literal like "[0.1,0.2,...]"; PostgREST casts it to vector.
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


def _row_to_chunk(row: dict[str, Any], *, distance: float = 1.0, semantic_score: float = 0.0) -> RetrievedChunk:
    """Rebuild the flat metadata dict callers expect (same keys Chroma exposed):
    the per-chunk jsonb plus the structural columns stored alongside it."""
    meta: dict[str, Any] = dict(row.get("metadata") or {})
    meta["chunk_id"] = row["id"]
    meta["knowledgebase_id"] = row.get("knowledgebase_id")
    meta["source_id"] = row.get("source_id")
    meta["source_ref"] = row.get("source_ref")
    meta["chunk_index"] = row.get("chunk_index")
    meta["token_estimate"] = row.get("token_estimate")
    if row.get("page_number") is not None:
        meta["page_number"] = row["page_number"]
    if row.get("section_title"):
        meta["section_title"] = row["section_title"]
    return RetrievedChunk(
        chunk_id=str(row["id"]),
        text=row.get("text") or "",
        metadata=meta,
        distance=distance,
        semantic_score=semantic_score,
    )


class VectorStore:
    def __init__(self):
        self.db = get_supabase_client()

    def upsert_chunks(
        self,
        *,
        knowledgebase_id: str,
        source_id: str,
        source_type: SourceType,
        source_ref: str,
        chunks: list[TextChunk],
        embeddings: list[list[float]],
        chunk_ids: list[str],
    ) -> None:
        # Writes a full chunks row including the embedding. repo.insert_chunks writes
        # the same rows without the embedding; whichever runs first inserts, the other
        # updates, and an on-conflict update never clears columns absent from its payload.
        # ponytail: two writers to one table, re-ingest scale is tiny; fold the embedding
        # into repo.insert_chunks and drop this method if ingestion write cost ever matters.
        rows: list[dict] = []
        for chunk, chunk_id, embedding in zip(chunks, chunk_ids, embeddings):
            metadata: dict[str, Any] = {"source_type": source_type}
            if getattr(chunk, "extra_metadata", None):
                metadata.update(chunk.extra_metadata)
            metadata = {k: v for k, v in metadata.items() if v is not None}
            rows.append(
                {
                    "id": chunk_id,
                    "knowledgebase_id": knowledgebase_id,
                    "source_id": source_id,
                    "chunk_index": chunk.index,
                    "text": chunk.text,
                    "token_estimate": chunk.token_estimate,
                    "char_count": len(chunk.text),
                    "source_ref": source_ref,
                    "page_number": chunk.page_number,
                    "section_title": chunk.section_title,
                    "metadata": metadata,
                    "embedding": _to_vector_literal(embedding),
                }
            )
        if rows:
            self.db.table("chunks").upsert(rows, on_conflict="id").execute()

    def search(
        self,
        *,
        query_embedding: list[float],
        knowledgebase_id: Optional[str] = None,
        source_id: Optional[str] = None,
        source_ids: Optional[list[str]] = None,
        top_k: int = 6,
    ) -> list[RetrievedChunk]:
        # source_ids spans knowledgebases, so kb/source are ignored when it is given
        # (match_chunks ANDs only the non-null filters passed here).
        if source_ids:
            params = {"filter_source_ids": list(source_ids), "filter_knowledgebase_id": None, "filter_source_id": None}
        else:
            params = {
                "filter_source_ids": None,
                "filter_knowledgebase_id": knowledgebase_id,
                "filter_source_id": source_id,
            }
        args = {"query_embedding": query_embedding, "match_count": max(top_k, 1), **params}
        eval_model = get_settings().eval_embedding_model
        if eval_model:
            rpc, args = "match_chunks_eval", {"match_model": eval_model, **args}
        else:
            rpc = "match_chunks"
        result = self.db.rpc(rpc, args).execute()

        retrieved: list[RetrievedChunk] = []
        for row in result.data or []:
            distance = float(row.get("distance", 1.0))
            retrieved.append(_row_to_chunk(row, distance=distance, semantic_score=max(0.0, min(1.0, 1.0 - distance))))
        return retrieved

    def _select(self):
        return self.db.table("chunks").select(_CHUNK_COLUMNS)

    def get_overview_text(self, source_id: str) -> Optional[str]:
        """Raw text of a source's deterministic overview chunk (metadata lookup, no search)."""
        result = (
            self._select()
            .eq("source_id", source_id)
            .eq("metadata->>chunk_kind", "source_overview")
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        text = rows[0].get("text") or ""
        # Strip the internal retrieval marker line (e.g. "__SAGE_WEBSITE_OVERVIEW__").
        lines = text.splitlines()
        if lines and lines[0].startswith("__SAGE_") and lines[0].endswith("__"):
            lines = lines[1:]
        return "\n".join(lines).strip() or None

    def get_overview_chunks(self, source_ids: list[str]) -> list[RetrievedChunk]:
        result = (
            self._select()
            .in_("source_id", list(source_ids))
            .eq("metadata->>chunk_kind", "source_overview")
            .execute()
        )
        return [_row_to_chunk(row) for row in result.data or []]

    def get_source_chunks(self, source_id: str) -> list[RetrievedChunk]:
        """All chunks of a source in document order (overview chunk first), no search."""
        result = self._select().eq("source_id", source_id).order("chunk_index").execute()
        return [_row_to_chunk(row) for row in result.data or []]

    def get_chunk(self, chunk_id: str) -> Optional[RetrievedChunk]:
        result = self._select().eq("id", chunk_id).limit(1).execute()
        rows = result.data or []
        return _row_to_chunk(rows[0]) if rows else None

    def get_edge_chunks(self, source_id: str, *, from_end: bool, count: int = 2) -> list[RetrievedChunk]:
        """First or last content chunks of a source by position (overview excluded)."""
        content = [c for c in self.get_source_chunks(source_id) if c.metadata.get("chunk_kind") != "source_overview"]
        return content[-count:] if from_end else content[:count]

    def delete_by_source(self, source_id: str) -> None:
        self.db.table("chunks").delete().eq("source_id", source_id).execute()

    def delete_by_knowledgebase(self, knowledgebase_id: str) -> None:
        self.db.table("chunks").delete().eq("knowledgebase_id", knowledgebase_id).execute()


def get_vector_store() -> VectorStore:
    return VectorStore()
