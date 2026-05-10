from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

from app.services.chunker import TextChunk
from app.services.github_repo import RepoRef, generate_repository_overview
from app.services.supabase_repo import make_chunk_id
from app.services.text_utils import clean_whitespace, estimate_tokens


_STOPWORDS = {
    "the", "and", "that", "with", "this", "from", "have", "your", "about", "what", "when", "where",
    "which", "would", "could", "there", "their", "into", "while", "they", "them", "than", "then",
    "also", "been", "were", "will", "just", "like", "video", "website", "pdf", "repo", "repository",
    "source", "overview", "chunk", "chunks", "pages", "page", "video", "transcript", "document",
}


def _as_text_lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        return lines
    return [str(value)]


def _top_terms(texts: Iterable[str], limit: int = 6) -> str:
    tokens: list[str] = []
    for text in texts:
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text.lower()):
            if token not in _STOPWORDS:
                tokens.append(token)
    if not tokens:
        return ""
    counter = Counter(tokens)
    return ", ".join(word for word, _ in counter.most_common(limit))


def _first_last_excerpt(texts: list[str], limit: int = 2) -> tuple[list[str], list[str]]:
    if not texts:
        return [], []
    return texts[:limit], texts[-limit:]


def _make_chunk(text: str, *, source_type: str, overview_type: str, source_ref: str, title: str, metadata: dict[str, Any]) -> TextChunk:
    chunk = TextChunk(
        index=0,
        text=text,
        token_estimate=estimate_tokens(text),
        extra_metadata={
            "source_type": source_type,
            "source_ref": source_ref,
            "source_title": title,
            "chunk_kind": "source_overview",
            "overview_type": overview_type,
            "is_sage_overview": True,
            **metadata,
        },
    )
    return chunk


def create_overview_chunk(
    *,
    source_type: str,
    overview_type: str,
    text: str,
    source_ref: str,
    title: str,
    metadata: dict[str, Any],
) -> TextChunk:
    marker_map = {
        "website": "__SAGE_WEBSITE_OVERVIEW__",
        "pdf": "__SAGE_PDF_OVERVIEW__",
        "video": "__SAGE_VIDEO_OVERVIEW__",
        "github": "__SAGE_REPO_OVERVIEW__",
    }
    marker = marker_map.get(overview_type, "__SAGE_SOURCE_OVERVIEW__")
    body = clean_whitespace(text)
    overview_text = f"{marker}\n{body}" if body else marker
    return _make_chunk(
        overview_text,
        source_type=source_type,
        overview_type=overview_type,
        source_ref=source_ref,
        title=title,
        metadata=metadata,
    )


def generate_website_overview(
    *,
    title: str,
    canonical_ref: str,
    starting_url: str,
    pages_attempted: int,
    pages_crawled: int,
    crawled_pages: list[Any],
    total_chunks: int,
) -> str:
    page_rows = []
    page_texts = []
    page_titles = []
    for page in crawled_pages:
        url = getattr(page, "final_url", None) or getattr(page, "normalized_url", None) or getattr(page, "url", None)
        page_title = getattr(page, "title", None) or "Untitled"
        text = clean_whitespace(getattr(page, "text", ""))
        page_texts.append(text)
        page_titles.append(page_title)
        if url:
            page_rows.append(f"- {page_title} — {url}")

    first_rows, last_rows = _first_last_excerpt(page_texts, limit=2)
    themes = _top_terms(page_texts)

    lines = [
        "WEBSITE OVERVIEW",
        f"Title: {title}",
        f"Canonical URL: {canonical_ref}",
        f"Starting URL: {starting_url}",
        f"Pages crawled: {pages_crawled}",
        f"Pages attempted: {pages_attempted}",
        f"Total chunks: {total_chunks}",
    ]
    if page_rows:
        lines.append("Crawled Pages:")
        lines.extend(page_rows[:5])
    if first_rows:
        lines.append("BEGINNING EXCERPT:")
        lines.extend(first_rows)
    if last_rows:
        lines.append("ENDING EXCERPT:")
        lines.extend(last_rows)
    if themes:
        lines.append("TRANSCRIPT THEMES:")
        lines.append(themes)
    return "\n".join(lines)


def generate_pdf_overview(
    *,
    title: str,
    filename: str,
    page_count: int,
    text_length: int,
    pages: list[tuple[int, str]],
    total_chunks: int,
) -> str:
    page_texts = [clean_whitespace(text) for _, text in pages]
    headings: list[str] = []
    for _, page_text in pages[:3]:
        for line in _as_text_lines(page_text):
            if len(line) <= 90 and (line.isupper() or line.startswith("#") or re.match(r"^[A-Z][A-Za-z0-9 ,:-]{3,}$", line)):
                headings.append(line.lstrip("# "))
            if len(headings) >= 6:
                break
        if len(headings) >= 6:
            break

    first_rows, last_rows = _first_last_excerpt(page_texts, limit=1)
    themes = _top_terms(page_texts)

    lines = [
        "PDF OVERVIEW",
        f"Title: {title}",
        f"Filename: {filename}",
        f"Page count: {page_count}",
        f"Text length: {text_length}",
        f"Total chunks: {total_chunks}",
    ]
    if headings:
        lines.append("DETECTED HEADINGS:")
        lines.extend(headings)
    if first_rows:
        lines.append("BEGINNING EXCERPT:")
        lines.extend(first_rows)
    if last_rows:
        lines.append("ENDING EXCERPT:")
        lines.extend(last_rows)
    if themes:
        lines.append("MAIN TOPICS:")
        lines.append(themes)
    return "\n".join(lines)


def generate_video_overview(
    *,
    title: str,
    video_id: str,
    duration_seconds: float,
    transcript_origin: str,
    segments: list[Any],
    total_chunks: int,
) -> str:
    segment_rows = []
    segment_texts = []
    for segment in segments:
        text = clean_whitespace(getattr(segment, "text", ""))
        if not text:
            continue
        segment_texts.append(text)
        start = getattr(segment, "start_time", 0.0)
        end = getattr(segment, "end_time", start)
        label = f"[{int(start // 60):02d}:{int(start % 60):02d} - {int(end // 60):02d}:{int(end % 60):02d}]"
        segment_rows.append(f"{label} {text[:220]}")

    first_rows, last_rows = _first_last_excerpt(segment_rows, limit=3)
    themes = _top_terms(segment_texts)

    lines = [
        "VIDEO OVERVIEW",
        f"Title: {title}",
        f"Video ID: {video_id}",
        f"Duration: {int(duration_seconds)} seconds",
        f"Transcript origin: {transcript_origin}",
        f"Transcript segments: {len(segment_rows)}",
        f"Total chunks: {total_chunks}",
    ]
    if first_rows:
        lines.append("BEGINNING EXCERPT:")
        lines.extend(first_rows)
    if last_rows:
        lines.append("ENDING EXCERPT:")
        lines.extend(last_rows)
    if themes:
        lines.append("TRANSCRIPT THEMES:")
        lines.append(themes)
    return "\n".join(lines)


def generate_github_overview(
    *,
    root: str,
    ref: RepoRef,
    detected_langs: set[str],
    files_indexed: int,
    files_skipped: int,
    total_chunks_created: int,
) -> str:
    return generate_repository_overview(
        root,
        ref,
        detected_langs,
        files_indexed,
        files_skipped,
        total_chunks_created,
    )