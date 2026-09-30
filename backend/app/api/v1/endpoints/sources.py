from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    KnowledgebaseDetail,
    KnowledgebaseGroup,
    RecrawlRequest,
    SourceDetail,
    SourceBrief,
    SourceOverviewResponse,
    SourceSummary,
)
from app.services.ingestion_jobs import start_website_recrawl_job
from app.services.llm import LLMServiceTimeoutError
from app.services.source_brief import get_source_brief
from app.services.source_management import (
    delete_knowledgebase,
    delete_source,
    get_knowledgebase_detail,
    get_source_detail,
    list_sources_grouped,
)
from app.services.supabase_repo import SupabaseRepository
from app.services.vector_store import get_vector_store

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[SourceSummary])
def list_sources():
    try:
        repo = SupabaseRepository()
        rows = repo.get_sources()
        summaries: list[SourceSummary] = []
        for row in rows:
            kb = row.get("knowledgebases") or {}
            meta = row.get("meta") or {}
            source_type = row["source_type"]
            summaries.append(
                SourceSummary(
                    knowledgebase_id=row["knowledgebase_id"],
                    knowledgebase_name=kb.get("name"),
                    source_id=row["id"],
                    source_type=source_type,
                    title=row.get("title"),
                    canonical_ref=row["canonical_ref"],
                    original_ref=row["original_ref"],
                    status=row.get("status") or kb.get("status") or "unknown",
                    text_length=row.get("text_length") or 0,
                    chunks_count=repo.get_chunks_count_for_source(row["knowledgebase_id"], row["id"]),
                    page_count=meta.get("page_count"),
                    crawled_pages=meta.get("crawled_pages") if source_type == "website" else meta.get("page_count"),
                    transcript_duration=meta.get("transcript_duration"),
                    video_id=meta.get("video_id"),
                    transcript_origin=meta.get("transcript_origin"),
                    meta=meta,
                    created_at=row.get("created_at"),
                )
            )
        return summaries
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not list sources: {exc}") from exc


@router.get("/grouped", response_model=list[KnowledgebaseGroup])
def list_sources_grouped_endpoint():
    try:
        return list_sources_grouped()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not list grouped sources: {exc}") from exc


@router.get("/{source_id}", response_model=SourceDetail)
def get_source_detail_endpoint(source_id: str):
    try:
        return get_source_detail(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not load source details: {exc}") from exc


@router.get("/{source_id}/summary", response_model=SourceOverviewResponse)
def get_source_summary_endpoint(source_id: str):
    try:
        return SourceOverviewResponse(summary=get_vector_store().get_overview_text(source_id))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not load source summary: {exc}") from exc


@router.get("/{source_id}/brief", response_model=SourceBrief)
def get_source_brief_endpoint(source_id: str, refresh: bool = False):
    try:
        return get_source_brief(source_id, refresh=refresh)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LLMServiceTimeoutError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        # The model returned something that wasn't a usable brief; retrying usually works.
        raise HTTPException(status_code=502, detail=f"Could not build the brief, please retry: {exc}") from exc


@router.get("/knowledgebases/{knowledgebase_id}", response_model=KnowledgebaseDetail)
def get_knowledgebase_detail_endpoint(knowledgebase_id: str):
    try:
        return get_knowledgebase_detail(knowledgebase_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not load knowledgebase details: {exc}") from exc


@router.delete("/{source_id}")
def delete_source_endpoint(source_id: str):
    try:
        return delete_source(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not delete source: {exc}") from exc


@router.delete("/knowledgebases/{knowledgebase_id}")
def delete_knowledgebase_endpoint(knowledgebase_id: str):
    try:
        return delete_knowledgebase(knowledgebase_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not delete knowledgebase: {exc}") from exc


@router.post("/website/recrawl", status_code=202)
def recrawl_website_endpoint(request: RecrawlRequest):
    try:
        return start_website_recrawl_job(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not start re-crawl: {exc}") from exc
