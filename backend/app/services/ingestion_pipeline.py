from typing import Callable, Optional

from app.core.config import get_settings
from app.models.schemas import IngestResponse, WebsiteCrawlResponse, CrawlSummaryResponse, TranscriptChunk
from app.services.chunker import TextChunk, chunk_pages, chunk_text
from app.services.embeddings import get_embedding_service
from app.services.pdf_extractor import extract_pdf_text, validate_pdf_upload
from app.services.supabase_repo import SupabaseRepository, make_chunk_id, sha256_bytes, sha256_text
from app.services.url_utils import normalize_url, safe_title_from_ref
from app.services.github_repo import (
    MAX_INDEXED_FILES,
    MAX_TOTAL_CHUNKS,
    MAX_TOTAL_TEXT_CHARS,
    fetch_repository,
    scan_repository_files,
    read_file_lines,
    chunk_file_by_lines,
    detect_language_by_ext,
)
from app.services.vector_store import get_vector_store
from app.services.web_scraper import extract_website_text
from app.services.website_crawler import crawl_website
from app.services.text_utils import estimate_tokens
from app.services.video_transcript import canonical_youtube_url, extract_video_id, extract_youtube_transcript, chunk_video_transcript
from app.services.video_transcriber import transcribe_youtube_video
from app.services.video_transcript import TranscriptLine
from app.services.source_overview import (
    create_overview_chunk,
    generate_github_overview,
    generate_pdf_overview,
    generate_video_overview,
    generate_website_overview,
)
from app.utils.exceptions import TranscriptUnavailableError, WebsiteCrawlTimeoutError, WebsiteNoUsableTextError


ProgressCallback = Callable[[str, int, str], None]


def _report(progress_callback: Optional[ProgressCallback], step: str, percentage: int, message: str) -> None:
    if progress_callback:
        progress_callback(step, percentage, message)


def _reindex_chunks(chunks):
    for index, chunk in enumerate(chunks):
        chunk.index = index
    return chunks


def _persist_video_chunks(
    *,
    repo: SupabaseRepository,
    kb_id: str,
    source_id: str,
    canonical_ref: str,
    title: str,
    video_id: str,
    transcript_duration: float,
    transcript_origin: str,
    transcription_model: str | None,
    video_chunks,
    progress_callback: Optional[ProgressCallback],
) -> int:
    if not video_chunks:
        raise ValueError("No chunks generated from transcript text.")

    transcript_text_chunks = [
        TextChunk(
            index=chunk.chunk_index,
            text=chunk.text,
            token_estimate=estimate_tokens(chunk.text),
            extra_metadata={
                "source_type": "video",
                "source_ref": canonical_ref,
                "source_url": canonical_ref,
                "source_title": title,
                "video_id": video_id,
                "timestamp_label": chunk.timestamp_label,
                "start_time": chunk.start_time,
                "end_time": chunk.end_time,
                "transcript_duration": transcript_duration,
                "transcript_origin": transcript_origin,
                "transcription_model": transcription_model,
                "has_timestamps": True,
            },
        )
        for chunk in video_chunks
    ]

    overview_text = generate_video_overview(
        title=title,
        video_id=video_id,
        duration_seconds=transcript_duration,
        transcript_origin=transcript_origin,
        segments=[
            TranscriptLine(
                text=chunk.text,
                start_time=float(chunk.start_time),
                duration=max(0.0, float(chunk.end_time) - float(chunk.start_time)),
                end_time=float(chunk.end_time),
            )
            for chunk in video_chunks
        ],
        total_chunks=len(transcript_text_chunks),
    )
    overview_chunk = create_overview_chunk(
        source_type="video",
        overview_type="video",
        text=overview_text,
        source_ref=canonical_ref,
        title=title,
        metadata={
            "video_id": video_id,
            "timestamp_label": "Full video",
            "start_time": 0,
            "end_time": transcript_duration,
            "transcript_duration": transcript_duration,
            "transcript_origin": transcript_origin,
            "transcription_model": transcription_model,
            "language": "transcript",
        },
    )

    text_chunks = _reindex_chunks([overview_chunk, *transcript_text_chunks])
    _report(progress_callback, "creating overview chunk", 52, "Creating source overview chunk")
    _report(progress_callback, "chunking transcript", 60, f"Chunking {len(video_chunks)} transcript chunks")
    chunk_ids = [make_chunk_id(kb_id, source_id, chunk.index, chunk.text) for chunk in text_chunks]
    _report(progress_callback, "generating embeddings", 78, "Generating embeddings")
    embeddings = get_embedding_service().embed_documents([chunk.text for chunk in text_chunks])

    get_vector_store().upsert_chunks(
        knowledgebase_id=kb_id,
        source_id=source_id,
        source_type="video",
        source_ref=canonical_ref,
        chunks=text_chunks,
        embeddings=embeddings,
        chunk_ids=chunk_ids,
    )
    repo.insert_chunks(
        knowledgebase_id=kb_id,
        source_id=source_id,
        source_type="video",
        source_ref=canonical_ref,
        chunks=text_chunks,
        chunk_ids=chunk_ids,
    )
    return len(text_chunks)


def ingest_website(url: str, progress_callback: Optional[ProgressCallback] = None) -> IngestResponse:
    settings = get_settings()
    repo = SupabaseRepository()
    canonical_ref = normalize_url(url)

    existing_kb = repo.get_knowledgebase_by_canonical_ref(canonical_ref)
    if existing_kb:
        existing_chunks = repo.get_chunks_count(existing_kb["id"])
        existing_source = repo.get_source_by_canonical_ref(canonical_ref)
        if existing_chunks > 0 and existing_source:
            return IngestResponse(
                knowledgebase_id=existing_kb["id"],
                source_id=existing_source["id"],
                source_type="website",
                canonical_ref=canonical_ref,
                title=existing_source.get("title"),
                status="ready",
                chunks_count=existing_chunks,
                reused_existing=True,
                page_count=1,
                crawled_pages=1,
                warnings=["Duplicate URL detected. Reused existing knowledgebase."],
            )

    extraction = extract_website_text(canonical_ref)
    title = extraction.title or safe_title_from_ref(canonical_ref)

    kb = existing_kb or repo.create_knowledgebase(name=title, source_type="website", canonical_ref=canonical_ref)
    kb_id = kb["id"]

    try:
        _report(progress_callback, "extracting", 20, "Extracting website content")
        source = repo.create_source(
            knowledgebase_id=kb_id,
            source_type="website",
            original_ref=url,
            canonical_ref=canonical_ref,
            title=title,
            content_hash=sha256_text(extraction.text),
            text_length=len(extraction.text),
            meta={"final_url": extraction.final_url},
        )
        source_id = source["id"]

        chunks = chunk_text(extraction.text, settings.chunk_size_chars, settings.chunk_overlap_chars)
        if not chunks:
            raise ValueError("No chunks generated from website text.")

        chunk_ids = [make_chunk_id(kb_id, source_id, chunk.index, chunk.text) for chunk in chunks]
        _report(progress_callback, "embedding", 70, "Generating embeddings")
        embeddings = get_embedding_service().embed_documents([chunk.text for chunk in chunks])

        get_vector_store().upsert_chunks(
            knowledgebase_id=kb_id,
            source_id=source_id,
            source_type="website",
            source_ref=canonical_ref,
            chunks=chunks,
            embeddings=embeddings,
            chunk_ids=chunk_ids,
        )
        repo.insert_chunks(
            knowledgebase_id=kb_id,
            source_id=source_id,
            source_type="website",
            source_ref=canonical_ref,
            chunks=chunks,
            chunk_ids=chunk_ids,
        )
        repo.update_knowledgebase_status(kb_id, "ready")
        _report(progress_callback, "ready", 100, "Website ingestion complete")
        return IngestResponse(
            knowledgebase_id=kb_id,
            source_id=source_id,
            source_type="website",
            canonical_ref=canonical_ref,
            title=title,
            status="ready",
            chunks_count=len(chunks),
            page_count=1,
            crawled_pages=1,
            warnings=extraction.warnings,
        )
    except Exception:
        repo.update_knowledgebase_status(kb_id, "failed")
        raise


def ingest_video(url: str, progress_callback: Optional[ProgressCallback] = None) -> IngestResponse:
    repo = SupabaseRepository()
    _report(progress_callback, "resolving video", 5, "Resolving video source")
    video_id = extract_video_id(url)
    canonical_ref = canonical_youtube_url(video_id)

    _report(progress_callback, "checking existing source", 10, "Checking existing video sources")
    existing_kb = repo.get_knowledgebase_by_canonical_ref(canonical_ref)
    existing_source = repo.get_source_by_canonical_ref(canonical_ref)
    if existing_kb and existing_source:
        existing_chunks = repo.get_chunks_count(existing_kb["id"])
        if existing_chunks > 0:
            meta = existing_source.get("meta") or {}
            return IngestResponse(
                knowledgebase_id=existing_kb["id"],
                source_id=existing_source["id"],
                source_type="video",
                canonical_ref=canonical_ref,
                title=existing_source.get("title"),
                status="ready",
                chunks_count=existing_chunks,
                reused_existing=True,
                transcript_duration=meta.get("transcript_duration"),
                duration_seconds=meta.get("transcript_duration"),
                video_id=meta.get("video_id") or video_id,
                transcript_origin=meta.get("transcript_origin") or "youtube_transcript",
                warnings=["Duplicate YouTube video detected. Reused existing knowledgebase."],
            )

    _report(progress_callback, "extracting transcript", 20, "Extracting YouTube transcript")
    try:
        transcript = extract_youtube_transcript(url)
    except TranscriptUnavailableError:
        raise

    title = transcript.title or "YouTube Video"

    kb = existing_kb or repo.create_knowledgebase(name=title, source_type="video", canonical_ref=canonical_ref)
    kb_id = kb["id"]

    try:
        source = repo.create_source(
            knowledgebase_id=kb_id,
            source_type="video",
            original_ref=url,
            canonical_ref=canonical_ref,
            title=title,
            content_hash=sha256_text("\n".join(chunk.text for chunk in transcript.chunks)),
            text_length=sum(len(chunk.text) for chunk in transcript.chunks),
            meta={
                "video_id": transcript.video_id,
                "transcript_duration": transcript.transcript_duration,
                "chunk_count": len(transcript.chunks),
                "segment_count": len(transcript.segments),
                "source_url": canonical_ref,
                "transcript_origin": "youtube_transcript",
                "has_timestamps": True,
            },
        )
        source_id = source["id"]

        chunks_count = _persist_video_chunks(
            repo=repo,
            kb_id=kb_id,
            source_id=source_id,
            canonical_ref=canonical_ref,
            title=title,
            video_id=transcript.video_id,
            transcript_duration=transcript.transcript_duration,
            transcript_origin="youtube_transcript",
            transcription_model=None,
            video_chunks=transcript.chunks,
            progress_callback=progress_callback,
        )
        _report(progress_callback, "storing metadata", 92, "Storing metadata")
        repo.update_knowledgebase_status(kb_id, "ready")
        _report(progress_callback, "completed", 100, "Video transcript ingestion complete")
        return IngestResponse(
            knowledgebase_id=kb_id,
            source_id=source_id,
            source_type="video",
            canonical_ref=canonical_ref,
            title=title,
            status="ready",
            chunks_count=chunks_count,
            transcript_duration=transcript.transcript_duration,
            duration_seconds=transcript.transcript_duration,
            video_id=transcript.video_id,
            transcript_origin="youtube_transcript",
            warnings=transcript.warnings,
        )
    except Exception:
        repo.update_knowledgebase_status(kb_id, "failed")
        raise


def ingest_video_auto_transcribe(url: str, progress_callback: Optional[ProgressCallback] = None) -> IngestResponse:
    repo = SupabaseRepository()
    _report(progress_callback, "resolving video", 5, "Resolving video source")
    video_id = extract_video_id(url)
    canonical_ref = canonical_youtube_url(video_id)

    _report(progress_callback, "checking existing source", 10, "Checking existing video sources")
    existing_kb = repo.get_knowledgebase_by_canonical_ref(canonical_ref)
    existing_source = repo.get_source_by_canonical_ref(canonical_ref)
    if existing_kb and existing_source:
        existing_chunks = repo.get_chunks_count(existing_kb["id"])
        if existing_chunks > 0:
            meta = existing_source.get("meta") or {}
            return IngestResponse(
                knowledgebase_id=existing_kb["id"],
                source_id=existing_source["id"],
                source_type="video",
                canonical_ref=canonical_ref,
                title=existing_source.get("title"),
                status="ready",
                chunks_count=existing_chunks,
                reused_existing=True,
                transcript_duration=meta.get("transcript_duration"),
                duration_seconds=meta.get("transcript_duration"),
                video_id=meta.get("video_id") or video_id,
                transcript_origin=meta.get("transcript_origin") or "auto_transcribed",
                warnings=["Duplicate YouTube video detected. Reused existing knowledgebase."],
            )

    transcript = transcribe_youtube_video(url, progress_callback=progress_callback)

    transcript_lines = [
        TranscriptLine(
            text=segment.text,
            start_time=segment.start_time,
            duration=segment.duration,
            end_time=segment.end_time,
        )
        for segment in transcript.segments
    ]

    _report(progress_callback, "chunking transcript", 60, "Chunking transcript")
    text_chunks = chunk_video_transcript(
        transcript_lines,
        source_url=transcript.canonical_url,
        video_id=transcript.video_id,
        source_title=transcript.title,
        transcript_duration=transcript.duration_seconds,
    )
    video_chunks = [
        TranscriptChunk(
            text=chunk.text,
            start_time=float(chunk.extra_metadata.get("start_time", 0.0)),
            end_time=float(chunk.extra_metadata.get("end_time", 0.0)),
            timestamp_label=str(chunk.extra_metadata.get("timestamp_label", "")),
            source_url=str(chunk.extra_metadata.get("source_url", transcript.canonical_url)),
            video_id=str(chunk.extra_metadata.get("video_id", transcript.video_id)),
            chunk_index=chunk.index,
        )
        for chunk in text_chunks
    ]

    kb = existing_kb or repo.create_knowledgebase(name=transcript.title, source_type="video", canonical_ref=canonical_ref)
    kb_id = kb["id"]

    try:
        source = repo.create_source(
            knowledgebase_id=kb_id,
            source_type="video",
            original_ref=url,
            canonical_ref=canonical_ref,
            title=transcript.title,
            content_hash=sha256_text("\n".join(chunk.text for chunk in video_chunks)),
            text_length=sum(len(chunk.text) for chunk in video_chunks),
            meta={
                "video_id": transcript.video_id,
                "transcript_duration": transcript.duration_seconds,
                "duration_seconds": transcript.duration_seconds,
                "chunk_count": len(video_chunks),
                "segment_count": len(transcript.segments),
                "source_url": canonical_ref,
                "transcript_origin": "auto_transcribed",
                "transcription_model": transcript.transcription_model,
                "has_timestamps": True,
            },
        )
        source_id = source["id"]

        chunks_count = _persist_video_chunks(
            repo=repo,
            kb_id=kb_id,
            source_id=source_id,
            canonical_ref=canonical_ref,
            title=transcript.title,
            video_id=transcript.video_id,
            transcript_duration=transcript.duration_seconds,
            transcript_origin="auto_transcribed",
            transcription_model=transcript.transcription_model,
            video_chunks=video_chunks,
            progress_callback=progress_callback,
        )
        _report(progress_callback, "storing metadata", 92, "Storing metadata")
        repo.update_knowledgebase_status(kb_id, "ready")
        _report(progress_callback, "completed", 100, "Video auto-transcription completed")

        return IngestResponse(
            knowledgebase_id=kb_id,
            source_id=source_id,
            source_type="video",
            canonical_ref=canonical_ref,
            title=transcript.title,
            status="ready",
            chunks_count=chunks_count,
            transcript_duration=transcript.duration_seconds,
            duration_seconds=transcript.duration_seconds,
            video_id=transcript.video_id,
            transcript_origin="auto_transcribed",
            warnings=transcript.warnings,
        )
    except Exception:
        repo.update_knowledgebase_status(kb_id, "failed")
        raise


def crawl_website_ingest(
    url: str,
    max_pages: int = 10,
    max_depth: int = 1,
    progress_callback: Optional[ProgressCallback] = None,
) -> WebsiteCrawlResponse:
    """Crawl a website and ingest all pages under a single knowledgebase."""
    settings = get_settings()
    repo = SupabaseRepository()
    
    # Get crawled pages
    _report(progress_callback, "crawling", 10, "Crawling website")
    crawled_pages, crawl_summary = crawl_website(url, max_pages=max_pages, max_depth=max_depth)
    
    if not crawled_pages:
        failure_messages = " ".join(crawl_summary.failed_pages.values()).lower()
        if "timeout" in failure_messages or "timed out" in failure_messages:
            raise WebsiteCrawlTimeoutError()
        raise WebsiteNoUsableTextError()

    _report(progress_callback, "extracting", 35, "Extracting rendered content")
    
    # Create a knowledgebase for the crawl
    canonical_ref = crawl_summary.normalized_url
    existing_kb = repo.get_knowledgebase_by_canonical_ref(canonical_ref)
    if existing_kb:
        existing_chunks = repo.get_chunks_count(existing_kb["id"])
        kb_sources = repo.list_sources_for_knowledgebase(existing_kb["id"])
        if existing_chunks > 0 and len(kb_sources) > 1:
            vector_store = get_vector_store()
            for source in kb_sources:
                source_id = source["id"]
                vector_store.delete_by_source(source_id)
                repo.delete_source_chunks(source_id)
                repo.delete_source(source_id)
            repo.delete_knowledgebase_chunks(existing_kb["id"])
            repo.delete_knowledgebase(existing_kb["id"])
            existing_kb = None
            existing_chunks = 0
        if existing_chunks > 0:
            # Reuse existing crawl
            sources_created = []
            for source in kb_sources:
                sources_created.append(IngestResponse(
                    knowledgebase_id=existing_kb["id"],
                    source_id=source["id"],
                    source_type="website",
                    canonical_ref=source["canonical_ref"],
                    title=source.get("title"),
                    status="ready",
                    chunks_count=repo.get_chunks_count_for_source(existing_kb["id"], source["id"]),
                    reused_existing=True,
                    page_count=source.get("meta", {}).get("page_count"),
                    crawled_pages=source.get("meta", {}).get("crawled_pages") or source.get("meta", {}).get("page_count"),
                ))
            crawl_summary.total_chunks_created = existing_chunks
            crawl_summary.warnings.append("Website crawl already exists. Reused existing knowledgebase.")
            _report(progress_callback, "ready", 100, "Website crawl complete")
            return WebsiteCrawlResponse(
                knowledgebase_id=existing_kb["id"],
                status="ready",
                crawl_summary=CrawlSummaryResponse(
                    starting_url=crawl_summary.starting_url,
                    normalized_url=crawl_summary.normalized_url,
                    pages_attempted=crawl_summary.pages_attempted,
                    pages_successfully_ingested=crawl_summary.pages_successfully_ingested,
                    pages_skipped=crawl_summary.pages_skipped,
                    failed_pages=crawl_summary.failed_pages,
                    total_chunks_created=existing_chunks,
                    warnings=crawl_summary.warnings,
                ),
                sources_created=sources_created,
            )
    
    # Create new knowledgebase
    title = crawled_pages[0].title or safe_title_from_ref(canonical_ref)
    kb = repo.create_knowledgebase(
        name=title,
        source_type="website",
        canonical_ref=canonical_ref,
    )
    kb_id = kb["id"]
    
    page_count = len(crawled_pages)
    page_chunks = chunk_pages(
        [(page_number, page.text) for page_number, page in enumerate(crawled_pages, start=1)],
        settings.chunk_size_chars,
        settings.chunk_overlap_chars,
    )
    page_metadata = {
        page_number: {
            "page_url": page.final_url or page.url,
            "page_title": page.title,
            "source_ref": page.final_url or page.url,
            "source_title": page.title,
        }
        for page_number, page in enumerate(crawled_pages, start=1)
    }
    for chunk in page_chunks:
        if chunk.page_number in page_metadata:
            chunk.extra_metadata.update(page_metadata[chunk.page_number])
    overview_text = generate_website_overview(
        title=title,
        canonical_ref=canonical_ref,
        starting_url=crawl_summary.starting_url,
        pages_attempted=crawl_summary.pages_attempted,
        pages_crawled=crawl_summary.pages_successfully_ingested,
        crawled_pages=crawled_pages,
        total_chunks=len(page_chunks),
    )
    overview_chunk = create_overview_chunk(
        source_type="website",
        overview_type="website",
        text=overview_text,
        source_ref=canonical_ref,
        title=title,
        metadata={
            "source_url": canonical_ref,
            "starting_url": crawl_summary.starting_url,
            "normalized_url": crawl_summary.normalized_url,
        },
    )
    page_chunks = _reindex_chunks([overview_chunk, *page_chunks])
    total_chunks = len(page_chunks)
    
    try:
        source = repo.create_source(
            knowledgebase_id=kb_id,
            source_type="website",
            original_ref=url,
            canonical_ref=canonical_ref,
            title=title,
            content_hash=sha256_text("\n\n".join(page.text for page in crawled_pages)),
            text_length=sum(len(page.text) for page in crawled_pages),
            meta={
                "starting_url": crawl_summary.starting_url,
                "normalized_url": crawl_summary.normalized_url,
                "extraction_method": crawl_summary.extraction_method,
                "page_count": page_count,
                "crawled_pages": page_count,
                "pages_attempted": crawl_summary.pages_attempted,
                "pages_skipped": crawl_summary.pages_skipped,
            },
        )
        source_id = source["id"]

        if not page_chunks:
            raise ValueError("No chunks generated from website text.")

        _report(progress_callback, "creating overview chunk", 52, "Creating source overview chunk")
        _report(progress_callback, "chunking", 55, f"Chunking {page_count} pages")
        chunk_ids = [make_chunk_id(kb_id, source_id, chunk.index, chunk.text) for chunk in page_chunks]
        _report(progress_callback, "embedding", 75, "Generating embeddings")
        embeddings = get_embedding_service().embed_documents([chunk.text for chunk in page_chunks])

        get_vector_store().upsert_chunks(
            knowledgebase_id=kb_id,
            source_id=source_id,
            source_type="website",
            source_ref=canonical_ref,
            chunks=page_chunks,
            embeddings=embeddings,
            chunk_ids=chunk_ids,
        )
        repo.insert_chunks(
            knowledgebase_id=kb_id,
            source_id=source_id,
            source_type="website",
            source_ref=canonical_ref,
            chunks=page_chunks,
            chunk_ids=chunk_ids,
        )

        _report(progress_callback, "storing", 92, "Storing metadata")
        repo.update_knowledgebase_status(kb_id, "ready")
        crawl_summary.total_chunks_created = total_chunks
        _report(progress_callback, "ready", 100, "Website crawl complete")
        
        return WebsiteCrawlResponse(
            knowledgebase_id=kb_id,
            status="ready",
            crawl_summary=CrawlSummaryResponse(
                starting_url=crawl_summary.starting_url,
                normalized_url=crawl_summary.normalized_url,
                pages_attempted=crawl_summary.pages_attempted,
                pages_successfully_ingested=crawl_summary.pages_successfully_ingested,
                pages_skipped=crawl_summary.pages_skipped,
                failed_pages=crawl_summary.failed_pages,
                total_chunks_created=total_chunks,
                warnings=crawl_summary.warnings,
            ),
            sources_created=[IngestResponse(
                knowledgebase_id=kb_id,
                source_id=source_id,
                source_type="website",
                canonical_ref=canonical_ref,
                title=title,
                status="ready",
                chunks_count=total_chunks,
                page_count=page_count,
                crawled_pages=page_count,
            )],
        )
    except Exception as e:
        repo.update_knowledgebase_status(kb_id, "failed")
        raise


def ingest_github(url: str, branch: Optional[str] = None, progress_callback: Optional[ProgressCallback] = None) -> IngestResponse:
    settings = get_settings()
    repo = SupabaseRepository()

    dest = None
    try:
        _report(progress_callback, "resolving", 5, "Resolving GitHub repository")
        repo_path, ref = fetch_repository(url, branch=branch)
        canonical_ref = ref.canonical

        existing_kb = repo.get_knowledgebase_by_canonical_ref(canonical_ref)
        existing_source = repo.get_source_by_canonical_ref(canonical_ref)
        if existing_kb and existing_source:
            existing_chunks = repo.get_chunks_count(existing_kb["id"])
            if existing_chunks > 0:
                meta = existing_source.get("meta") or {}
                return IngestResponse(
                    knowledgebase_id=existing_kb["id"],
                    source_id=existing_source["id"],
                    source_type="github",
                    canonical_ref=canonical_ref,
                    title=existing_source.get("title"),
                    status="ready",
                    chunks_count=existing_chunks,
                    reused_existing=True,
                    repo_owner=meta.get("repo_owner"),
                    repo_name=meta.get("repo_name"),
                    branch=meta.get("branch"),
                    detected_languages=meta.get("detected_languages"),
                    files_indexed=meta.get("files_indexed"),
                    files_skipped=meta.get("files_skipped"),
                    warnings=["Duplicate repository detected. Reused existing knowledgebase."],
                )

        title = f"GitHub: {ref.owner}/{ref.repo}"
        kb = existing_kb or repo.create_knowledgebase(name=title, source_type="github", canonical_ref=canonical_ref)
        kb_id = kb["id"]

        _report(progress_callback, "scanning", 20, "Scanning repository files")
        files_indexed = 0
        files_skipped = 0
        total_text_chars = 0
        repo_warnings: list[str] = []
        detected_langs: set[str] = set()

        text_chunks: list[TextChunk] = []
        global_index = 0
        for rel_path, ext in scan_repository_files(repo_path, max_files=MAX_INDEXED_FILES):
            if len(text_chunks) >= MAX_TOTAL_CHUNKS:
                repo_warnings.append(f"Repository chunk limit reached ({MAX_TOTAL_CHUNKS}). Some files were skipped.")
                break

            lines = read_file_lines(repo_path, rel_path)
            if not lines:
                files_skipped += 1
                continue

            chunks = chunk_file_by_lines(lines)
            if not chunks:
                files_skipped += 1
                continue

            lang = detect_language_by_ext(ext)
            detected_langs.add(lang)
            added_for_file = 0
            for c_idx, (start_line, end_line, text) in enumerate(chunks):
                if len(text_chunks) >= MAX_TOTAL_CHUNKS:
                    repo_warnings.append(f"Repository chunk limit reached ({MAX_TOTAL_CHUNKS}). Some file chunks were skipped.")
                    break
                if total_text_chars + len(text) > MAX_TOTAL_TEXT_CHARS:
                    repo_warnings.append(f"Repository indexed text limit reached ({MAX_TOTAL_TEXT_CHARS} characters). Some content was skipped.")
                    break

                tc = TextChunk(
                    index=global_index,
                    text=text,
                    token_estimate=estimate_tokens(text),
                    extra_metadata={
                        "source_type": "github",
                        "repo_owner": ref.owner,
                        "repo_name": ref.repo,
                        "branch": ref.branch,
                        "file_path": rel_path,
                        "language": lang,
                        "start_line": start_line,
                        "end_line": end_line,
                    },
                )
                text_chunks.append(tc)
                total_text_chars += len(text)
                global_index += 1
                added_for_file += 1

            if added_for_file:
                files_indexed += 1
            else:
                files_skipped += 1

        if files_indexed >= MAX_INDEXED_FILES:
            repo_warnings.append(f"Repository file limit reached ({MAX_INDEXED_FILES}). Large repositories are partially indexed for stability.")

        if not text_chunks:
            raise ValueError("No text chunks generated from repository files.")

        # Generate repository overview chunk (deterministic, metadata-derived)
        _report(progress_callback, "generating", 50, "Generating repository overview")
        overview_text = generate_github_overview(
            root=repo_path,
            ref=ref,
            detected_langs=detected_langs,
            files_indexed=files_indexed,
            files_skipped=files_skipped,
            total_chunks_created=len(text_chunks),
        )
        
        # Create overview chunk (special metadata for citation handling)
        overview_chunk = create_overview_chunk(
            source_type="github",
            overview_type="github",
            text=overview_text,
            source_ref=canonical_ref,
            title=title,
            metadata={
                "repo_owner": ref.owner,
                "repo_name": ref.repo,
                "branch": ref.branch,
                "file_path": "__SAGE_REPO_OVERVIEW__",
                "language": "text",
                "start_line": 1,
                "end_line": 1,
            },
        )
        
        # Insert overview chunk at the beginning for high relevance
        text_chunks.insert(0, overview_chunk)
        # Re-index all chunks to maintain consistency
        for idx, chunk in enumerate(text_chunks):
            chunk.index = idx

        _report(progress_callback, "chunking", 55, f"Prepared {len(text_chunks)} chunks (including overview) from {files_indexed} files")
        _report(progress_callback, "embedding", 70, "Generating embeddings for repository chunks")
        embeddings = get_embedding_service().embed_documents([chunk.text for chunk in text_chunks])

        source = repo.create_source(
            knowledgebase_id=kb_id,
            source_type="github",
            original_ref=url,
            canonical_ref=canonical_ref,
            title=title,
            content_hash=sha256_text("\n\n".join(c.text for c in text_chunks)),
            text_length=sum(len(c.text) for c in text_chunks),
            meta={
                "repo_owner": ref.owner,
                "repo_name": ref.repo,
                "branch": ref.branch,
                "detected_languages": list(detected_langs),
                "files_indexed": files_indexed,
                "files_skipped": files_skipped,
                "indexing_limits": {
                    "max_files": MAX_INDEXED_FILES,
                    "max_chunks": MAX_TOTAL_CHUNKS,
                    "max_text_chars": MAX_TOTAL_TEXT_CHARS,
                },
                "warnings": repo_warnings,
            },
        )
        source_id = source["id"]
        # Now compute stable chunk IDs using the real source id
        chunk_ids = [make_chunk_id(kb_id, source_id, chunk.index, chunk.text) for chunk in text_chunks]

        get_vector_store().upsert_chunks(
            knowledgebase_id=kb_id,
            source_id=source_id,
            source_type="github",
            source_ref=canonical_ref,
            chunks=text_chunks,
            embeddings=embeddings,
            chunk_ids=chunk_ids,
        )
        repo.insert_chunks(
            knowledgebase_id=kb_id,
            source_id=source_id,
            source_type="github",
            source_ref=canonical_ref,
            chunks=text_chunks,
            chunk_ids=chunk_ids,
        )

        repo.update_knowledgebase_status(kb_id, "ready")
        _report(progress_callback, "ready", 100, "Repository ingestion complete")
        return IngestResponse(
            knowledgebase_id=kb_id,
            source_id=source_id,
            source_type="github",
            canonical_ref=canonical_ref,
            title=title,
            status="ready",
            chunks_count=len(text_chunks),
            repo_owner=ref.owner,
            repo_name=ref.repo,
            branch=ref.branch,
            detected_languages=list(detected_langs),
            files_indexed=files_indexed,
            files_skipped=files_skipped,
            warnings=repo_warnings,
        )
    except Exception:
        if "kb_id" in locals():
            repo.update_knowledgebase_status(kb_id, "failed")
        raise
    finally:
        # cleanup fetched repository
        try:
            if "repo_path" in locals() and repo_path:
                shutil.rmtree(os.path.dirname(repo_path), ignore_errors=True)
        except Exception:
            pass


def ingest_pdf(
    filename: str,
    content_type: str | None,
    raw: bytes,
    progress_callback: Optional[ProgressCallback] = None,
) -> IngestResponse:
    settings = get_settings()
    repo = SupabaseRepository()
    validate_pdf_upload(filename, content_type, raw)
    _report(progress_callback, "extracting", 15, "Extracting PDF text")

    file_hash = sha256_bytes(raw)
    canonical_ref = f"pdf:{file_hash}"
    existing_kb = repo.get_knowledgebase_by_canonical_ref(canonical_ref)
    if existing_kb:
        existing_chunks = repo.get_chunks_count(existing_kb["id"])
        existing_source = repo.get_source_by_canonical_ref(canonical_ref)
        if existing_chunks > 0 and existing_source:
            return IngestResponse(
                knowledgebase_id=existing_kb["id"],
                source_id=existing_source["id"],
                source_type="pdf",
                canonical_ref=canonical_ref,
                title=existing_source.get("title"),
                status="ready",
                chunks_count=existing_chunks,
                reused_existing=True,
                page_count=existing_source.get("meta", {}).get("page_count"),
                crawled_pages=existing_source.get("meta", {}).get("page_count"),
                warnings=["Duplicate PDF detected by file hash. Reused existing knowledgebase."],
            )

    extraction = extract_pdf_text(filename, raw)
    title = extraction.title
    kb = existing_kb or repo.create_knowledgebase(name=title, source_type="pdf", canonical_ref=canonical_ref)
    kb_id = kb["id"]

    try:
        source = repo.create_source(
            knowledgebase_id=kb_id,
            source_type="pdf",
            original_ref=filename,
            canonical_ref=canonical_ref,
            title=title,
            content_hash=file_hash,
            text_length=len(extraction.text),
            meta={"page_count": extraction.page_count, "file_hash": file_hash},
        )
        source_id = source["id"]

        _report(progress_callback, "chunking", 45, "Creating chunks")
        chunks = chunk_pages(extraction.pages, settings.chunk_size_chars, settings.chunk_overlap_chars)
        if not chunks:
            raise ValueError("No chunks generated from PDF text.")

        overview_text = generate_pdf_overview(
            title=title,
            filename=filename,
            page_count=extraction.page_count,
            text_length=len(extraction.text),
            pages=extraction.pages,
            total_chunks=len(chunks),
        )
        overview_chunk = create_overview_chunk(
            source_type="pdf",
            overview_type="pdf",
            text=overview_text,
            source_ref=canonical_ref,
            title=title,
            metadata={
                "page_number": 1,
                "source_url": canonical_ref,
                "page_count": extraction.page_count,
                "text_length": len(extraction.text),
            },
        )
        chunks = _reindex_chunks([overview_chunk, *chunks])

        chunk_ids = [make_chunk_id(kb_id, source_id, chunk.index, chunk.text) for chunk in chunks]
        _report(progress_callback, "embedding", 70, "Generating embeddings")
        embeddings = get_embedding_service().embed_documents([chunk.text for chunk in chunks])

        get_vector_store().upsert_chunks(
            knowledgebase_id=kb_id,
            source_id=source_id,
            source_type="pdf",
            source_ref=filename,
            chunks=chunks,
            embeddings=embeddings,
            chunk_ids=chunk_ids,
        )
        repo.insert_chunks(
            knowledgebase_id=kb_id,
            source_id=source_id,
            source_type="pdf",
            source_ref=filename,
            chunks=chunks,
            chunk_ids=chunk_ids,
        )
        repo.update_knowledgebase_status(kb_id, "ready")
        _report(progress_callback, "ready", 100, "PDF ingestion complete")
        return IngestResponse(
            knowledgebase_id=kb_id,
            source_id=source_id,
            source_type="pdf",
            canonical_ref=canonical_ref,
            title=title,
            status="ready",
            chunks_count=len(chunks),
            page_count=extraction.page_count,
            crawled_pages=extraction.page_count,
            warnings=extraction.warnings,
        )
    except Exception:
        repo.update_knowledgebase_status(kb_id, "failed")
        raise
