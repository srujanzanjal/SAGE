import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from app.services.text_utils import clean_whitespace, estimate_tokens


@dataclass
class TextChunk:
    index: int
    text: str
    token_estimate: int
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    extra_metadata: dict[str, object] = field(default_factory=dict)


_SENTENCE_RE = re.compile(r"(?<=[.!?।])\s+")


def _split_sentences(text: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    sentences: list[str] = []
    for paragraph in paragraphs:
        parts = [s.strip() for s in _SENTENCE_RE.split(paragraph) if s.strip()]
        if parts:
            sentences.extend(parts)
        else:
            sentences.append(paragraph)
    return sentences


def _split_long_text(text: str, max_chars: int) -> Iterable[str]:
    for i in range(0, len(text), max_chars):
        yield text[i : i + max_chars]


def chunk_text(
    text: str,
    chunk_size_chars: int = 1200,
    overlap_chars: int = 180,
    page_number: Optional[int] = None,
) -> list[TextChunk]:
    """Sentence-aware chunking with lightweight overlap.

    It avoids cutting sentences whenever possible while keeping chunks bounded.
    """
    text = clean_whitespace(text)
    if not text:
        return []

    sentences = _split_sentences(text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if len(sentence) > chunk_size_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(part.strip() for part in _split_long_text(sentence, chunk_size_chars) if part.strip())
            continue

        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= chunk_size_chars:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            overlap = current[-overlap_chars:] if overlap_chars > 0 else ""
            current = f"{overlap} {sentence}".strip() if overlap else sentence

    if current:
        chunks.append(current.strip())

    return [
        TextChunk(index=i, text=chunk, token_estimate=estimate_tokens(chunk), page_number=page_number)
        for i, chunk in enumerate(chunks)
        if chunk.strip()
    ]


def chunk_pages(
    pages: list[tuple[int, str]],
    chunk_size_chars: int = 1200,
    overlap_chars: int = 180,
) -> list[TextChunk]:
    all_chunks: list[TextChunk] = []
    global_index = 0
    for page_number, page_text in pages:
        page_chunks = chunk_text(page_text, chunk_size_chars, overlap_chars, page_number=page_number)
        for chunk in page_chunks:
            chunk.index = global_index
            global_index += 1
            all_chunks.append(chunk)
    return all_chunks
