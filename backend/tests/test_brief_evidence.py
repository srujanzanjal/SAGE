import pytest

from app.models.schemas import Citation
from app.services.evidence import clean_claim, pick_highlights, sentence_spans
from app.services.retrieval_types import RetrievedChunk
from app.services.source_brief import _select_chunks, parse_brief


def _citation(cid, start_time=None):
    return Citation(
        citation_id=cid, chunk_id=f"chk_{cid}", source_id="src", source_type="video", source_ref="ref",
        snippet="s", chunk_index=0, score=0.5, start_time=start_time, timestamp_label="00:00",
    )


def test_parse_brief_attaches_citations_and_orders_video_chapters():
    citations = {"S1": _citation("S1", 300.0), "S2": _citation("S2", 10.0)}
    raw = """```json
    {"summary": "A talk about procrastination.",
     "key_points": [{"text": "The monkey wants fun now.", "cite": "S2"}, {"text": "", "cite": "S1"}],
     "sections": [{"title": "Life Calendar", "detail": "Weeks of a life.", "cite": "[S1]"},
                  {"title": "Intro", "detail": "College papers.", "cite": "S2"},
                  {"title": "Uncited", "detail": "x", "cite": "S9"}],
     "questions": ["What is the Panic Monster?"]}
    ```"""
    brief = parse_brief(raw, citations, "video")
    assert brief["summary"] == "A talk about procrastination."
    assert len(brief["key_points"]) == 1 and brief["key_points"][0]["citation"]["chunk_id"] == "chk_S2"
    assert [s["title"] for s in brief["sections"]] == ["Uncited", "Intro", "Life Calendar"]
    assert brief["sections"][0]["citation"] is None
    assert brief["section_label"] == "Chapters"


def test_parse_brief_rejects_missing_summary():
    with pytest.raises(ValueError):
        parse_brief('{"key_points": []}', {}, "pdf")


def test_select_chunks_keeps_overview_and_spreads_over_source():
    def chunk(i, kind=None):
        meta = {"chunk_index": i, **({"chunk_kind": kind} if kind else {})}
        return RetrievedChunk(chunk_id=str(i), text="x" * 1000, metadata=meta, distance=1.0, semantic_score=0.0)

    chunks = [chunk(0, "source_overview")] + [chunk(i) for i in range(1, 41)]
    picked = _select_chunks(chunks, budget=11_000)
    assert picked[0].chunk_id == "0"
    ids = [int(c.chunk_id) for c in picked[1:]]
    assert len(ids) == 10 and ids[0] == 1 and ids[-1] > 30  # covers the end, not just the start


def test_sentence_spans_and_highlight_picking():
    text = "Short. The Panic Monster wakes up near deadlines.\nIt scares the monkey away for good."
    spans = sentence_spans(text)
    assert [text[s:e] for s, e in spans] == ["The Panic Monster wakes up near deadlines.", "It scares the monkey away for good."]
    assert pick_highlights([0.2, 0.25]) == []                 # nothing close enough
    assert pick_highlights([0.9, 0.5, 0.85]) == [0, 2]       # best plus a near runner-up
    cleaned = clean_claim("It wakes up **near deadlines** [S1], [S2]【S3】.")
    assert cleaned.startswith("It wakes up near deadlines") and "S1" not in cleaned and "*" not in cleaned and "S3" not in cleaned
