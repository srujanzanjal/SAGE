from __future__ import annotations

from typing import Any, Optional

from app.models.schemas import KnowledgebaseDetail, KnowledgebaseGroup, RecrawlRequest, SourceDetail, SourceSummary, WebsiteCrawlResponse
from app.services.ingestion_pipeline import crawl_website_ingest
from app.services.supabase_repo import SupabaseRepository
from app.services.vector_store import get_vector_store


def _source_summary_from_row(row: dict[str, Any]) -> SourceSummary:
    kb = row.get("knowledgebases") or {}
    meta = row.get("meta") or {}
    page_count = meta.get("page_count")
    source_type = row.get("source_type")
    crawled_pages = meta.get("crawled_pages") if source_type == "website" else page_count
    return SourceSummary(
        knowledgebase_id=row["knowledgebase_id"],
        knowledgebase_name=kb.get("name"),
        source_id=row["id"],
        source_type=source_type,
        title=row.get("title"),
        canonical_ref=row["canonical_ref"],
        original_ref=row["original_ref"],
        status=row.get("status") or kb.get("status") or "unknown",
        text_length=row.get("text_length") or 0,
        chunks_count=0,
        page_count=page_count,
        crawled_pages=crawled_pages,
        transcript_duration=meta.get("transcript_duration"),
        video_id=meta.get("video_id"),
        transcript_origin=meta.get("transcript_origin"),
        meta=meta,
        created_at=row.get("created_at"),
    )


def _source_detail_from_row(row: dict[str, Any], chunks_count: int, kb_row: dict[str, Any]) -> SourceDetail:
    meta = row.get("meta") or {}
    page_count = meta.get("page_count")
    source_type = row.get("source_type")
    crawled_pages = meta.get("crawled_pages") if source_type == "website" else page_count
    return SourceDetail(
        knowledgebase_id=row["knowledgebase_id"],
        knowledgebase_name=kb_row.get("name"),
        source_id=row["id"],
        source_type=source_type,
        title=row.get("title"),
        canonical_ref=row["canonical_ref"],
        original_ref=row["original_ref"],
        status=row.get("status") or kb_row.get("status") or "unknown",
        text_length=row.get("text_length") or 0,
        chunks_count=chunks_count,
        page_count=page_count,
        crawled_pages=crawled_pages,
        transcript_duration=meta.get("transcript_duration"),
        video_id=meta.get("video_id"),
        transcript_origin=meta.get("transcript_origin"),
        meta=meta,
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def list_sources_grouped() -> list[KnowledgebaseGroup]:
    repo = SupabaseRepository()
    groups: list[KnowledgebaseGroup] = []
    for kb_row in repo.list_knowledgebases():
        sources = []
        for source_row in repo.list_sources_for_knowledgebase(kb_row["id"]):
            source_summary = _source_summary_from_row({**source_row, "knowledgebases": kb_row})
            source_summary.chunks_count = repo.get_chunks_count_for_source(kb_row["id"], source_row["id"])
            sources.append(source_summary)
        groups.append(
            KnowledgebaseGroup(
                knowledgebase=KnowledgebaseDetail(
                    knowledgebase_id=kb_row["id"],
                    name=kb_row["name"],
                    source_type=kb_row["source_type"],
                    canonical_ref=kb_row["canonical_ref"],
                    status=kb_row.get("status") or "unknown",
                    created_at=kb_row.get("created_at"),
                    updated_at=kb_row.get("updated_at"),
                    source_count=len(sources),
                    chunks_count=repo.get_chunks_count_for_knowledgebase(kb_row["id"]),
                    sources=sources,
                ),
                sources=sources,
            )
        )
    return groups


def get_source_detail(source_id: str) -> SourceDetail:
    repo = SupabaseRepository()
    source_row = repo.get_source(source_id)
    if not source_row:
        raise ValueError(f"Source not found: {source_id}")
    kb_row = repo.get_knowledgebase(source_row["knowledgebase_id"]) or {}
    chunks_count = repo.get_chunks_count_for_source(source_row["knowledgebase_id"], source_id)
    return _source_detail_from_row(source_row, chunks_count, kb_row)


def get_knowledgebase_detail(knowledgebase_id: str) -> KnowledgebaseDetail:
    repo = SupabaseRepository()
    kb_row = repo.get_knowledgebase(knowledgebase_id)
    if not kb_row:
        raise ValueError(f"Knowledgebase not found: {knowledgebase_id}")
    sources = []
    for source_row in repo.list_sources_for_knowledgebase(knowledgebase_id):
        source_summary = _source_summary_from_row({**source_row, "knowledgebases": kb_row})
        source_summary.chunks_count = repo.get_chunks_count_for_source(knowledgebase_id, source_row["id"])
        sources.append(source_summary)
    return KnowledgebaseDetail(
        knowledgebase_id=kb_row["id"],
        name=kb_row["name"],
        source_type=kb_row["source_type"],
        canonical_ref=kb_row["canonical_ref"],
        status=kb_row.get("status") or "unknown",
        created_at=kb_row.get("created_at"),
        updated_at=kb_row.get("updated_at"),
        source_count=len(sources),
        chunks_count=repo.get_chunks_count_for_knowledgebase(knowledgebase_id),
        sources=sources,
    )


def delete_source(source_id: str) -> dict[str, Any]:
    repo = SupabaseRepository()
    source_row = repo.get_source(source_id)
    if not source_row:
        raise ValueError(f"Source not found: {source_id}")

    kb_id = source_row["knowledgebase_id"]
    warnings: list[str] = []

    # Supabase rows are deleted first so metadata/history is consistently removed.
    # Chroma cleanup is best-effort because ChromaDB and Supabase cannot share one transaction.
    repo.delete_query_history_for_source(source_id)
    repo.delete_source_chunks(source_id)
    deleted_rows = repo.delete_source(source_id)

    try:
        get_vector_store().delete_by_source(source_id)
    except Exception as exc:
        warnings.append(f"Source metadata was deleted, but vector cleanup failed: {exc}")

    remaining_sources = repo.list_sources_for_knowledgebase(kb_id)
    if remaining_sources:
        repo.update_knowledgebase_status(kb_id, "ready")

    return {
        "deleted": True,
        "source_id": source_id,
        "knowledgebase_id": kb_id,
        "rows_deleted": len(deleted_rows),
        "warnings": warnings,
        "message": "Source deleted. Vector cleanup is best-effort if ChromaDB is unavailable.",
    }


def delete_knowledgebase(knowledgebase_id: str) -> dict[str, Any]:
    repo = SupabaseRepository()
    kb_row = repo.get_knowledgebase(knowledgebase_id)
    if not kb_row:
        raise ValueError(f"Knowledgebase not found: {knowledgebase_id}")

    source_rows = repo.list_sources_for_knowledgebase(knowledgebase_id)
    warnings: list[str] = []

    # Delete relational metadata/history first. FK cascade removes sources and chunks.
    repo.delete_query_history_for_knowledgebase(knowledgebase_id)
    repo.delete_knowledgebase_chunks(knowledgebase_id)
    deleted_rows = repo.delete_knowledgebase(knowledgebase_id)

    try:
        get_vector_store().delete_by_knowledgebase(knowledgebase_id)
    except Exception as exc:
        warnings.append(f"Knowledgebase metadata was deleted, but vector cleanup failed: {exc}")

    return {
        "deleted": True,
        "knowledgebase_id": knowledgebase_id,
        "source_count": len(source_rows),
        "rows_deleted": len(deleted_rows),
        "warnings": warnings,
        "message": "Knowledgebase deleted. Vector cleanup is best-effort if ChromaDB is unavailable.",
    }


def _resolve_recrawl_target(request: RecrawlRequest) -> tuple[str, str]:
    repo = SupabaseRepository()
    if request.knowledgebase_id:
        kb = repo.get_knowledgebase(request.knowledgebase_id)
        if not kb:
            raise ValueError(f"Knowledgebase not found: {request.knowledgebase_id}")
        if kb["source_type"] != "website":
            raise ValueError("Re-crawl is only supported for website knowledgebases.")
        return kb["id"], kb["canonical_ref"]

    if request.canonical_ref:
        kb = repo.get_knowledgebase_by_canonical_ref(request.canonical_ref)
        if not kb:
            raise ValueError(f"Knowledgebase not found for canonical URL: {request.canonical_ref}")
        if kb["source_type"] != "website":
            raise ValueError("Re-crawl is only supported for website knowledgebases.")
        return kb["id"], kb["canonical_ref"]

    raise ValueError("Provide knowledgebase_id or canonical_ref.")


def recrawl_website(request: RecrawlRequest) -> WebsiteCrawlResponse:
    kb_id, canonical_ref = _resolve_recrawl_target(request)
    delete_knowledgebase(kb_id)
    return crawl_website_ingest(canonical_ref, max_pages=request.max_pages, max_depth=request.max_depth)


