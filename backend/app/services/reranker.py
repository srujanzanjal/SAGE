import re

from app.services.retrieval_types import RetrievedChunk

STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "from", "is", "are", "was", "were",
    "what", "why", "how", "when", "where", "which", "tell", "me", "about", "please", "give", "does", "do",
}


def _keywords(text: str) -> set[str]:
    words = set(re.findall(r"[A-Za-z0-9_]{3,}", text.lower()))
    return {w for w in words if w not in STOPWORDS}


def keyword_overlap_score(question: str, text: str) -> float:
    q = _keywords(question)
    if not q:
        return 0.0
    t = _keywords(text)
    return len(q & t) / len(q)


def rerank_chunks(question: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    for chunk in chunks:
        overlap = keyword_overlap_score(question, chunk.text)
        # Semantic retrieval should dominate; lexical overlap acts as a stabilizer.
        chunk.score = round((0.78 * chunk.semantic_score) + (0.22 * overlap), 4)
    return sorted(chunks, key=lambda c: c.score, reverse=True)
