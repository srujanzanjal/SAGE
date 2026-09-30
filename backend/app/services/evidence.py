"""Evidence highlighting: which sentences of a cited chunk support the answer.

Runs on the local embedding model (no LLM call): the answer sentences that cite
a chunk are compared with each sentence of that chunk, and the closest few are
returned as character spans for the UI to highlight.
"""
from __future__ import annotations

import re

from app.services.embeddings import get_embedding_service
from app.services.reranker import keyword_overlap_score
from app.services.vector_store import get_vector_store

# Sentences end at punctuation or a paragraph break; single line breaks are
# layout (transcript caption lines, wrapped PDF text), not sentence ends.
SENTENCE = re.compile(r"(?:[^.!?।\n]|\n(?!\n))+(?:[.!?।]+|$)")
MIN_SENTENCE_CHARS = 20
MIN_SCORE = 0.30       # below this nothing in the chunk really matches the claim
SEMANTIC_WEIGHT = 0.7  # the rest is keyword overlap with the claim
NEAR_BEST = 0.08       # also highlight sentences almost as close as the best one
MAX_HIGHLIGHTS = 3


def sentence_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for match in SENTENCE.finditer(text):
        start, end = match.start(), match.end()
        # Skip whitespace and closing brackets/quotes left over from the previous sentence.
        while start < end and (text[start].isspace() or text[start] in ")]}\"'”’"):
            start += 1
        if end - start >= MIN_SENTENCE_CHARS:
            spans.append((start, end))
    return spans


def pick_highlights(scores: list[float]) -> list[int]:
    """Indexes of sentences to highlight: the best match plus any close runners-up."""
    if not scores or max(scores) < MIN_SCORE:
        return []
    best = max(scores)
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return sorted(i for i in ranked[:MAX_HIGHLIGHTS] if scores[i] >= best - NEAR_BEST)


def clean_claim(text: str) -> str:
    text = re.sub(r"\[S\d+(?:,\s*S\d+)*\]|【S\d+】", "", text)
    return re.sub(r"[*`#_]+", "", text).strip()


def find_evidence(chunk_id: str, claims: list[str]) -> dict:
    chunk = get_vector_store().get_chunk(chunk_id)
    if chunk is None:
        raise LookupError(f"Chunk not found: {chunk_id}")
    text = chunk.text
    if text.startswith("__SAGE_"):  # internal overview marker line
        text = text.split("\n", 1)[1] if "\n" in text else ""
    # Join layout line breaks so the passage reads as prose and sentences stay whole.
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)

    claims = [c for c in (clean_claim(c) for c in claims) if len(c) >= 8][:10]
    spans = sentence_spans(text)
    highlights: list[dict] = []
    if claims and spans:
        embedder = get_embedding_service()
        sentences = [text[s:e] for s, e in spans]
        # Each sentence is also embedded with the one before it, so a sentence
        # like "He lives in the present" keeps who "he" is.
        windows = [f"{sentences[i - 1]} {sentences[i]}" if i else sentences[i] for i in range(len(sentences))]
        claim_vectors = embedder.embed_documents(claims)
        sentence_vectors = embedder.embed_documents(sentences)
        window_vectors = embedder.embed_documents(windows)

        def cosine(a, b):  # vectors are L2-normalized
            return sum(x * y for x, y in zip(a, b))

        scores = [
            max(
                SEMANTIC_WEIGHT * max(cosine(sentence_vectors[i], cv), cosine(window_vectors[i], cv))
                + (1 - SEMANTIC_WEIGHT) * keyword_overlap_score(claim, sentences[i])
                for claim, cv in zip(claims, claim_vectors)
            )
            for i in range(len(sentences))
        ]
        highlights = [{"start": spans[i][0], "end": spans[i][1], "score": round(scores[i], 3)} for i in pick_highlights(scores)]
    return {"chunk_id": chunk_id, "text": text, "highlights": highlights}
