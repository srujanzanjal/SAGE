from __future__ import annotations

import logging

from langdetect import DetectorFactory, LangDetectException, detect

logger = logging.getLogger(__name__)

# Deterministic detection: langdetect's underlying Naive Bayes sampling is
# otherwise randomized, which would make the same text detect inconsistently
# across ingestion runs.
DetectorFactory.seed = 0

MIN_CHARS_FOR_DETECTION = 40
DETECTION_SAMPLE_CHARS = 2000


def detect_language(text: str) -> str | None:
    """Best-effort language code (e.g. 'en', 'hi', 'es', 'ja'), or None if the
    text is too short to detect reliably or detection otherwise fails."""
    sample = (text or "").strip()
    if len(sample) < MIN_CHARS_FOR_DETECTION:
        return None
    try:
        return detect(sample[:DETECTION_SAMPLE_CHARS])
    except LangDetectException:
        return None


def is_english(text: str) -> bool:
    language = detect_language(text)
    return language is None or language == "en"


def translate_if_needed(text: str) -> tuple[str, str | None, bool, bool]:
    """Detect the language of `text` and translate it to English via the LLM if
    it isn't already English (or too short to tell). Returns (possibly-translated
    text, detected language code or None if no translation was needed,
    segments_ok, truncated). When no translation was needed, segments_ok is
    True and truncated is False. Otherwise: segments_ok is False if any
    segment fell back to its original text (e.g. a provider error -- callers
    should not claim that source as "translated" when this is False); truncated
    is True if the text was longer than the provider can translate in one
    ingestion pass, in which case the tail was left in its original language to
    bound worst-case latency. These are reported separately because they're
    different situations to surface to a user: a translation failure versus a
    long page that was only partially translated."""
    language = detect_language(text)
    if language is None or language == "en":
        return text, None, True, False

    from app.services.llm import get_llm_service

    llm = get_llm_service()
    translated, segments_ok, truncated = llm.translate_to_english(text, source_language=language)
    return translated, language, segments_ok, truncated
