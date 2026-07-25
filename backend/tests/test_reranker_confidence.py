from app.services.confidence import calculate_confidence
from app.services.reranker import keyword_overlap_score, rerank_chunks
from app.services.retrieval_types import RetrievedChunk


def test_keyword_overlap_score_detects_overlap():
    score = keyword_overlap_score("What are admission fees?", "The admission fees are listed in the brochure.")
    assert score > 0


def test_rerank_and_confidence_reasonable():
    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            text="Admission fees and eligibility are mentioned here.",
            metadata={},
            distance=0.1,
            semantic_score=0.9,
        ),
        RetrievedChunk(
            chunk_id="c2",
            text="Unrelated cafeteria information.",
            metadata={},
            distance=0.7,
            semantic_score=0.3,
        ),
    ]
    ranked = rerank_chunks("admission fees", chunks)
    assert ranked[0].chunk_id == "c1"
    assert 0 <= calculate_confidence(ranked) <= 1


def test_rerank_prefers_rare_term_match_over_common_term_match():
    """BM25's IDF component should rank a rare/distinctive query-term match above a
    common-term match, even when plain keyword-set overlap would score them equally
    (each chunk matches exactly one of the two query keywords)."""
    chunks = [
        RetrievedChunk(
            chunk_id="common_term",
            text="Python is a popular programming language for beginners.",
            metadata={},
            distance=0.5,
            semantic_score=0.5,
        ),
        RetrievedChunk(
            chunk_id="rare_term",
            text="Eigenvalue decomposition is used in linear algebra.",
            metadata={},
            distance=0.5,
            semantic_score=0.5,
        ),
        RetrievedChunk(
            chunk_id="filler",
            text="Python developers often use python for scripting tasks.",
            metadata={},
            distance=0.5,
            semantic_score=0.5,
        ),
    ]

    ranked = rerank_chunks("python eigenvalue", chunks)
    scores = {c.chunk_id: c.score for c in ranked}
    assert scores["rare_term"] > scores["common_term"]
