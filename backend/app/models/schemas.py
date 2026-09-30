from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


Mode = Literal["grounded", "exploratory"]
SourceType = Literal["website", "pdf", "video", "github"]


class WebsiteIngestRequest(BaseModel):
    url: HttpUrl
    max_pages: int = Field(default=10, ge=1, le=100)
    max_depth: int = Field(default=1, ge=1, le=3)


class VideoIngestRequest(BaseModel):
    url: HttpUrl


class VideoAutoTranscribeRequest(BaseModel):
    url: HttpUrl


class GitHubIngestRequest(BaseModel):
    url: HttpUrl
    branch: Optional[str] = None


class CrawlSummaryResponse(BaseModel):
    starting_url: str
    normalized_url: str
    pages_attempted: int
    pages_successfully_ingested: int
    pages_skipped: int
    failed_pages: dict[str, str] = Field(default_factory=dict)
    total_chunks_created: int
    extraction_method: str = "playwright"
    warnings: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    citation_id: str
    chunk_id: str
    source_id: str
    source_type: SourceType
    source_ref: str
    source_title: Optional[str] = None
    snippet: str
    page_number: Optional[int] = None
    chunk_index: int
    score: float
    video_id: Optional[str] = None
    timestamp_label: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    file_path: Optional[str] = None
    language: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    branch: Optional[str] = None
    file_url: Optional[str] = None


class IngestResponse(BaseModel):
    knowledgebase_id: str
    source_id: str
    source_type: SourceType
    canonical_ref: str
    title: Optional[str] = None
    status: str
    chunks_count: int
    reused_existing: bool = False
    page_count: Optional[int] = None
    crawled_pages: Optional[int] = None
    transcript_duration: Optional[float] = None
    duration_seconds: Optional[float] = None
    video_id: Optional[str] = None
    transcript_origin: Optional[str] = None
    # GitHub fields
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    branch: Optional[str] = None
    detected_languages: Optional[list[str]] = None
    files_indexed: Optional[int] = None
    files_skipped: Optional[int] = None
    warnings: list[str] = Field(default_factory=list)


class WebsiteCrawlResponse(BaseModel):
    knowledgebase_id: str
    status: str
    crawl_summary: CrawlSummaryResponse
    sources_created: list[IngestResponse]


class ConversationTurn(BaseModel):
    question: str = Field(max_length=2000)
    answer: str = Field(max_length=6000)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    mode: Mode = "grounded"
    knowledgebase_id: Optional[str] = None
    source_id: Optional[str] = None
    # Combine multiple sources (any mix of types) into one question. When set,
    # takes precedence over knowledgebase_id/source_id.
    source_ids: Optional[list[str]] = Field(default=None, max_length=12)
    # Prior turns in this chat thread, oldest first, for follow-up questions.
    history: Optional[list[ConversationTurn]] = Field(default=None, max_length=6)
    top_k: int = Field(default=6, ge=1, le=15)


class AnswerResponse(BaseModel):
    answer: str
    mode: Mode
    question: str
    rewritten_query: str
    confidence_score: float
    confidence_label: str
    confidence_reason: str
    retrieved_source_count: int
    citations: list[Citation]
    retrieved_sources: list[dict[str, Any]]
    follow_up_question: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class SourceSummary(BaseModel):
    knowledgebase_id: str
    knowledgebase_name: Optional[str] = None
    source_id: str
    source_type: SourceType
    title: Optional[str] = None
    canonical_ref: str
    original_ref: str
    status: str
    text_length: int = 0
    chunks_count: int = 0
    page_count: Optional[int] = None
    crawled_pages: Optional[int] = None
    transcript_duration: Optional[float] = None
    video_id: Optional[str] = None
    transcript_origin: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class SourceDetail(BaseModel):
    knowledgebase_id: str
    knowledgebase_name: Optional[str] = None
    source_id: str
    source_type: SourceType
    title: Optional[str] = None
    canonical_ref: str
    original_ref: str
    status: str
    text_length: int = 0
    chunks_count: int = 0
    page_count: Optional[int] = None
    crawled_pages: Optional[int] = None
    transcript_duration: Optional[float] = None
    video_id: Optional[str] = None
    transcript_origin: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SourceOverviewResponse(BaseModel):
    summary: Optional[str] = None


class BriefItem(BaseModel):
    text: str
    citation: Optional[Citation] = None


class BriefSection(BaseModel):
    title: str
    detail: str = ""
    citation: Optional[Citation] = None


class SourceBrief(BaseModel):
    version: int
    source_type: str
    summary: str
    key_points: list[BriefItem]
    section_label: str
    sections: list[BriefSection]
    questions: list[str]
    generated_at: str


class EvidenceRequest(BaseModel):
    chunk_id: str = Field(min_length=1, max_length=100)
    # The answer sentences that cite this chunk.
    claims: list[str] = Field(default_factory=list, max_length=10)


class EvidenceHighlight(BaseModel):
    start: int
    end: int
    score: float


class EvidenceResponse(BaseModel):
    chunk_id: str
    text: str
    highlights: list[EvidenceHighlight]


class KnowledgebaseDetail(BaseModel):
    knowledgebase_id: str
    name: str
    source_type: SourceType
    canonical_ref: str
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    source_count: int = 0
    chunks_count: int = 0
    sources: list[SourceSummary] = Field(default_factory=list)


class KnowledgebaseGroup(BaseModel):
    knowledgebase: KnowledgebaseDetail
    sources: list[SourceSummary] = Field(default_factory=list)


class JobStatusResponse(BaseModel):
    job_id: str
    operation: str
    source_type: SourceType
    status: str
    current_step: str
    progress_percentage: int
    message: str
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RecrawlRequest(BaseModel):
    knowledgebase_id: Optional[str] = None
    canonical_ref: Optional[str] = None
    max_pages: int = Field(default=10, ge=1, le=100)
    max_depth: int = Field(default=1, ge=1, le=3)


class TranscriptSegment(BaseModel):
    text: str
    start_time: float
    duration: float
    end_time: float


class TranscriptChunk(BaseModel):
    text: str
    start_time: float
    end_time: float
    timestamp_label: str
    source_url: str
    video_id: str
    chunk_index: int


class RepoChunk(BaseModel):
    file_path: str
    language: str
    start_line: int
    end_line: int
    chunk_index: int
    text: str
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    branch: Optional[str] = None


class YouTubeTranscriptResponse(BaseModel):
    video_id: str
    canonical_url: str
    title: str
    transcript_duration: float
    segments: list[TranscriptSegment]
    chunks: list[TranscriptChunk]
    warnings: list[str] = Field(default_factory=list)


class TranscriptUnavailableResponse(BaseModel):
    error_code: str = "TRANSCRIPT_NOT_AVAILABLE"
    message: str
    fallback_options: list[str] = Field(default_factory=lambda: ["auto_transcribe"])


class VideoTranscriptResult(BaseModel):
    video_id: str
    canonical_url: str
    title: str
    duration_seconds: float
    segments: list[TranscriptSegment]
    transcription_model: str
    transcript_origin: str = "auto_transcribed"
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str
