from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.models.schemas import TranscriptSegment, VideoTranscriptResult
from app.services.video_transcript import canonical_youtube_url, extract_video_id
from app.utils.exceptions import VideoAutoTranscriptionError

ProgressCallback = Callable[[str, int, str], None]


def _report(progress_callback: ProgressCallback | None, step: str, percentage: int, message: str) -> None:
    if progress_callback:
        progress_callback(step, percentage, message)


def _pick_downloaded_audio_file(tmp_dir: str, video_id: str) -> Path:
    candidates = [p for p in Path(tmp_dir).glob(f"{video_id}.*") if p.is_file()]
    if not candidates:
        raise VideoAutoTranscriptionError("Audio download failed.", error_code="AUDIO_DOWNLOAD_FAILED")
    return sorted(candidates, key=lambda p: p.stat().st_size, reverse=True)[0]


def _validate_video_info(info: dict[str, Any]) -> None:
    settings = get_settings()

    extractor = str(info.get("extractor") or "").lower()
    if "youtube" not in extractor:
        raise VideoAutoTranscriptionError("Only YouTube videos are supported.", error_code="UNSUPPORTED_VIDEO")

    if bool(info.get("is_live")):
        raise VideoAutoTranscriptionError("Live streams are not supported.", error_code="UNSUPPORTED_VIDEO")

    availability = str(info.get("availability") or "").lower()
    if availability in {"private", "subscriber_only", "premium_only", "needs_auth"}:
        raise VideoAutoTranscriptionError("Video is private or unavailable.", error_code="UNSUPPORTED_VIDEO")

    duration = info.get("duration")
    if duration is None:
        raise VideoAutoTranscriptionError("Could not determine video duration.", error_code="UNSUPPORTED_VIDEO")

    if float(duration) > float(settings.video_auto_transcribe_max_duration_seconds):
        minutes = int(settings.video_auto_transcribe_max_duration_seconds // 60)
        raise VideoAutoTranscriptionError(
            f"Video exceeds maximum supported duration ({minutes} minutes).",
            error_code="VIDEO_TOO_LONG",
        )


def transcribe_youtube_video(url: str, progress_callback: ProgressCallback | None = None) -> VideoTranscriptResult:
    try:
        import yt_dlp
    except Exception as exc:
        raise VideoAutoTranscriptionError(
            "Automatic transcription requires yt-dlp. Install it with pip install yt-dlp.",
            error_code="TRANSCRIPTION_DEPENDENCY_MISSING",
        ) from exc

    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise VideoAutoTranscriptionError(
            "Automatic transcription requires faster-whisper. Install it with pip install faster-whisper.",
            error_code="TRANSCRIPTION_DEPENDENCY_MISSING",
        ) from exc

    settings = get_settings()
    video_id = extract_video_id(url)
    canonical_url = canonical_youtube_url(video_id)

    ydl_info_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": settings.request_timeout_seconds,
    }

    try:
        _report(progress_callback, "downloading audio", 10, "Loading video metadata")
        with yt_dlp.YoutubeDL(ydl_info_opts) as ydl:
            info = ydl.extract_info(canonical_url, download=False)
    except Exception as exc:
        raise VideoAutoTranscriptionError("Could not load YouTube metadata.", error_code="UNSUPPORTED_VIDEO") from exc

    if not isinstance(info, dict):
        raise VideoAutoTranscriptionError("Could not load YouTube metadata.", error_code="UNSUPPORTED_VIDEO")

    _validate_video_info(info)

    title = str(info.get("title") or "YouTube Video").strip() or "YouTube Video"
    duration_seconds = float(info.get("duration") or 0.0)

    with tempfile.TemporaryDirectory(prefix="sage-video-") as tmp_dir:
        outtmpl = os.path.join(tmp_dir, "%(id)s.%(ext)s")
        ydl_download_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "socket_timeout": settings.request_timeout_seconds,
            "overwrites": True,
        }

        try:
            _report(progress_callback, "downloading audio", 25, "Downloading video audio")
            with yt_dlp.YoutubeDL(ydl_download_opts) as ydl:
                ydl.extract_info(canonical_url, download=True)
            audio_file = _pick_downloaded_audio_file(tmp_dir, video_id)
        except VideoAutoTranscriptionError:
            raise
        except Exception as exc:
            raise VideoAutoTranscriptionError("Audio download failed.", error_code="AUDIO_DOWNLOAD_FAILED") from exc

        max_audio_bytes = int(settings.video_auto_transcribe_max_audio_mb) * 1024 * 1024
        if audio_file.stat().st_size > max_audio_bytes:
            raise VideoAutoTranscriptionError(
                f"Downloaded audio exceeds {settings.video_auto_transcribe_max_audio_mb} MB limit.",
                error_code="AUDIO_DOWNLOAD_FAILED",
            )

        try:
            _report(progress_callback, "transcribing audio", 45, "Transcribing audio with speech-to-text")
            model_name = settings.selected_whisper_model_size
            model = None
            last_error: Exception | None = None
            for compute_type in ("int8", "int8_float16", "float32"):
                try:
                    model = WhisperModel(model_name, compute_type=compute_type)
                    break
                except Exception as exc:
                    last_error = exc
                    model = None
            if model is None:
                raise last_error or RuntimeError("Could not initialize WhisperModel")
            transcript_stream, _ = model.transcribe(str(audio_file), beam_size=1, vad_filter=True)
        except Exception as exc:
            raise VideoAutoTranscriptionError("Audio transcription failed.", error_code="TRANSCRIPTION_FAILED") from exc

        segments: list[TranscriptSegment] = []
        for segment in transcript_stream:
            text = str(getattr(segment, "text", "")).strip()
            start = float(getattr(segment, "start", 0.0))
            end = float(getattr(segment, "end", start))
            duration = max(0.0, end - start)
            if text:
                segments.append(
                    TranscriptSegment(text=text, start_time=start, end_time=end, duration=duration)
                )

    if not segments:
        raise VideoAutoTranscriptionError("Audio transcription returned no text.", error_code="TRANSCRIPTION_FAILED")

    return VideoTranscriptResult(
        video_id=video_id,
        canonical_url=canonical_url,
        title=title,
        duration_seconds=duration_seconds,
        segments=segments,
        transcription_model=settings.selected_whisper_model_size,
        transcript_origin="auto_transcribed",
        warnings=[],
    )
