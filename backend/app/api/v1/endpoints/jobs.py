from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.schemas import JobStatusResponse, RecrawlRequest, VideoAutoTranscribeRequest, VideoIngestRequest, WebsiteIngestRequest, GitHubIngestRequest
from app.services.ingestion_jobs import start_pdf_ingest_job, start_video_auto_transcribe_job, start_video_ingest_job, start_website_ingest_job, start_website_recrawl_job, start_github_ingest_job
from app.services.job_tracker import get_job, job_to_dict
from app.services.video_transcript import extract_video_id
from app.utils.exceptions import SourceExtractionError

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job_to_dict(job)


@router.post("/website-ingest", response_model=JobStatusResponse, status_code=202)
def create_website_ingest_job(payload: WebsiteIngestRequest):
    try:
        return start_website_ingest_job(str(payload.url), payload.max_pages, payload.max_depth)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not start website job: {exc}") from exc


@router.post("/pdf-ingest", response_model=JobStatusResponse, status_code=202)
async def create_pdf_ingest_job(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        return start_pdf_ingest_job(file.filename or "document.pdf", file.content_type, raw)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not start PDF job: {exc}") from exc


@router.post("/website-recrawl", response_model=JobStatusResponse, status_code=202)
def create_website_recrawl_job(request: RecrawlRequest):
    try:
        return start_website_recrawl_job(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not start re-crawl job: {exc}") from exc


@router.post("/video-ingest", response_model=JobStatusResponse, status_code=202)
def create_video_ingest_job(payload: VideoIngestRequest):
    try:
        extract_video_id(str(payload.url))
        return start_video_ingest_job(str(payload.url))
    except SourceExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not start video job: {exc}") from exc


@router.post("/video-auto-transcribe", response_model=JobStatusResponse, status_code=202)
def create_video_auto_transcribe_job(payload: VideoAutoTranscribeRequest):
    try:
        extract_video_id(str(payload.url))
        return start_video_auto_transcribe_job(str(payload.url))
    except SourceExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not start video auto-transcription job: {exc}") from exc


@router.post("/github-ingest", response_model=JobStatusResponse, status_code=202)
def create_github_ingest_job(payload: GitHubIngestRequest):
    try:
        # Validate URL early before creating job (fail fast with 400 instead of 202+later error)
        from app.services.github_repo import parse_github_url
        parse_github_url(str(payload.url))
        return start_github_ingest_job(str(payload.url), branch=payload.branch)
    except SourceExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not start GitHub job: {exc}") from exc
