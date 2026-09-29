from __future__ import annotations

from types import SimpleNamespace

from app.models.schemas import IngestResponse, TranscriptSegment, VideoTranscriptResult
from app.services import ingestion_pipeline, qa_pipeline
from app.services.github_repo import RepoRef
from app.services.retrieval_types import RetrievedChunk
from app.services.source_overview import (
    create_overview_chunk,
    generate_pdf_overview,
    generate_video_overview,
    generate_website_overview,
)
from app.services.website_crawler import CrawlSummary, CrawledPage
from app.services.pdf_extractor import PdfExtractionResult


class FakeSettings:
    chunk_size_chars = 400
    chunk_overlap_chars = 0
    min_source_text_chars = 10
    max_website_chars = 100000


class FakeEmbeddingService:
    def embed_documents(self, documents):
        return [[0.0] * 3 for _ in documents]


class FakeVectorStore:
    def get_overview_chunks(self, source_ids):
        return []

    def get_edge_chunks(self, source_id, from_end, count=2):
        return []

    def __init__(self):
        self.calls = []

    def upsert_chunks(self, **kwargs):
        self.calls.append(kwargs)


class FakeRepo:
    def __init__(self, *, existing_source=None, existing_chunks=0):
        self.created_knowledgebases = []
        self.created_sources = []
        self.inserted_chunks = []
        self.updated_status = []
        self.existing_source = existing_source
        self.existing_chunks = existing_chunks

    def get_knowledgebase_by_canonical_ref(self, canonical_ref):
        if self.existing_source:
            return {"id": self.existing_source["knowledgebase_id"], "canonical_ref": canonical_ref, "source_type": self.existing_source["source_type"]}
        return None

    def get_source_by_canonical_ref(self, canonical_ref):
        return self.existing_source

    def get_chunks_count(self, knowledgebase_id):
        return self.existing_chunks

    def get_chunks_count_for_source(self, knowledgebase_id, source_id):
        return self.existing_chunks

    def create_knowledgebase(self, *, name, source_type, canonical_ref):
        payload = {"id": f"kb_{len(self.created_knowledgebases)+1}", "name": name, "source_type": source_type, "canonical_ref": canonical_ref}
        self.created_knowledgebases.append(payload)
        return payload

    def create_source(self, **kwargs):
        payload = {"id": f"src_{len(self.created_sources)+1}", **kwargs}
        self.created_sources.append(payload)
        return payload

    def update_knowledgebase_status(self, knowledgebase_id, status):
        self.updated_status.append((knowledgebase_id, status))

    def insert_chunks(self, **kwargs):
        self.inserted_chunks.append(kwargs)

    def list_sources_for_knowledgebase(self, knowledgebase_id):
        return [self.existing_source] if self.existing_source else []

    def delete_by_source(self, source_id):
        return None

    def delete_source_chunks(self, source_id):
        return None

    def delete_source(self, source_id):
        return []

    def delete_knowledgebase_chunks(self, knowledgebase_id):
        return None

    def delete_knowledgebase(self, knowledgebase_id):
        return []


def _wire_ingestion(monkeypatch, fake_repo, fake_vectors):
    monkeypatch.setattr(ingestion_pipeline, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(ingestion_pipeline, "SupabaseRepository", lambda: fake_repo)
    monkeypatch.setattr(ingestion_pipeline, "get_embedding_service", lambda: FakeEmbeddingService())
    monkeypatch.setattr(ingestion_pipeline, "get_vector_store", lambda: fake_vectors)


def test_source_overview_chunks_share_generic_metadata():
    overview = create_overview_chunk(
        source_type="video",
        overview_type="video",
        text="Video OVERVIEW\nTitle: Sample",
        source_ref="https://www.youtube.com/watch?v=xb0nLpdWttA",
        title="Sample",
        metadata={"video_id": "xb0nLpdWttA", "timestamp_label": "Full video", "start_time": 0, "end_time": 10},
    )
    assert overview.extra_metadata["chunk_kind"] == "source_overview"
    assert overview.extra_metadata["overview_type"] == "video"
    assert overview.extra_metadata["is_sage_overview"] is True
    assert overview.extra_metadata["timestamp_label"] == "Full video"


def test_build_context_labels_generic_overview_types():
    cases = [
        ("website", "Website Overview"),
        ("pdf", "PDF Overview"),
        ("video", "Video Overview"),
        ("github", "Repository Overview"),
    ]
    for overview_type, expected_label in cases:
        chunk = RetrievedChunk(
            chunk_id="c1",
            text="overview text",
            metadata={
                "source_id": "src_1",
                "source_type": overview_type,
                "source_ref": "ref",
                "source_title": "Title",
                "chunk_kind": "source_overview",
                "overview_type": overview_type,
                "file_path": "__SAGE_REPO_OVERVIEW__" if overview_type == "github" else None,
                "repo_owner": "octocat" if overview_type == "github" else None,
                "repo_name": "hello-world" if overview_type == "github" else None,
            },
            distance=0.1,
            semantic_score=0.9,
            score=0.9,
        )
        context, citations = qa_pipeline.build_context([chunk])
        assert expected_label in context
        assert citations[0].file_url is None


def test_crawl_website_ingest_includes_source_overview_chunk(monkeypatch):
    fake_repo = FakeRepo()
    fake_vectors = FakeVectorStore()
    _wire_ingestion(monkeypatch, fake_repo, fake_vectors)

    crawled_pages = [
        CrawledPage(url="https://example.com", normalized_url="https://example.com", title="Home", text="Welcome to the site. Inner voice and focus.", final_url="https://example.com"),
        CrawledPage(url="https://example.com/about", normalized_url="https://example.com/about", title="About", text="About the site and its purpose.", final_url="https://example.com/about"),
    ]
    crawl_summary = CrawlSummary(
        starting_url="https://example.com",
        normalized_url="https://example.com",
        pages_attempted=2,
        pages_successfully_ingested=2,
        pages_skipped=0,
        failed_pages={},
        total_chunks_created=0,
        extraction_method="playwright",
        warnings=[],
    )
    monkeypatch.setattr(ingestion_pipeline, "crawl_website", lambda url, max_pages=10, max_depth=1: (crawled_pages, crawl_summary))

    result = ingestion_pipeline.crawl_website_ingest("https://example.com", max_pages=2, max_depth=1)

    assert result.status == "ready"
    assert result.crawl_summary.total_chunks_created >= 2
    assert fake_vectors.calls
    chunks = fake_vectors.calls[0]["chunks"]
    assert chunks[0].extra_metadata["chunk_kind"] == "source_overview"
    assert chunks[0].extra_metadata["overview_type"] == "website"
    assert "WEBSITE OVERVIEW" in chunks[0].text


def test_ingest_pdf_includes_source_overview_chunk(monkeypatch):
    fake_repo = FakeRepo()
    fake_vectors = FakeVectorStore()
    _wire_ingestion(monkeypatch, fake_repo, fake_vectors)

    monkeypatch.setattr(ingestion_pipeline, "validate_pdf_upload", lambda filename, content_type, raw: None)
    monkeypatch.setattr(
        ingestion_pipeline,
        "extract_pdf_text",
        lambda filename, raw: PdfExtractionResult(
            title="Sample PDF",
            pages=[(1, "First page heading\nSome sample text about the topic."), (2, "Second page\nMore detail and a conclusion.")],
            page_count=2,
            text="First page heading Some sample text about the topic. Second page More detail and a conclusion.",
            warnings=[],
        ),
    )

    result = ingestion_pipeline.ingest_pdf("sample.pdf", "application/pdf", b"%PDF-1.4 fake")

    assert result.status == "ready"
    assert fake_vectors.calls
    chunks = fake_vectors.calls[0]["chunks"]
    assert chunks[0].extra_metadata["chunk_kind"] == "source_overview"
    assert chunks[0].extra_metadata["overview_type"] == "pdf"
    assert "PDF OVERVIEW" in chunks[0].text


def test_ingest_video_auto_transcribe_includes_source_overview_chunk(monkeypatch):
    fake_repo = FakeRepo()
    fake_vectors = FakeVectorStore()
    _wire_ingestion(monkeypatch, fake_repo, fake_vectors)

    monkeypatch.setattr(
        ingestion_pipeline,
        "transcribe_youtube_video",
        lambda url, progress_callback=None: VideoTranscriptResult(
            video_id="xb0nLpdWttA",
            canonical_url="https://www.youtube.com/watch?v=xb0nLpdWttA",
            title="Sample Video",
            duration_seconds=120.0,
            segments=[
                TranscriptSegment(text="First idea about the topic.", start_time=0.0, duration=10.0, end_time=10.0),
                TranscriptSegment(text="Second idea with more detail.", start_time=10.0, duration=10.0, end_time=20.0),
            ],
            transcription_model="tiny",
            transcript_origin="auto_transcribed",
            warnings=[],
        ),
    )

    result = ingestion_pipeline.ingest_video_auto_transcribe("https://www.youtube.com/watch?v=xb0nLpdWttA")

    assert result.status == "ready"
    assert fake_vectors.calls
    chunks = fake_vectors.calls[0]["chunks"]
    assert chunks[0].extra_metadata["chunk_kind"] == "source_overview"
    assert chunks[0].extra_metadata["overview_type"] == "video"
    assert chunks[0].extra_metadata["timestamp_label"] == "Full video"
    assert "VIDEO OVERVIEW" in chunks[0].text


def test_ingest_video_auto_transcribe_reuses_existing_source(monkeypatch):
    existing_source = {
        "id": "src_existing",
        "knowledgebase_id": "kb_existing",
        "source_type": "video",
        "title": "Already analyzed",
        "canonical_ref": "https://www.youtube.com/watch?v=xb0nLpdWttA",
        "meta": {"video_id": "xb0nLpdWttA", "transcript_duration": 120.0, "transcript_origin": "auto_transcribed"},
    }
    fake_repo = FakeRepo(existing_source=existing_source, existing_chunks=8)
    fake_vectors = FakeVectorStore()
    _wire_ingestion(monkeypatch, fake_repo, fake_vectors)
    monkeypatch.setattr(ingestion_pipeline, "transcribe_youtube_video", lambda url, progress_callback=None: (_ for _ in ()).throw(AssertionError("Should not transcribe again")))

    result = ingestion_pipeline.ingest_video_auto_transcribe("https://www.youtube.com/watch?v=xb0nLpdWttA")

    assert isinstance(result, IngestResponse)
    assert result.reused_existing is True
    assert result.source_id == "src_existing"
    assert result.chunks_count == 8
    assert not fake_vectors.calls

def test_position_questions_are_detected():
    assert qa_pipeline._position_asked("what is his advice at the end") == "end"
    assert qa_pipeline._position_asked("how does the talk conclude?") == "end"
    assert qa_pipeline._position_asked("what does he say in the intro") == "start"
    assert qa_pipeline._position_asked("what is RAG") is None
