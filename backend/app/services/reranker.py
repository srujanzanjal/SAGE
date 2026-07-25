import math
import re

from app.services.retrieval_types import RetrievedChunk

STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "from", "is", "are", "was", "were",
    "what", "why", "how", "when", "where", "which", "tell", "me", "about", "please", "give", "does", "do",
}

# Standard Okapi BM25 constants (term-frequency saturation and length normalization).
BM25_K1 = 1.5
BM25_B = 0.75
# Squashes an unbounded BM25 score into [0, 1) via raw / (raw + K), so it stays on a
# comparable scale to semantic_score without depending on the size of the candidate pool.
BM25_SATURATION_K = 2.0


def _keywords(text: str) -> set[str]:
    words = set(re.findall(r"[A-Za-z0-9_]{3,}", text.lower()))
    return {w for w in words if w not in STOPWORDS}


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_]{3,}", text.lower())
    return [w for w in words if w not in STOPWORDS]


def keyword_overlap_score(question: str, text: str) -> float:
    q = _keywords(question)
    if not q:
        return 0.0
    t = _keywords(text)
    return len(q & t) / len(q)


def _bm25_lexical_scores(question: str, chunks: list[RetrievedChunk]) -> list[float]:
    """Okapi BM25 over the current candidate pool, used as a local sparse-retrieval corpus.

    Dense retrieval already narrows the corpus down to a widened top-k candidate set
    before reranking; treating that set as the BM25 corpus (rather than maintaining a
    separate persistent inverted index) is the standard, lightweight way to add a
    hybrid dense+sparse signal at the reranking stage. Term-document-frequency-based
    IDF and document-length normalization make this a genuine improvement over plain
    keyword-set overlap, which ignores term frequency, term rarity, and chunk length.
    """
    query_terms = _tokens(question)
    if not query_terms or not chunks:
        return [0.0] * len(chunks)

    doc_tokens = [_tokens(chunk.text) for chunk in chunks]
    n_docs = len(doc_tokens)
    avg_len = (sum(len(d) for d in doc_tokens) / n_docs) or 1.0

    doc_freq: dict[str, int] = {}
    for doc in doc_tokens:
        for term in set(doc):
            doc_freq[term] = doc_freq.get(term, 0) + 1

    idf = {
        term: math.log(1 + (n_docs - freq + 0.5) / (freq + 0.5))
        for term, freq in doc_freq.items()
    }

    unique_query_terms = set(query_terms)
    raw_scores = []
    for doc in doc_tokens:
        doc_len = len(doc) or 1
        term_freq: dict[str, int] = {}
        for term in doc:
            term_freq[term] = term_freq.get(term, 0) + 1

        score = 0.0
        for term in unique_query_terms:
            freq = term_freq.get(term)
            if not freq:
                continue
            numerator = idf[term] * freq * (BM25_K1 + 1)
            denominator = freq + BM25_K1 * (1 - BM25_B + BM25_B * doc_len / avg_len)
            score += numerator / denominator
        raw_scores.append(score)

    return [raw / (raw + BM25_SATURATION_K) for raw in raw_scores]


def rerank_chunks(question: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    bm25_scores = _bm25_lexical_scores(question, chunks)
    for chunk, bm25 in zip(chunks, bm25_scores):
        # BM25's IDF term rewards rare/distinctive query-term matches (good for exact
        # identifiers, error strings, etc.), but it can under-reward a chunk for broad,
        # generic-phrasing questions ("what is this website about") when every query
        # term is common across the whole candidate pool -- exactly the case a
        # deterministic overview chunk exists to answer. Plain keyword-set overlap has
        # no IDF, so it doesn't share that failure mode: it gives full credit for
        # simply containing every query term at all. Taking the max of the two keeps
        # BM25's rare-term benefit while guaranteeing broad-question retrieval of the
        # overview chunk never regresses relative to plain overlap.
        overlap = keyword_overlap_score(question, chunk.text)
        # Only the *full-coverage* case (every query keyword present at least once)
        # gets the safety floor: that's the one guarantee plain overlap can make that
        # BM25 can't, since BM25's IDF can legitimately treat a common word as
        # low-signal even when it's the exact word the question asked about. Partial
        # matches (< 1.0) are exactly where BM25's rarity-aware differentiation is a
        # genuine improvement over overlap's coarse, tied fractions, so it's left
        # untouched there.
        lexical = 1.0 if overlap >= 1.0 else bm25
        # Semantic retrieval should dominate; the lexical signal acts as a stabilizer.
        chunk.score = round((0.78 * chunk.semantic_score) + (0.22 * lexical), 4)
    return sorted(chunks, key=lambda c: c.score, reverse=True)
