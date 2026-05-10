from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.schemas import IngestResponse, JobStatusResponse, VideoAutoTranscribeRequest, VideoIngestRequest, WebsiteIngestRequest, WebsiteCrawlResponse
from app.services.ingestion_jobs import start_video_auto_transcribe_job, start_video_ingest_job
from app.services.ingestion_pipeline import ingest_pdf, ingest_website, crawl_website_ingest
from app.services.video_transcript import extract_video_id
from app.utils.exceptions import (
    SourceExtractionError,
    TranscriptUnavailableError,
    UnsupportedFileError,
    WebsiteIngestionError,
)

router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/website", response_model=WebsiteCrawlResponse)
def ingest_website_endpoint(payload: WebsiteIngestRequest):
    try:
        return crawl_website_ingest(str(payload.url), max_pages=payload.max_pages, max_depth=payload.max_depth)
    except WebsiteIngestionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc
    except SourceExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Website crawl failed: {exc}") from exc


@router.post("/pdf", response_model=IngestResponse)
async def ingest_pdf_endpoint(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        return ingest_pdf(file.filename or "document.pdf", file.content_type, raw)
    except UnsupportedFileError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except SourceExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF ingestion failed: {exc}") from exc


@router.post("/video", response_model=JobStatusResponse, status_code=202)
def ingest_video_endpoint(payload: VideoIngestRequest):
    try:
        extract_video_id(str(payload.url))
        return start_video_ingest_job(str(payload.url))
    except TranscriptUnavailableError as exc:
        raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
    except SourceExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Video ingestion failed: {exc}") from exc


@router.post("/video-auto-transcribe", response_model=JobStatusResponse, status_code=202)
def ingest_video_auto_transcribe_endpoint(payload: VideoAutoTranscribeRequest):
    try:
        extract_video_id(str(payload.url))
        return start_video_auto_transcribe_job(str(payload.url))
    except SourceExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Video auto-transcription failed: {exc}") from exc
