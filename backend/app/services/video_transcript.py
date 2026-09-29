from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import parse_qs, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi

from app.core.config import get_settings
from app.models.schemas import TranscriptChunk, TranscriptSegment, YouTubeTranscriptResponse
from app.services.chunker import TextChunk
from app.services.text_utils import clean_whitespace, estimate_tokens
from app.utils.exceptions import SourceExtractionError, TranscriptUnavailableError


_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass
class TranscriptLine:
    text: str
    start_time: float
    duration: float
    end_time: float


def extract_video_id(url: str) -> str:
    parsed = urlparse(str(url).strip())
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")

    if "youtube.com" in host or "youtube-nocookie.com" in host:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith("/shorts/"):
            video_id = path.split("/")[1] if "/" in path else ""
        elif parsed.path.startswith("/embed/"):
            video_id = path.split("/")[1] if "/" in path else ""
        else:
            video_id = parse_qs(parsed.query).get("v", [""])[0]
    elif host.endswith("youtu.be"):
        video_id = path.split("/")[0]
    else:
        raise SourceExtractionError("Invalid YouTube URL.")

    video_id = (video_id or "").strip()
    if not _VIDEO_ID_RE.match(video_id):
        raise SourceExtractionError("Invalid YouTube URL.")
    return video_id


def canonical_youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _format_timestamp(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _format_timestamp_label(start_time: float, end_time: float) -> str:
    return f"{_format_timestamp(start_time)} - {_format_timestamp(end_time)}"


def _get_video_title(canonical_url: str, fallback: str = "YouTube Video") -> str:
    settings = get_settings()
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        response = requests.get(canonical_url, headers=headers, timeout=settings.request_timeout_seconds)
        response.raise_for_status()
    except requests.RequestException:
        return fallback

    soup = BeautifulSoup(response.text, "html.parser")
    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get("content"):
        return clean_whitespace(str(og_title.get("content"))) or fallback

    if soup.title and soup.title.get_text(strip=True):
        title_text = clean_whitespace(soup.title.get_text(" "))
        title_text = title_text.replace(" - YouTube", "").strip()
        return title_text or fallback

    return fallback


def _fetch_transcript_lines(video_id: str) -> list[TranscriptLine]:
    api = YouTubeTranscriptApi()

    try:
        transcript_list = api.list(video_id)
    except Exception as exc:
        raise TranscriptUnavailableError("Transcript not available from YouTube.") from exc

    transcript = None
    english_codes = ["en", "en-US", "en-GB"]

    # 1) Manual English transcript.
    try:
        transcript = transcript_list.find_manually_created_transcript(english_codes)
    except Exception:
        transcript = None

    # 2) Auto-generated English transcript.
    if transcript is None:
        try:
            transcript = transcript_list.find_generated_transcript(english_codes)
        except Exception:
            transcript = None

    # 3) Any available transcript.
    if transcript is None:
        try:
            transcript = next(iter(transcript_list), None)
        except Exception:
            transcript = None

    # 4) Try translating to English if supported.
    if transcript is None:
        try:
            for candidate in transcript_list:
                is_translatable = bool(getattr(candidate, "is_translatable", False))
                if is_translatable:
                    transcript = candidate.translate("en")
                    break
        except Exception:
            transcript = None
    elif getattr(transcript, "language_code", "") not in english_codes and bool(getattr(transcript, "is_translatable", False)):
        try:
            transcript = transcript.translate("en")
        except Exception:
            pass

    if transcript is None:
        raise TranscriptUnavailableError("Transcript not available from YouTube.")

    try:
        raw_segments = transcript.fetch()
    except Exception as exc:
        raise TranscriptUnavailableError("Transcript not available from YouTube.") from exc

    lines: list[TranscriptLine] = []
    for segment in raw_segments:
        if isinstance(segment, dict):
            text = clean_whitespace(str(segment.get("text", "")))
            start_time = float(segment.get("start", 0.0))
            duration = float(segment.get("duration", 0.0))
        else:
            text = clean_whitespace(str(getattr(segment, "text", "")))
            start_time = float(getattr(segment, "start", 0.0))
            duration = float(getattr(segment, "duration", 0.0))

        if not text:
            continue
        lines.append(
            TranscriptLine(
                text=text,
                start_time=start_time,
                duration=duration,
                end_time=start_time + duration,
            )
        )

    if not lines:
        raise TranscriptUnavailableError("Transcript not available from YouTube.")

    return lines


def _merge_small_tail(chunks: list[TranscriptChunk], min_tail_chars: int = 260) -> list[TranscriptChunk]:
    if len(chunks) < 2:
        return chunks
    tail = chunks[-1]
    if len(tail.text) >= min_tail_chars:
        return chunks

    previous = chunks[-2]
    merged_text = f"{previous.text} {tail.text}".strip()
    merged = TranscriptChunk(
        text=merged_text,
        start_time=previous.start_time,
        end_time=tail.end_time,
        timestamp_label=_format_timestamp_label(previous.start_time, tail.end_time),
        source_url=previous.source_url,
        video_id=previous.video_id,
        chunk_index=previous.chunk_index,
    )
    return [*chunks[:-2], merged]


def chunk_video_transcript(
    segments: list[TranscriptLine],
    *,
    source_url: str,
    video_id: str,
    source_title: str,
    transcript_duration: float,
    target_chars: int = 900,
    min_chars: int = 700,
    max_chars: int = 1000,
) -> list[TextChunk]:
    chunks: list[TranscriptChunk] = []
    buffer: list[TranscriptLine] = []
    buffer_length = 0

    def flush_buffer() -> None:
        nonlocal buffer, buffer_length, chunks
        if not buffer:
            return
        text = clean_whitespace(" ".join(line.text for line in buffer))
        if not text:
            buffer = []
            buffer_length = 0
            return
        start_time = buffer[0].start_time
        end_time = buffer[-1].end_time
        chunks.append(
            TranscriptChunk(
                text=text,
                start_time=start_time,
                end_time=end_time,
                timestamp_label=_format_timestamp_label(start_time, end_time),
                source_url=source_url,
                video_id=video_id,
                chunk_index=len(chunks),
            )
        )
        buffer = []
        buffer_length = 0

    for segment in segments:
        segment_length = len(segment.text)
        if buffer and buffer_length >= min_chars and buffer_length + segment_length + 1 > max_chars:
            flush_buffer()
        buffer.append(segment)
        buffer_length += segment_length + 1
        if buffer_length >= target_chars:
            flush_buffer()

    flush_buffer()
    chunks = _merge_small_tail(chunks)

    return [
        TextChunk(
            index=chunk.chunk_index,
            text=chunk.text,
            token_estimate=estimate_tokens(chunk.text),
            extra_metadata={
                "source_type": "video",
                "source_ref": source_url,
                "source_url": source_url,
                "source_title": source_title,
                "video_id": video_id,
                "timestamp_label": chunk.timestamp_label,
                "start_time": chunk.start_time,
                "end_time": chunk.end_time,
                "transcript_duration": transcript_duration,
            },
        )
        for chunk in chunks
    ]


def extract_youtube_transcript(url: str) -> YouTubeTranscriptResponse:
    video_id = extract_video_id(url)
    canonical_url = canonical_youtube_url(video_id)
    title = _get_video_title(canonical_url)
    segments = _fetch_transcript_lines(video_id)
    transcript_duration = max(segment.end_time for segment in segments)
    chunks = chunk_video_transcript(
        segments,
        source_url=canonical_url,
        video_id=video_id,
        source_title=title,
        transcript_duration=transcript_duration,
    )
    return YouTubeTranscriptResponse(
        video_id=video_id,
        canonical_url=canonical_url,
        title=title,
        transcript_duration=transcript_duration,
        segments=[
            TranscriptSegment(
                text=segment.text,
                start_time=segment.start_time,
                duration=segment.duration,
                end_time=segment.end_time,
            )
            for segment in segments
        ],
        chunks=[
            TranscriptChunk(
                text=chunk.text,
                start_time=float(chunk.extra_metadata.get("start_time", 0.0)),
                end_time=float(chunk.extra_metadata.get("end_time", 0.0)),
                timestamp_label=str(chunk.extra_metadata.get("timestamp_label", "")),
                source_url=str(chunk.extra_metadata.get("source_url", canonical_url)),
                video_id=str(chunk.extra_metadata.get("video_id", video_id)),
                chunk_index=chunk.index,
            )
            for chunk in chunks
        ],
        warnings=[],
    )
