from app.services.retrieval_types import RetrievedChunk


def calculate_confidence(chunks: list[RetrievedChunk]) -> float:
    """Heuristic confidence score based on retrieval strength.

    This is not a probability. It is a UI signal to help users judge how strongly
    the answer is grounded in retrieved context.
    """
    if not chunks:
        return 0.0

    top = chunks[:3]
    avg_score = sum(c.score for c in top) / len(top)
    best_score = top[0].score
    coverage_bonus = min(len(chunks), 5) * 0.025
    confidence = (0.65 * best_score) + (0.35 * avg_score) + coverage_bonus
    return round(max(0.0, min(1.0, confidence)), 2)


def confidence_label_and_reason(question: str, chunks: list[RetrievedChunk], confidence: float) -> tuple[str, str]:
    if not chunks:
        return "Low", "few relevant chunks"

    q = question.strip().lower().rstrip("?")
    vague_queries = {"fees", "contact", "about", "summary", "cost", "price"}
    top = chunks[0]
    if q in vague_queries or len(q.split()) <= 2:
        return ("Low" if confidence < 0.45 else "Medium"), "vague query"
    if len(chunks) < 3:
        return ("Medium" if confidence >= 0.4 else "Low"), "few relevant chunks"
    if top.semantic_score >= 0.75 and top.score >= 0.7:
        return "High", "strong semantic match"
    if confidence >= 0.6:
        return "High", "strong semantic match"
    if confidence >= 0.4:
        return "Medium", "weak evidence"
    return "Low", "weak evidence"
