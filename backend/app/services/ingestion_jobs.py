from __future__ import annotations

from threading import Thread
from typing import Any, Optional

from app.models.schemas import RecrawlRequest
from app.services.ingestion_pipeline import crawl_website_ingest, ingest_pdf, ingest_video, ingest_github, ingest_video_auto_transcribe
from app.services.job_tracker import create_job, job_to_dict, update_job
from app.services.source_management import recrawl_website
from app.utils.exceptions import TranscriptUnavailableError, VideoAutoTranscriptionError, WebsiteIngestionError


def _error_result_payload(exc: Exception) -> dict[str, Any] | None:
    if isinstance(exc, (TranscriptUnavailableError, VideoAutoTranscriptionError, WebsiteIngestionError)):
        return exc.to_dict()
    return None


def start_website_ingest_job(url: str, max_pages: int, max_depth: int) -> dict[str, Any]:
    job = create_job(operation="website_ingest", source_type="website", message="Queued website crawl")

    def runner() -> None:
        try:
            result = crawl_website_ingest(
                url,
                max_pages=max_pages,
                max_depth=max_depth,
                progress_callback=lambda step, pct, message: update_job(
                    job.job_id,
                    status="processing",
                    current_step=step,
                    progress_percentage=pct,
                    message=message,
                ),
            )
            update_job(
                job.job_id,
                status="completed",
                current_step="Ready",
                progress_percentage=100,
                message="Website crawl completed",
                result=result.model_dump(),
            )
        except Exception as exc:
            error_payload = _error_result_payload(exc)
            error_message = error_payload.get("message") if error_payload else str(exc)
            update_job(
                job.job_id,
                status="failed",
                current_step="Failed",
                progress_percentage=100,
                message="Website crawl failed",
                error=error_message,
                result=error_payload,
            )

    Thread(target=runner, daemon=True).start()
    return job_to_dict(job)


def start_pdf_ingest_job(filename: str, content_type: str | None, raw: bytes) -> dict[str, Any]:
    job = create_job(operation="pdf_ingest", source_type="pdf", message="Queued PDF ingestion")

    def runner() -> None:
        try:
            result = ingest_pdf(
                filename,
                content_type,
                raw,
                progress_callback=lambda step, pct, message: update_job(
                    job.job_id,
                    status="processing",
                    current_step=step,
                    progress_percentage=pct,
                    message=message,
                ),
            )
            update_job(
                job.job_id,
                status="completed",
                current_step="Ready",
                progress_percentage=100,
                message="PDF ingestion completed",
                result=result.model_dump(),
            )
        except Exception as exc:
            update_job(
                job.job_id,
                status="failed",
                current_step="Failed",
                progress_percentage=100,
                message="PDF ingestion failed",
                error=str(exc),
            )

    Thread(target=runner, daemon=True).start()
    return job_to_dict(job)


def start_video_ingest_job(url: str) -> dict[str, Any]:
    job = create_job(operation="video_ingest", source_type="video", message="Queued video transcript ingestion")

    def runner() -> None:
        try:
            result = ingest_video(
                url,
                progress_callback=lambda step, pct, message: update_job(
                    job.job_id,
                    status="processing",
                    current_step=step,
                    progress_percentage=pct,
                    message=message,
                ),
            )
            update_job(
                job.job_id,
                status="completed",
                current_step="Ready",
                progress_percentage=100,
                message="Video transcript ingestion completed",
                result=result.model_dump(),
            )
        except Exception as exc:
            update_job(
                job.job_id,
                status="failed",
                current_step="Failed",
                progress_percentage=100,
                message="Video transcript ingestion failed",
                error=str(exc),
                result=_error_result_payload(exc),
            )

    Thread(target=runner, daemon=True).start()
    return job_to_dict(job)


def start_website_recrawl_job(request: RecrawlRequest) -> dict[str, Any]:
    job = create_job(operation="website_recrawl", source_type="website", message="Queued website re-crawl")

    def runner() -> None:
        try:
            update_job(
                job.job_id,
                status="processing",
                current_step="Resolving target",
                progress_percentage=5,
                message="Resolving re-crawl target",
            )
            result = recrawl_website(request)
            update_job(
                job.job_id,
                status="completed",
                current_step="Ready",
                progress_percentage=100,
                message="Website re-crawl completed",
                result=result.model_dump(),
            )
        except Exception as exc:
            update_job(
                job.job_id,
                status="failed",
                current_step="Failed",
                progress_percentage=100,
                message="Website re-crawl failed",
                error=str(exc),
            )

    Thread(target=runner, daemon=True).start()
    return job_to_dict(job)


def start_github_ingest_job(url: str, branch: Optional[str] = None) -> dict[str, Any]:
    job = create_job(operation="github_ingest", source_type="github", message="Queued GitHub repository ingestion")

    def runner() -> None:
        try:
            result = ingest_github(
                url,
                branch=branch,
                progress_callback=lambda step, pct, message: update_job(
                    job.job_id,
                    status="processing",
                    current_step=step,
                    progress_percentage=pct,
                    message=message,
                ),
            )
            update_job(
                job.job_id,
                status="completed",
                current_step="Ready",
                progress_percentage=100,
                message="GitHub repository ingestion completed",
                result=result.model_dump(),
            )
        except Exception as exc:
            update_job(
                job.job_id,
                status="failed",
                current_step="Failed",
                progress_percentage=100,
                message="GitHub repository ingestion failed",
                error=str(exc),
            )

    Thread(target=runner, daemon=True).start()
    return job_to_dict(job)


def start_video_auto_transcribe_job(url: str) -> dict[str, Any]:
    job = create_job(operation="video_auto_transcribe", source_type="video", message="Queued automatic video transcription")

    def runner() -> None:
        try:
            result = ingest_video_auto_transcribe(
                url,
                progress_callback=lambda step, pct, message: update_job(
                    job.job_id,
                    status="processing",
                    current_step=step,
                    progress_percentage=pct,
                    message=message,
                ),
            )
            update_job(
                job.job_id,
                status="completed",
                current_step="Ready",
                progress_percentage=100,
                message="Video auto-transcription completed",
                result=result.model_dump(),
            )
        except Exception as exc:
            update_job(
                job.job_id,
                status="failed",
                current_step="Failed",
                progress_percentage=100,
                message="Video auto-transcription failed",
                error=str(exc),
                result=_error_result_payload(exc),
            )

    Thread(target=runner, daemon=True).start()
    return job_to_dict(job)
