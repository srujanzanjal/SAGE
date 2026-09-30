import hashlib
from functools import lru_cache
from typing import Any, Optional

from app.core.supabase_client import get_supabase_client
from app.models.schemas import SourceType
from app.services.chunker import TextChunk


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class SupabaseRepository:
    def __init__(self):
        self.db = get_supabase_client()

    def get_knowledgebase_by_canonical_ref(self, canonical_ref: str) -> Optional[dict[str, Any]]:
        result = (
            self.db.table("knowledgebases")
            .select("*")
            .eq("canonical_ref", canonical_ref)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_knowledgebase(self, knowledgebase_id: str) -> Optional[dict[str, Any]]:
        result = self.db.table("knowledgebases").select("*").eq("id", knowledgebase_id).limit(1).execute()
        return result.data[0] if result.data else None

    def list_knowledgebases(self, limit: int = 100) -> list[dict[str, Any]]:
        result = (
            self.db.table("knowledgebases")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def create_knowledgebase(self, *, name: str, source_type: SourceType, canonical_ref: str) -> dict[str, Any]:
        payload = {"name": name, "source_type": source_type, "canonical_ref": canonical_ref, "status": "processing"}
        result = self.db.table("knowledgebases").insert(payload).execute()
        return result.data[0]

    def update_knowledgebase_status(self, knowledgebase_id: str, status: str) -> None:
        self.db.table("knowledgebases").update({"status": status}).eq("id", knowledgebase_id).execute()

    def get_source_by_canonical_ref(self, canonical_ref: str) -> Optional[dict[str, Any]]:
        result = self.db.table("sources").select("*").eq("canonical_ref", canonical_ref).limit(1).execute()
        return result.data[0] if result.data else None

    def create_source(
        self,
        *,
        knowledgebase_id: str,
        source_type: SourceType,
        original_ref: str,
        canonical_ref: str,
        title: str,
        content_hash: str,
        text_length: int,
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "knowledgebase_id": knowledgebase_id,
            "source_type": source_type,
            "original_ref": original_ref,
            "canonical_ref": canonical_ref,
            "title": title,
            "status": "ready",
            "content_hash": content_hash,
            "text_length": text_length,
            "meta": meta,
        }
        result = self.db.table("sources").insert(payload).execute()
        return result.data[0]

    def update_source_meta(self, source_id: str, meta: dict[str, Any]) -> None:
        self.db.table("sources").update({"meta": meta}).eq("id", source_id).execute()

    def get_chunks_count(self, knowledgebase_id: str) -> int:
        result = (
            self.db.table("chunks")
            .select("id", count="exact")
            .eq("knowledgebase_id", knowledgebase_id)
            .limit(1)
            .execute()
        )
        return int(result.count or 0)

    def get_chunks_count_for_source(self, knowledgebase_id: str, source_id: str) -> int:
        result = (
            self.db.table("chunks")
            .select("id", count="exact")
            .eq("knowledgebase_id", knowledgebase_id)
            .eq("source_id", source_id)
            .limit(1)
            .execute()
        )
        return int(result.count or 0)

    def get_chunks_count_for_knowledgebase(self, knowledgebase_id: str) -> int:
        result = (
            self.db.table("chunks")
            .select("id", count="exact")
            .eq("knowledgebase_id", knowledgebase_id)
            .limit(1)
            .execute()
        )
        return int(result.count or 0)

    def list_sources_for_knowledgebase(self, knowledgebase_id: str) -> list[dict[str, Any]]:
        result = (
            self.db.table("sources")
            .select("*")
            .eq("knowledgebase_id", knowledgebase_id)
            .execute()
        )
        return result.data or []

    def get_source(self, source_id: str) -> Optional[dict[str, Any]]:
        result = self.db.table("sources").select("*").eq("id", source_id).limit(1).execute()
        return result.data[0] if result.data else None


    def delete_query_history_for_source(self, source_id: str) -> None:
        self.db.table("query_history").delete().eq("source_id", source_id).execute()

    def delete_query_history_for_knowledgebase(self, knowledgebase_id: str) -> None:
        self.db.table("query_history").delete().eq("knowledgebase_id", knowledgebase_id).execute()

    def purge_old_query_history(self, retention_days: int = 30) -> None:
        # Best effort cleanup. Works even if the optional SQL function has not been installed.
        self.db.rpc("purge_old_query_history", {"retention_days": retention_days}).execute()

    def delete_source_chunks(self, source_id: str) -> None:
        self.db.table("chunks").delete().eq("source_id", source_id).execute()

    def delete_knowledgebase_chunks(self, knowledgebase_id: str) -> None:
        self.db.table("chunks").delete().eq("knowledgebase_id", knowledgebase_id).execute()

    def delete_source(self, source_id: str) -> list[dict[str, Any]]:
        result = self.db.table("sources").delete().eq("id", source_id).execute()
        return result.data or []

    def delete_knowledgebase(self, knowledgebase_id: str) -> list[dict[str, Any]]:
        result = self.db.table("knowledgebases").delete().eq("id", knowledgebase_id).execute()
        return result.data or []

    def insert_chunks(
        self,
        *,
        knowledgebase_id: str,
        source_id: str,
        source_type: SourceType,
        source_ref: str,
        chunks: list[TextChunk],
        chunk_ids: list[str],
    ) -> None:
        rows = []
        for chunk, chunk_id in zip(chunks, chunk_ids):
            metadata = {"source_type": source_type}
            if getattr(chunk, "extra_metadata", None):
                # merge chunk.extra_metadata into metadata stored in DB
                metadata.update(chunk.extra_metadata)
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
                }
            )

        if rows:
            self.db.table("chunks").upsert(rows, on_conflict="id").execute()

    def get_sources(self, limit: int = 50) -> list[dict[str, Any]]:
        result = (
            self.db.table("sources")
            .select("*, knowledgebases(id, status, name)")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def save_query_history(
        self,
        *,
        knowledgebase_id: str | None,
        source_id: str | None,
        question: str,
        rewritten_query: str,
        mode: str,
        answer: str,
        confidence: float,
        retrieved_chunk_ids: list[str],
    ) -> None:
        payload = {
            "knowledgebase_id": knowledgebase_id,
            "source_id": source_id,
            "question": question,
            "rewritten_query": rewritten_query,
            "mode": mode,
            "answer": answer,
            "confidence": confidence,
            "retrieved_chunk_ids": retrieved_chunk_ids,
        }
        self.db.table("query_history").insert(payload).execute()


@lru_cache(maxsize=1)
def get_supabase_repository() -> SupabaseRepository:
    return SupabaseRepository()


def make_chunk_id(knowledgebase_id: str, source_id: str, index: int, text: str) -> str:
    digest = hashlib.sha256(f"{knowledgebase_id}:{source_id}:{index}:{text}".encode("utf-8")).hexdigest()[:24]
    return f"chk_{digest}"
