from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from app.models.schemas import CrawlSummaryResponse, IngestResponse, KnowledgebaseDetail, RecrawlRequest, WebsiteCrawlResponse
from app.services import confidence, ingestion_jobs, source_management
from app.services.job_tracker import create_job, get_job, update_job
from app.services.retrieval_types import RetrievedChunk


class FakeVectorStore:
    def get_overview_chunks(self, source_ids):
        return []

    def get_edge_chunks(self, source_id, from_end, count=2):
        return []

    def __init__(self):
        self.deleted_sources: list[str] = []
        self.deleted_kbs: list[str] = []

    def delete_by_source(self, source_id: str) -> None:
        self.deleted_sources.append(source_id)

    def delete_by_knowledgebase(self, knowledgebase_id: str) -> None:
        self.deleted_kbs.append(knowledgebase_id)


class FakeRepo:
    def __init__(self):
        self.sources = {
            "src_1": {
                "id": "src_1",
                "knowledgebase_id": "kb_1",
                "source_type": "website",
                "original_ref": "https://example.com",
                "canonical_ref": "https://example.com",
                "title": "Example",
                "status": "ready",
                "text_length": 1000,
                "meta": {"page_count": 1},
                "created_at": "2026-05-01T00:00:00Z",
                "updated_at": "2026-05-01T00:00:00Z",
            }
        }
        self.kbs = {
            "kb_1": {
                "id": "kb_1",
                "name": "Example",
                "source_type": "website",
                "canonical_ref": "https://example.com",
                "status": "ready",
                "created_at": "2026-05-01T00:00:00Z",
                "updated_at": "2026-05-01T00:00:00Z",
            }
        }
        self.deleted_sources: list[str] = []
        self.deleted_kbs: list[str] = []
        self.updated_status: list[tuple[str, str]] = []
        self.deleted_query_history: list[str] = []

    def list_knowledgebases(self, limit: int = 100):
        return list(self.kbs.values())

    def list_sources_for_knowledgebase(self, knowledgebase_id: str):
        return [source for source in self.sources.values() if source["knowledgebase_id"] == knowledgebase_id]

    def get_source(self, source_id: str):
        return self.sources.get(source_id)

    def get_knowledgebase(self, knowledgebase_id: str):
        return self.kbs.get(knowledgebase_id)

    def get_knowledgebase_by_canonical_ref(self, canonical_ref: str):
        for kb in self.kbs.values():
            if kb["canonical_ref"] == canonical_ref:
                return kb
        return None

    def get_chunks_count_for_source(self, knowledgebase_id: str, source_id: str):
        return 4

    def get_chunks_count_for_knowledgebase(self, knowledgebase_id: str):
        return 4

    def delete_query_history_for_source(self, source_id: str):
        self.deleted_query_history.append(f"source:{source_id}")

    def delete_query_history_for_knowledgebase(self, knowledgebase_id: str):
        self.deleted_query_history.append(f"knowledgebase:{knowledgebase_id}")

    def delete_source_chunks(self, source_id: str):
        self.deleted_sources.append(f"chunks:{source_id}")

    def delete_source(self, source_id: str):
        self.deleted_sources.append(source_id)
        self.sources.pop(source_id, None)
        return [{"id": source_id}]

    def delete_knowledgebase_chunks(self, knowledgebase_id: str):
        self.deleted_kbs.append(f"chunks:{knowledgebase_id}")

    def delete_knowledgebase(self, knowledgebase_id: str):
        self.deleted_kbs.append(knowledgebase_id)
        self.kbs.pop(knowledgebase_id, None)
        return [{"id": knowledgebase_id}]

    def update_knowledgebase_status(self, knowledgebase_id: str, status: str):
        self.updated_status.append((knowledgebase_id, status))


def test_confidence_label_and_reason_transparent():
    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            text="Python is a programming language used for web development.",
            metadata={"source_id": "s1", "source_type": "website", "source_ref": "https://python.org", "chunk_index": 0},
            distance=0.05,
            semantic_score=0.92,
            score=0.9,
        )
    ]

    score = confidence.calculate_confidence(chunks)
    label, reason = confidence.confidence_label_and_reason("What is Python?", chunks, score)

    assert 0 <= score <= 1
    assert label in {"High", "Medium", "Low"}
    assert reason in {"strong semantic match", "weak evidence", "few relevant chunks", "vague query"}


def test_job_tracker_lifecycle():
    job = create_job(operation="website_ingest", source_type="website")
    assert job.status == "queued"

    updated = update_job(job.job_id, status="processing", current_step="Crawling", progress_percentage=25, message="Working")
    assert updated.status == "processing"
    assert updated.progress_percentage == 25
    assert get_job(job.job_id).current_step == "Crawling"


def test_delete_source_cleans_vectors_and_metadata(monkeypatch):
    fake_repo = FakeRepo()
    fake_vectors = FakeVectorStore()
    monkeypatch.setattr(source_management, "SupabaseRepository", lambda: fake_repo)
    monkeypatch.setattr(source_management, "get_vector_store", lambda: fake_vectors)

    result = source_management.delete_source("src_1")

    assert result["deleted"] is True
    assert "src_1" in fake_vectors.deleted_sources
    assert "chunks:src_1" in fake_repo.deleted_sources
    assert "src_1" in fake_repo.deleted_sources


def test_retrieve_knowledgebase_detail(monkeypatch):
    fake_repo = FakeRepo()
    monkeypatch.setattr(source_management, "SupabaseRepository", lambda: fake_repo)

    detail = source_management.get_knowledgebase_detail("kb_1")
    assert isinstance(detail, KnowledgebaseDetail)
    assert detail.source_count == 1
    assert detail.chunks_count == 4
    assert detail.sources[0].knowledgebase_name == "Example"


def test_recrawl_uses_existing_website_target(monkeypatch):
    fake_repo = FakeRepo()
    monkeypatch.setattr(source_management, "SupabaseRepository", lambda: fake_repo)
    monkeypatch.setattr(source_management, "delete_knowledgebase", lambda knowledgebase_id: {"deleted": True, "knowledgebase_id": knowledgebase_id})

    expected_response = WebsiteCrawlResponse(
        knowledgebase_id="kb_new",
        status="ready",
        crawl_summary=CrawlSummaryResponse(
            starting_url="https://example.com",
            normalized_url="https://example.com",
            pages_attempted=1,
            pages_successfully_ingested=1,
            pages_skipped=0,
            failed_pages={},
            total_chunks_created=2,
            warnings=[],
        ),
        sources_created=[
            IngestResponse(
                knowledgebase_id="kb_new",
                source_id="src_new",
                source_type="website",
                canonical_ref="https://example.com",
                title="Example",
                status="ready",
                chunks_count=2,
            )
        ],
    )
    monkeypatch.setattr(source_management, "crawl_website_ingest", lambda url, max_pages=10, max_depth=1, **kwargs: expected_response)

    result = source_management.recrawl_website(RecrawlRequest(knowledgebase_id="kb_1", max_pages=10, max_depth=1))
    assert result.knowledgebase_id == "kb_new"


def test_start_website_ingest_job_completes(monkeypatch):
    expected_response = WebsiteCrawlResponse(
        knowledgebase_id="kb_new",
        status="ready",
        crawl_summary=CrawlSummaryResponse(
            starting_url="https://example.com",
            normalized_url="https://example.com",
            pages_attempted=1,
            pages_successfully_ingested=1,
            pages_skipped=0,
            failed_pages={},
            total_chunks_created=2,
            warnings=[],
        ),
        sources_created=[
            IngestResponse(
                knowledgebase_id="kb_new",
                source_id="src_new",
                source_type="website",
                canonical_ref="https://example.com",
                title="Example",
                status="ready",
                chunks_count=2,
            )
        ],
    )
    monkeypatch.setattr(ingestion_jobs, "crawl_website_ingest", lambda *args, **kwargs: expected_response)

    job = ingestion_jobs.start_website_ingest_job("https://example.com", 2, 1)
    for _ in range(20):
        status = get_job(job["job_id"])
        if status and status.status == "completed":
            break
        time.sleep(0.1)

    final_job = get_job(job["job_id"])
    assert final_job is not None
    assert final_job.status == "completed"
    assert final_job.result["knowledgebase_id"] == "kb_new"
