class SageError(Exception):
    """Base SAGE exception."""


class SourceExtractionError(SageError):
    """Raised when useful source text cannot be extracted."""


class TranscriptUnavailableError(SourceExtractionError):
    """Raised when YouTube transcript retrieval fails but auto-transcribe fallback is possible."""

    def __init__(
        self,
        message: str = "Transcript not available from YouTube.",
        *,
        error_code: str = "TRANSCRIPT_NOT_AVAILABLE",
        fallback_options: list[str] | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.fallback_options = fallback_options or ["auto_transcribe"]

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": str(self),
            "fallback_options": self.fallback_options,
        }


class VideoAutoTranscriptionError(SourceExtractionError):
    """Raised for auto-transcription specific failures with stable error codes."""

    def __init__(self, message: str, *, error_code: str):
        super().__init__(message)
        self.error_code = error_code

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": str(self),
        }


class WebsiteIngestionError(SourceExtractionError):
    """Raised for website ingestion failures with stable error codes and HTTP status mapping."""

    def __init__(self, message: str, *, error_code: str, status_code: int):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": str(self),
        }


class WebsiteNoUsableTextError(WebsiteIngestionError):
    """Raised when crawl succeeds technically but yields no usable text for ingestion."""

    def __init__(
        self,
        message: str = (
            "No usable text could be extracted from this website. "
            "The page may contain very little text, block crawlers, or require JavaScript/login access."
        ),
    ):
        super().__init__(message, error_code="WEBSITE_NO_USABLE_TEXT", status_code=422)


class WebsiteInvalidUrlError(WebsiteIngestionError):
    """Raised when the submitted website URL is invalid for crawling."""

    def __init__(self, message: str = "Invalid website URL."):
        super().__init__(message, error_code="WEBSITE_INVALID_URL", status_code=400)


class WebsiteCrawlTimeoutError(WebsiteIngestionError):
    """Raised when crawling times out before usable pages are ingested."""

    def __init__(
        self,
        message: str = "Website crawl timed out before any usable page could be extracted.",
    ):
        super().__init__(message, error_code="WEBSITE_CRAWL_TIMEOUT", status_code=504)


class UnsupportedFileError(SageError):
    """Raised for unsupported uploads."""
