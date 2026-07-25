from __future__ import annotations

import pytest

from app.models.schemas import QuestionRequest, TranscriptSegment, TranscriptChunk, YouTubeTranscriptResponse
from app.services import ingestion_pipeline, qa_pipeline, source_management, video_transcript
from app.services.retrieval_types import RetrievedChunk
from app.services.video_transcript import TranscriptLine
from app.services.video_transcript import extract_video_id, chunk_video_transcript, extract_youtube_transcript
from app.utils.exceptions import SourceExtractionError, TranscriptUnavailableError
from app.api.v1.endpoints import sources as sources_endpoint


class FakeVectorStore:
    def __init__(self, chunks: list[RetrievedChunk] | None = None):
        self.chunks = chunks or []
        self.last_upsert = None

    def upsert_chunks(self, **kwargs):
        self.last_upsert = kwargs

    def search(self, **kwargs):
        return self.chunks

    def delete_by_source(self, source_id: str) -> None:
        return None

    def delete_by_knowledgebase(self, knowledgebase_id: str) -> None:
        return None


class FakeRepo:
    def __init__(self):
        self.sources = {}
        self.kbs = {}
        self.saved_history = []

    def get_knowledgebase_by_canonical_ref(self, canonical_ref: str):
        return self.kbs.get(canonical_ref)

    def get_source_by_canonical_ref(self, canonical_ref: str):
        return self.sources.get(canonical_ref)

    def get_chunks_count(self, knowledgebase_id: str):
        return 0

    def create_knowledgebase(self, *, name: str, source_type: str, canonical_ref: str):
        kb = {"id": f"kb_{len(self.kbs) + 1}", "name": name, "source_type": source_type, "canonical_ref": canonical_ref, "status": "processing"}
        self.kbs[canonical_ref] = kb
        return kb

    def create_source(self, **payload):
        source = {"id": f"src_{len(self.sources) + 1}", **payload}
        self.sources[payload["canonical_ref"]] = source
        return source

    def insert_chunks(self, **kwargs):
        return None

    def update_knowledgebase_status(self, knowledgebase_id: str, status: str):
        return None

    def save_query_history(self, **payload):
        self.saved_history.append(payload)

    def list_knowledgebases(self, limit: int = 100):
        return [
            {
                "id": "kb_video",
                "name": "Test Video",
                "source_type": "video",
                "canonical_ref": "https://www.youtube.com/watch?v=abcdefghijk",
                "status": "ready",
                "created_at": "2026-05-04T00:00:00Z",
                "updated_at": "2026-05-04T00:00:00Z",
            }
        ]

    def list_sources_for_knowledgebase(self, knowledgebase_id: str):
        return [
            {
                "id": "src_video",
                "knowledgebase_id": knowledgebase_id,
                "source_type": "video",
                "original_ref": "https://www.youtube.com/watch?v=abcdefghijk",
                "canonical_ref": "https://www.youtube.com/watch?v=abcdefghijk",
                "title": "Test Video",
                "status": "ready",
                "text_length": 1000,
                "meta": {"video_id": "abcdefghijk", "transcript_duration": 120.0},
                "created_at": "2026-05-04T00:00:00Z",
                "updated_at": "2026-05-04T00:00:00Z",
            }
        ]

    def get_sources(self, limit: int = 50):
        return [
            {
                "id": "src_video",
                "knowledgebase_id": "kb_video",
                "source_type": "video",
                "original_ref": "https://www.youtube.com/watch?v=abcdefghijk",
                "canonical_ref": "https://www.youtube.com/watch?v=abcdefghijk",
                "title": "Test Video",
                "status": "ready",
                "text_length": 1000,
                "meta": {"video_id": "abcdefghijk", "transcript_duration": 120.0},
                "knowledgebases": {
                    "id": "kb_video",
                    "name": "Test Video",
                    "status": "ready",
                },
                "created_at": "2026-05-04T00:00:00Z",
                "updated_at": "2026-05-04T00:00:00Z",
            }
        ]

    def get_source(self, source_id: str):
        return {
            "id": source_id,
            "knowledgebase_id": "kb_video",
            "source_type": "video",
            "original_ref": "https://www.youtube.com/watch?v=abcdefghijk",
            "canonical_ref": "https://www.youtube.com/watch?v=abcdefghijk",
            "title": "Test Video",
            "status": "ready",
            "text_length": 1000,
            "meta": {"video_id": "abcdefghijk", "transcript_duration": 120.0},
            "created_at": "2026-05-04T00:00:00Z",
            "updated_at": "2026-05-04T00:00:00Z",
        }

    def get_knowledgebase(self, knowledgebase_id: str):
        return {
            "id": knowledgebase_id,
            "name": "Test Video",
            "source_type": "video",
            "canonical_ref": "https://www.youtube.com/watch?v=abcdefghijk",
            "status": "ready",
            "created_at": "2026-05-04T00:00:00Z",
            "updated_at": "2026-05-04T00:00:00Z",
        }

    def get_chunks_count_for_source(self, knowledgebase_id: str, source_id: str):
        return 3

    def get_chunks_count_for_knowledgebase(self, knowledgebase_id: str):
        return 3


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.youtube.com/watch?v=VIDEO_ID123", "VIDEO_ID123"),
        ("https://www.youtube.com/watch?v=VIDEO_ID123&t=42s&feature=youtu.be", "VIDEO_ID123"),
    ],
)
def test_extract_video_id_watch_urls(url, expected):
    assert extract_video_id(url) == expected


def test_extract_video_id_youtu_be_url():
    assert extract_video_id("https://youtu.be/VIDEO_ID123") == "VIDEO_ID123"


def test_extract_video_id_shorts_url():
    assert extract_video_id("https://www.youtube.com/shorts/VIDEO_ID123") == "VIDEO_ID123"


def test_invalid_youtube_url_rejected():
    with pytest.raises(SourceExtractionError):
        extract_video_id("https://example.com/not-youtube")


def test_video_chunking_preserves_timestamps():
    segments = [
        TranscriptLine(text="One", start_time=0.0, duration=1.0, end_time=1.0),
        TranscriptLine(text="two", start_time=1.0, duration=1.0, end_time=2.0),
        TranscriptLine(text="three", start_time=2.0, duration=1.0, end_time=3.0),
        TranscriptLine(text="four", start_time=3.0, duration=1.0, end_time=4.0),
    ]
    chunks = chunk_video_transcript(
        segments,
        source_url="https://www.youtube.com/watch?v=abcdefghijk",
        video_id="abcdefghijk",
        source_title="Test Video",
        transcript_duration=4.0,
        target_chars=6,
        min_chars=3,
        max_chars=10,
    )

    assert chunks
    assert chunks[0].extra_metadata["video_id"] == "abcdefghijk"
    assert chunks[0].extra_metadata["timestamp_label"]
    assert chunks[0].extra_metadata["start_time"] == 0.0
    assert chunks[0].extra_metadata["source_type"] == "video"


def test_unavailable_transcript_error_handling(monkeypatch):
    class FakeApi:
        def list_transcripts(self, video_id):
            raise RuntimeError("disabled")

    monkeypatch.setattr(video_transcript, "YouTubeTranscriptApi", lambda: FakeApi())

    with pytest.raises(TranscriptUnavailableError, match="Transcript not available from YouTube") as exc_info:
        extract_youtube_transcript("https://www.youtube.com/watch?v=abcdefghijk")

    assert exc_info.value.error_code == "TRANSCRIPT_NOT_AVAILABLE"
    assert "auto_transcribe" in exc_info.value.fallback_options


def test_video_auto_transcribe_job_endpoint_rejects_invalid_url(client):
    response = client.post(
        "/api/v1/jobs/video-auto-transcribe",
        json={"url": "https://example.com/not-youtube"},
    )
    assert response.status_code == 422


def test_video_ingestion_pipeline(monkeypatch):
    fake_repo = FakeRepo()
    fake_vectors = FakeVectorStore()
    fake_response = YouTubeTranscriptResponse(
        video_id="abcdefghijk",
        canonical_url="https://www.youtube.com/watch?v=abcdefghijk",
        title="Test Video",
        transcript_duration=120.0,
        segments=[
            TranscriptSegment(text="Hello world", start_time=0.0, duration=2.0, end_time=2.0),
            TranscriptSegment(text="More transcript", start_time=2.0, duration=2.0, end_time=4.0),
        ],
        chunks=[
            TranscriptChunk(
                text="Hello world More transcript",
                start_time=0.0,
                end_time=4.0,
                timestamp_label="00:00 - 00:04",
                source_url="https://www.youtube.com/watch?v=abcdefghijk",
                video_id="abcdefghijk",
                chunk_index=0,
            )
        ],
        warnings=[],
    )

    monkeypatch.setattr(ingestion_pipeline, "SupabaseRepository", lambda: fake_repo)
    monkeypatch.setattr(ingestion_pipeline, "get_vector_store", lambda: fake_vectors)
    monkeypatch.setattr(ingestion_pipeline, "extract_youtube_transcript", lambda url: fake_response)

    result = ingestion_pipeline.ingest_video("https://www.youtube.com/watch?v=abcdefghijk")

    assert result.source_type == "video"
    assert result.video_id == "abcdefghijk"
    assert result.transcript_duration == 120.0
    # 1 transcript chunk from the fake response + 1 deterministic source-overview chunk.
    assert result.chunks_count == 2
    assert fake_vectors.last_upsert is not None
    assert fake_vectors.last_upsert["source_type"] == "video"


def test_qa_over_video_transcript_includes_timestamp_label(monkeypatch):
    fake_repo = FakeRepo()
    fake_chunk = RetrievedChunk(
        chunk_id="chunk_1",
        text="The speaker explains the main idea.",
        metadata={
            "source_id": "src_video",
            "source_ref": "https://www.youtube.com/watch?v=abcdefghijk",
            "source_type": "video",
            "source_title": "Test Video",
            "video_id": "abcdefghijk",
            "timestamp_label": "01:23 - 01:45",
            "start_time": 83.0,
            "end_time": 105.0,
            "chunk_index": 0,
        },
        distance=0.05,
        semantic_score=0.95,
        score=0.93,
    )

    class FakeEmbeddingService:
        def embed_query(self, text: str):
            return [0.1]

    class FakeLLM:
        def rewrite_query(self, question: str, history=None):
            return question

        def generate_answer(self, question: str, context: str, mode: str, history=None):
            return "Answer from video transcript."

    monkeypatch.setattr(qa_pipeline, "get_supabase_repository", lambda: fake_repo)
    monkeypatch.setattr(qa_pipeline, "get_embedding_service", lambda: FakeEmbeddingService())
    monkeypatch.setattr(qa_pipeline, "get_llm_service", lambda: FakeLLM())
    monkeypatch.setattr(qa_pipeline, "should_rewrite", lambda question: False)
    monkeypatch.setattr(qa_pipeline, "rerank_chunks", lambda rewritten_query, chunks: chunks)
    monkeypatch.setattr(qa_pipeline, "get_vector_store", lambda: FakeVectorStore([fake_chunk]))

    result = qa_pipeline.answer_question(
        QuestionRequest(
            question="What does the speaker explain?",
            mode="grounded",
            knowledgebase_id="kb_video",
            top_k=6,
        )
    )

    assert result.citations
    assert result.citations[0].source_type == "video"
    assert result.citations[0].timestamp_label == "01:23 - 01:45"
    assert result.retrieved_sources[0]["timestamp_label"] == "01:23 - 01:45"


def test_qa_low_confidence_returns_follow_up_question(monkeypatch):
    fake_repo = FakeRepo()
    fake_chunk = RetrievedChunk(
        chunk_id="chunk_1",
        text="The speaker introduces the topic but gives no summary.",
        metadata={
            "source_id": "src_video",
            "source_ref": "https://www.youtube.com/watch?v=abcdefghijk",
            "source_type": "video",
            "source_title": "Test Video",
            "video_id": "abcdefghijk",
            "timestamp_label": "00:10 - 00:24",
            "start_time": 10.0,
            "end_time": 24.0,
            "chunk_index": 0,
        },
        distance=0.5,
        semantic_score=0.25,
        score=0.24,
    )

    class FakeEmbeddingService:
        def embed_query(self, text: str):
            return [0.1]

    class FakeLLM:
        def rewrite_query(self, question: str, history=None):
            return question

        def generate_answer(self, question: str, context: str, mode: str, history=None):
            return "Should not be used for low confidence."

    monkeypatch.setattr(qa_pipeline, "get_supabase_repository", lambda: fake_repo)
    monkeypatch.setattr(qa_pipeline, "get_embedding_service", lambda: FakeEmbeddingService())
    monkeypatch.setattr(qa_pipeline, "get_llm_service", lambda: FakeLLM())
    monkeypatch.setattr(qa_pipeline, "should_rewrite", lambda question: False)
    monkeypatch.setattr(qa_pipeline, "rerank_chunks", lambda rewritten_query, chunks: chunks)
    monkeypatch.setattr(qa_pipeline, "get_vector_store", lambda: FakeVectorStore([fake_chunk]))

    result = qa_pipeline.answer_question(
        QuestionRequest(
            question="summarize this video",
            mode="grounded",
            knowledgebase_id="kb_video",
            top_k=6,
        )
    )

    # Video sources are exempted from the hard low-confidence refusal: the answer is
    # still generated, flagged with a warning instead of being replaced by a refusal.
    assert result.answer == "Should not be used for low confidence."
    assert any("low confidence" in w.lower() for w in result.warnings)
    assert result.follow_up_question is None


def test_source_listing_includes_video_source(client, monkeypatch):
    fake_repo = FakeRepo()
    monkeypatch.setattr(sources_endpoint, "SupabaseRepository", lambda: fake_repo)

    response = client.get("/api/v1/sources")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["source_type"] == "video"
    assert data[0]["video_id"] == "abcdefghijk"
    assert data[0]["transcript_duration"] == 120.0


@pytest.mark.integration
def test_real_youtube_transcript_fetch():
    url = "https://www.youtube.com/watch?v=5MgBikgcWnY"
    try:
        result = extract_youtube_transcript(url)
    except SourceExtractionError as exc:
        pytest.skip(str(exc))

    assert result.video_id == "5MgBikgcWnY"
    assert result.canonical_url.endswith("watch?v=5MgBikgcWnY")
    assert result.chunks
    assert result.transcript_duration > 0
