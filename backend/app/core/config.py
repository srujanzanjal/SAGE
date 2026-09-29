from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from backend/.env."""

    app_name: str = "SAGE MVP API"
    app_env: str = "development"
    api_prefix: str = "/api/v1"

    # Required for real integration testing.
    supabase_url: Optional[str] = Field(default=None, alias="SUPABASE_URL")
    supabase_key: Optional[str] = Field(default=None, alias="SUPABASE_KEY")
    groq_api_key: Optional[str] = Field(default=None, alias="GROQ_API_KEY")
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")

    # Configurable model names.
    groq_model: str = Field(default="qwen/qwen3.8-27b", alias="GROQ_MODEL")
    # Extra free Groq models tried in order when the ones before are rate-limited.
    groq_fallback_models: str = Field(default="openai/gpt-oss-20b,openai/gpt-oss-120b", alias="GROQ_FALLBACK_MODELS")
    # Gemini is the primary LLM; the fast model handles query rewriting and translation.
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    gemini_fast_model: str = Field(default="gemini-2.5-flash-lite", alias="GEMINI_FAST_MODEL")
    embedding_model_name: str = Field(default="all-MiniLM-L6-v2", alias="EMBEDDING_MODEL_NAME")

    # Local Chroma persistence.
    chroma_persist_dir: str = Field(default="./chroma_data", alias="CHROMA_PERSIST_DIR")
    chroma_collection_name: str = Field(default="sage_chunks", alias="CHROMA_COLLECTION_NAME")

    # Data limits and retrieval tuning.
    max_upload_mb: int = Field(default=25, alias="MAX_UPLOAD_MB")
    max_website_chars: int = Field(default=250_000, alias="MAX_WEBSITE_CHARS")
    min_source_text_chars: int = Field(default=200, alias="MIN_SOURCE_TEXT_CHARS")
    chunk_size_chars: int = Field(default=1200, alias="CHUNK_SIZE_CHARS")
    chunk_overlap_chars: int = Field(default=180, alias="CHUNK_OVERLAP_CHARS")
    default_top_k: int = Field(default=6, alias="DEFAULT_TOP_K")
    request_timeout_seconds: int = Field(default=15, alias="REQUEST_TIMEOUT_SECONDS")
    llm_timeout_seconds: int = Field(default=30, alias="LLM_TIMEOUT_SECONDS")

    # Video auto-transcription safety/performance limits.
    video_auto_transcribe_max_duration_seconds: int = Field(default=900, alias="VIDEO_AUTO_TRANSCRIBE_MAX_DURATION_SECONDS")
    video_auto_transcribe_max_audio_mb: int = Field(default=100, alias="VIDEO_AUTO_TRANSCRIBE_MAX_AUDIO_MB")
    whisper_model_size: str = Field(default="tiny", alias="WHISPER_MODEL_SIZE")
    video_auto_transcribe_model: str = Field(default="tiny", alias="VIDEO_AUTO_TRANSCRIBE_MODEL")

    # Query history is opt-in to avoid storing user questions/answers by default.
    store_query_history: bool = Field(default=False, alias="STORE_QUERY_HISTORY")
    query_history_retention_days: int = Field(default=30, alias="QUERY_HISTORY_RETENTION_DAYS")
    query_history_timeout_seconds: float = Field(default=2.0, alias="QUERY_HISTORY_TIMEOUT_SECONDS")

    cors_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174", alias="CORS_ORIGINS")
    cors_origin_regex: str = Field(
        default=r"^https?://(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)(:\d+)?$",
        alias="CORS_ORIGIN_REGEX",
    )

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def cors_origin_pattern(self) -> str:
        return self.cors_origin_regex

    @property
    def groq_fallback_model_list(self) -> list[str]:
        return [m.strip() for m in self.groq_fallback_models.split(",") if m.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def selected_whisper_model_size(self) -> str:
        model = (self.whisper_model_size or self.video_auto_transcribe_model or "tiny").strip().lower()
        return model if model in {"tiny", "base", "small"} else "tiny"

    def require_supabase(self) -> None:
        missing = []
        if not self.supabase_url:
            missing.append("SUPABASE_URL")
        if not self.supabase_key:
            missing.append("SUPABASE_KEY")
        if missing:
            raise RuntimeError(f"Missing required Supabase environment variables: {', '.join(missing)}")

    def require_llm(self) -> None:
        if not self.gemini_api_key and not self.groq_api_key:
            raise RuntimeError("Set GEMINI_API_KEY and/or GROQ_API_KEY in backend/.env")


@lru_cache
def get_settings() -> Settings:
    return Settings()
