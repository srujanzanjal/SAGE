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
