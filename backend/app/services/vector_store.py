from functools import lru_cache
from typing import Optional

from app.core.chroma_client import get_chroma_collection
from app.models.schemas import SourceType
from app.services.chunker import TextChunk
from app.services.retrieval_types import RetrievedChunk


class VectorStore:
    def __init__(self):
        self.collection = get_chroma_collection()

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
        def _clean_metadata(raw: dict) -> dict:
            cleaned: dict = {}
            for key, value in raw.items():
                if value is None:
                    continue
                if isinstance(value, (str, int, float, bool)):
                    cleaned[key] = value
            return cleaned

        metadatas: list[dict] = []
        documents: list[str] = []
        for chunk, chunk_id in zip(chunks, chunk_ids):
            metadata: dict = {
                "chunk_id": chunk_id,
                "knowledgebase_id": knowledgebase_id,
                "source_id": source_id,
                "source_type": source_type,
                "source_ref": source_ref,
                "chunk_index": chunk.index,
                "token_estimate": chunk.token_estimate,
            }
            if chunk.page_number is not None:
                metadata["page_number"] = chunk.page_number
            if chunk.section_title:
                metadata["section_title"] = chunk.section_title
            if getattr(chunk, "extra_metadata", None):
                metadata.update(chunk.extra_metadata)
            metadatas.append(_clean_metadata(metadata))
            documents.append(chunk.text)

        if chunk_ids:
            self.collection.upsert(
                ids=chunk_ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )

    def search(
        self,
        *,
        query_embedding: list[float],
        knowledgebase_id: Optional[str] = None,
        source_id: Optional[str] = None,
        source_ids: Optional[list[str]] = None,
        top_k: int = 6,
    ) -> list[RetrievedChunk]:
        if source_ids:
            # Combined multi-source question: sources may span different
            # knowledgebases, so knowledgebase_id/source_id are ignored here.
            where = {"source_id": {"$in": list(source_ids)}}
        elif knowledgebase_id and source_id:
            where = {"$and": [{"knowledgebase_id": knowledgebase_id}, {"source_id": source_id}]}
        elif knowledgebase_id:
            where = {"knowledgebase_id": knowledgebase_id}
        elif source_id:
            where = {"source_id": source_id}
        else:
            where = None

        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=max(top_k, 1),
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        docs = result.get("documents", [[]])[0] or []
        metas = result.get("metadatas", [[]])[0] or []
        distances = result.get("distances", [[]])[0] or []

        retrieved: list[RetrievedChunk] = []
        for doc, meta, distance in zip(docs, metas, distances):
            semantic_score = max(0.0, min(1.0, 1.0 - float(distance)))
            retrieved.append(
                RetrievedChunk(
                    chunk_id=str(meta.get("chunk_id")),
                    text=doc,
                    metadata=dict(meta),
                    distance=float(distance),
                    semantic_score=semantic_score,
                )
            )
        return retrieved

    def get_overview_text(self, source_id: str) -> Optional[str]:
        """Fetch the deterministic overview chunk's raw text for a source, if any.

        This is a direct metadata lookup (no embedding/LLM call) — the overview
        chunk is generated once at ingestion time from source stats.
        """
        result = self.collection.get(
            where={"$and": [{"source_id": source_id}, {"chunk_kind": "source_overview"}]},
            include=["documents"],
            limit=1,
        )
        docs = result.get("documents") or []
        if not docs:
            return None
        text = docs[0] or ""
        # Strip the internal retrieval marker line (e.g. "__SAGE_WEBSITE_OVERVIEW__").
        lines = text.splitlines()
        if lines and lines[0].startswith("__SAGE_") and lines[0].endswith("__"):
            lines = lines[1:]
        return "\n".join(lines).strip() or None

    def get_overview_chunks(self, source_ids: list[str]) -> list[RetrievedChunk]:
        """Overview chunks for the given sources, fetched by metadata (no search)."""
        result = self.collection.get(
            where={"$and": [{"source_id": {"$in": list(source_ids)}}, {"chunk_kind": "source_overview"}]},
            include=["documents", "metadatas"],
        )
        return [
            RetrievedChunk(chunk_id=str(meta.get("chunk_id")), text=doc, metadata=dict(meta), distance=1.0, semantic_score=0.0)
            for doc, meta in zip(result.get("documents") or [], result.get("metadatas") or [])
        ]

    def get_source_chunks(self, source_id: str) -> list[RetrievedChunk]:
        """All chunks of a source in document order (overview chunk first), no search."""
        result = self.collection.get(where={"source_id": source_id}, include=["documents", "metadatas"])
        chunks = [
            RetrievedChunk(chunk_id=str(meta.get("chunk_id")), text=doc, metadata=dict(meta), distance=1.0, semantic_score=0.0)
            for doc, meta in zip(result.get("documents") or [], result.get("metadatas") or [])
        ]
        return sorted(chunks, key=lambda c: int(c.metadata.get("chunk_index", 0)))

    def get_chunk(self, chunk_id: str) -> Optional[RetrievedChunk]:
        result = self.collection.get(ids=[chunk_id], include=["documents", "metadatas"])
        docs, metas = result.get("documents") or [], result.get("metadatas") or []
        if not docs:
            return None
        return RetrievedChunk(chunk_id=chunk_id, text=docs[0], metadata=dict(metas[0]), distance=1.0, semantic_score=0.0)

    def get_edge_chunks(self, source_id: str, *, from_end: bool, count: int = 2) -> list[RetrievedChunk]:
        """First or last content chunks of a source by position (overview excluded)."""
        content = [c for c in self.get_source_chunks(source_id) if c.metadata.get("chunk_kind") != "source_overview"]
        return content[-count:] if from_end else content[:count]

    def delete_by_source(self, source_id: str) -> None:
        self.collection.delete(where={"source_id": source_id})

    def delete_by_knowledgebase(self, knowledgebase_id: str) -> None:
        self.collection.delete(where={"knowledgebase_id": knowledgebase_id})


def get_vector_store() -> VectorStore:
    return VectorStore()
