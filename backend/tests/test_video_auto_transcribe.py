from __future__ import annotations

import sys
import types

import pytest

from app.models.schemas import TranscriptSegment, VideoTranscriptResult
from app.services import ingestion_pipeline
from app.services.video_transcriber import transcribe_youtube_video
from app.utils.exceptions import VideoAutoTranscriptionError


class _DummyEmbedder:
    def embed_documents(self, texts):
        return [[0.01] * 8 for _ in texts]


class _DummyVectorStore:
    def __init__(self):
        self.last_upsert = None

    def upsert_chunks(self, **kwargs):
        self.last_upsert = kwargs


class _DummyRepo:
    def __init__(self):
        self.kb = None
        self.source = None

    def get_knowledgebase_by_canonical_ref(self, canonical_ref: str):
        return None

    def get_source_by_canonical_ref(self, canonical_ref: str):
        return None

    def get_chunks_count(self, knowledgebase_id: str):
        return 0

    def create_knowledgebase(self, *, name: str, source_type: str, canonical_ref: str):
        self.kb = {"id": "kb_auto_1", "name": name, "source_type": source_type, "canonical_ref": canonical_ref}
        return self.kb

    def create_source(self, **kwargs):
        self.source = {"id": "src_auto_1", **kwargs}
        return self.source

    def insert_chunks(self, **kwargs):
        return None

    def update_knowledgebase_status(self, knowledgebase_id: str, status: str):
        return None


def _install_fake_modules(monkeypatch, *, duration: float = 120.0):
    class _FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def extract_info(self, url, download=False):
            if not download:
                return {
                    "id": "abcdefghijk",
                    "extractor": "youtube",
                    "duration": duration,
                    "title": "Demo Video",
                    "is_live": False,
                }
            return {"id": "abcdefghijk", "ext": "m4a"}

    fake_yt_dlp = types.SimpleNamespace(YoutubeDL=_FakeYoutubeDL)

    class _FakeWhisperModel:
        def __init__(self, model_name, compute_type="int8"):
            self.model_name = model_name
            self.compute_type = compute_type

        def transcribe(self, audio_path, beam_size=1, vad_filter=True, task="transcribe"):
            segments = [
                types.SimpleNamespace(text="Hello there", start=0.0, end=2.0),
                types.SimpleNamespace(text="General Kenobi", start=2.0, end=4.0),
            ]
            return segments, types.SimpleNamespace(language="en")

    fake_faster_whisper = types.SimpleNamespace(WhisperModel=_FakeWhisperModel)

    monkeypatch.setitem(sys.modules, "yt_dlp", fake_yt_dlp)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_faster_whisper)


class _FakeTempFile:
    def __init__(self, size=1024):
        self._size = size

    def stat(self):
        return types.SimpleNamespace(st_size=self._size)


def test_video_auto_transcribe_dependency_missing(monkeypatch):
    _install_fake_modules(monkeypatch)

    original_import = __import__

    def _raising_import(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _raising_import)

    with pytest.raises(VideoAutoTranscriptionError) as exc_info:
        transcribe_youtube_video("https://www.youtube.com/watch?v=abcdefghijk")

    assert exc_info.value.error_code == "TRANSCRIPTION_DEPENDENCY_MISSING"


def test_video_auto_transcribe_rejects_too_long_video(monkeypatch):
    _install_fake_modules(monkeypatch, duration=3600.0)
    monkeypatch.setattr("app.services.video_transcriber._pick_downloaded_audio_file", lambda *_: _FakeTempFile())

    with pytest.raises(VideoAutoTranscriptionError) as exc_info:
        transcribe_youtube_video("https://www.youtube.com/watch?v=abcdefghijk")

    assert exc_info.value.error_code == "VIDEO_TOO_LONG"


def test_video_auto_transcribe_mocked_segments(monkeypatch):
    _install_fake_modules(monkeypatch, duration=100.0)
    monkeypatch.setattr("app.services.video_transcriber._pick_downloaded_audio_file", lambda *_: _FakeTempFile())

    result = transcribe_youtube_video("https://www.youtube.com/watch?v=abcdefghijk")

    assert result.video_id == "abcdefghijk"
    assert result.transcript_origin == "auto_transcribed"
    assert result.segments
    assert result.segments[0].start_time == 0.0
    assert result.segments[0].end_time == 2.0


def test_auto_transcribed_ingest_preserves_timestamps(monkeypatch):
    fake_repo = _DummyRepo()
    fake_vectors = _DummyVectorStore()

    fake_transcript = VideoTranscriptResult(
        video_id="abcdefghijk",
        canonical_url="https://www.youtube.com/watch?v=abcdefghijk",
        title="Auto Transcript Demo",
        duration_seconds=90.0,
        transcription_model="base",
        transcript_origin="auto_transcribed",
        segments=[
            TranscriptSegment(text="First sentence", start_time=0.0, duration=2.0, end_time=2.0),
            TranscriptSegment(text="Second sentence", start_time=2.0, duration=2.0, end_time=4.0),
        ],
        warnings=[],
    )

    monkeypatch.setattr(ingestion_pipeline, "SupabaseRepository", lambda: fake_repo)
    monkeypatch.setattr(ingestion_pipeline, "get_vector_store", lambda: fake_vectors)
    monkeypatch.setattr(ingestion_pipeline, "get_embedding_service", lambda: _DummyEmbedder())
    monkeypatch.setattr(ingestion_pipeline, "transcribe_youtube_video", lambda *_args, **_kwargs: fake_transcript)

    result = ingestion_pipeline.ingest_video_auto_transcribe("https://www.youtube.com/watch?v=abcdefghijk")

    assert result.source_type == "video"
    assert result.transcript_origin == "auto_transcribed"
    assert result.chunks_count > 0
    assert fake_vectors.last_upsert is not None
    overview_meta = fake_vectors.last_upsert["chunks"][0].extra_metadata
    assert overview_meta["chunk_kind"] == "source_overview"
    assert overview_meta["overview_type"] == "video"
    assert overview_meta["timestamp_label"] == "Full video"

    detail_meta = fake_vectors.last_upsert["chunks"][1].extra_metadata
    assert detail_meta["has_timestamps"] is True
    assert detail_meta["transcript_origin"] == "auto_transcribed"
    assert "timestamp_label" in detail_meta


def test_auto_transcribe_reuses_existing_video(monkeypatch):
    class _ExistingRepo(_DummyRepo):
        def get_knowledgebase_by_canonical_ref(self, canonical_ref: str):
            return {"id": "kb_existing", "canonical_ref": canonical_ref, "source_type": "video"}

        def get_source_by_canonical_ref(self, canonical_ref: str):
            return {
                "id": "src_existing",
                "title": "Existing Video",
                "meta": {"video_id": "abcdefghijk", "transcript_duration": 90.0, "transcript_origin": "auto_transcribed"},
            }

        def get_chunks_count(self, knowledgebase_id: str):
            return 9

    fake_repo = _ExistingRepo()
    monkeypatch.setattr(ingestion_pipeline, "SupabaseRepository", lambda: fake_repo)

    called = {"value": False}

    def _should_not_transcribe(*_args, **_kwargs):
        called["value"] = True
        raise AssertionError("Transcription should not run for existing ready source")

    monkeypatch.setattr(ingestion_pipeline, "transcribe_youtube_video", _should_not_transcribe)

    result = ingestion_pipeline.ingest_video_auto_transcribe("https://www.youtube.com/watch?v=abcdefghijk")

    assert result.reused_existing is True
    assert result.source_id == "src_existing"
    assert result.chunks_count == 9
    assert called["value"] is False
