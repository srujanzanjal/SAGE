#!/usr/bin/env python
"""Video Module QA Test Runner - Tests all Video QA scenarios."""
import os
import sys
import requests
import json
import time
from dataclasses import dataclass

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000/api/v1")
VIDEO_SOURCE_ID = os.getenv("VIDEO_SOURCE_ID", None)
TIMEOUT = 90
SLEEP_BETWEEN = 1  # base seconds between questions (grounded)

# Note: exploratory (LLM-heavy) questions will sleep longer to avoid TPM limits
EXPLORATORY_SLEEP = 2

session = requests.Session()

@dataclass
class QAResult:
    question: str
    mode: str
    confidence: float
    citations_count: int
    retrieved_sources: int
    response_time: float
    answer: str
    citations: list
    status: str

def request_json(method, path, **kwargs):
    """Make HTTP request and return (response, json_or_empty).

    Caller should inspect status codes rather than rely on exceptions.
    """
    url = f"{API_BASE}{path}"
    kwargs.setdefault("timeout", TIMEOUT)
    response = session.request(method, url, **kwargs)
    try:
        payload = response.json() if response.text else {}
    except Exception:
        payload = {}
    return response, payload

def health_check():
    """Check backend health."""
    try:
        response = session.get("http://127.0.0.1:8000/health", timeout=TIMEOUT)
        data = response.json() if response.text else {}
        print(f"✓ Backend health: {data.get('status')} ({data.get('app_name')})")
        return True
    except Exception as e:
        print(f"✗ Backend health check failed: {e}")
        return False

def list_sources():
    """List all sources and find latest ready video."""
    try:
        _, data = request_json("GET", "/sources")
        videos = [s for s in data if s.get("source_type") == "video" and s.get("status") == "ready" and s.get("chunks_count", 0) > 0]
        if videos:
            latest = max(videos, key=lambda x: x.get("created_at", ""), default=videos[0])
            return latest
        return None
    except Exception as e:
        print(f"✗ Failed to list sources: {e}")
        return None

def print_source_info(source):
    """Print selected video source info."""
    if not source:
        print("✗ No video source selected")
        return False
    
    print("\n" + "="*70)
    print("SELECTED VIDEO SOURCE")
    print("="*70)
    print(f"source_id:           {source.get('source_id')}")
    print(f"knowledgebase_id:    {source.get('knowledgebase_id')}")
    print(f"title:               {source.get('title', 'N/A')}")
    print(f"canonical_ref:       {source.get('canonical_ref', 'N/A')}")
    print(f"original_ref:        {source.get('original_ref', 'N/A')}")
    print(f"chunks_count:        {source.get('chunks_count', 0)}")
    print(f"transcript_duration: {source.get('transcript_duration', 'N/A')} seconds")
    print(f"transcript_origin:   {source.get('transcript_origin', 'N/A')}")
    print(f"video_id:            {source.get('video_id', 'N/A')}")
    print(f"status:              {source.get('status')}")
    print("="*70 + "\n")
    return True

def ask_question(source_id, kb_id, question, mode="grounded"):
    """Ask a question and return QA result.

    Handles external provider rate-limits (429) and marks them as PARTIAL / EXTERNAL_PROVIDER_LIMIT.
    """
    start = time.time()
    payload = {
        "question": question,
        "mode": mode,
        "source_id": source_id,
        "top_k": 6,
    }

    resp, data = request_json("POST", "/qa/ask", json=payload)
    elapsed = time.time() - start

    # Handle rate limit from LLM provider
    if resp.status_code == 429 or (isinstance(data, dict) and "rate limit" in json.dumps(data).lower()):
        return QAResult(
            question=question,
            mode=mode,
            confidence=data.get("confidence_score", 0) if isinstance(data, dict) else 0,
            citations_count=len(data.get("citations", [])) if isinstance(data, dict) else 0,
            retrieved_sources=data.get("retrieved_source_count", 0) if isinstance(data, dict) else 0,
            response_time=elapsed,
            answer=data.get("answer", "") if isinstance(data, dict) else "",
            citations=data.get("citations", []) if isinstance(data, dict) else [],
            status="PARTIAL: EXTERNAL_PROVIDER_LIMIT"
        )

    if not resp.ok:
        # Non-429 errors are treated as failures for the QA run
        return QAResult(
            question=question,
            mode=mode,
            confidence=0,
            citations_count=0,
            retrieved_sources=0,
            response_time=elapsed,
            answer="",
            citations=[],
            status=f"FAIL: HTTP {resp.status_code}"
        )

    # Successful response
    citations = data.get("citations", []) if isinstance(data, dict) else []
    confidence = data.get("confidence_score", 0) if isinstance(data, dict) else 0
    status = "PASS" if confidence > 0.1 and len(citations) > 0 else "PARTIAL" if data.get("answer") else "FAIL"

    return QAResult(
        question=question,
        mode=mode,
        confidence=confidence,
        citations_count=len(citations),
        retrieved_sources=data.get("retrieved_source_count", 0) if isinstance(data, dict) else 0,
        response_time=elapsed,
        answer=data.get("answer", "") if isinstance(data, dict) else "",
        citations=citations,
        status=status
    )

def run_qa_tests(source_id, kb_id):
    """Run all QA tests VQ1-VQ10."""
    tests = [
        ("VQ1", "What is this video about?", "grounded"),
        ("VQ2", "Summarize the main points of the video.", "grounded"),
        ("VQ3", "What does the speaker explain in the beginning?", "grounded"),
        ("VQ4", "List three important ideas from the video.", "grounded"),
        ("VQ5", "What conclusion or final message does the speaker give?", "grounded"),
        ("VQ6", "contact?", "grounded"),
        ("VQ7", "fees?", "grounded"),
        ("VQ8", "What is the capital of Japan?", "grounded"),
        ("VQ9", "Explain this video to a beginner.", "exploratory"),
        ("VQ10", "Give me a study-note style summary from this video.", "exploratory"),
    ]
    
    results = []
    print("\n" + "="*90)
    print("QA TEST RESULTS")
    print("="*90)
    print(f"{'QID':<6} {'Question':<50} {'Mode':<12} {'Conf':<6} {'Cit':<4} {'Status':<10}")
    print("-"*90)
    
    for qid, question, mode in tests:
        result = ask_question(source_id, kb_id, question, mode)
        results.append((qid, result))

        conf_str = f"{result.confidence:.2f}"
        print(f"{qid:<6} {question[:47]:<50} {mode:<12} {conf_str:<6} {result.citations_count:<4} {result.status:<10}")

        # Sleep longer for exploratory (LLM-heavy) questions to help avoid provider TPM limits
        if mode == "exploratory":
            time.sleep(EXPLORATORY_SLEEP)
        else:
            time.sleep(SLEEP_BETWEEN)
    
    print("-"*90)
    pass_count = sum(1 for _, r in results if r.status == "PASS")
    partial_count = sum(1 for _, r in results if r.status == "PARTIAL")
    fail_count = sum(1 for _, r in results if r.status.startswith("FAIL"))
    print(f"SUMMARY: {pass_count} Pass, {partial_count} Partial, {fail_count} Fail / {len(results)} Total")
    print("="*90 + "\n")
    
    return results

def extract_citation_data(qid, question, result):
    """Extract citation data from QA result."""
    if not result.citations:
        return []
    
    citations = []
    for cite in result.citations[:6]:  # First 6 citations
        citations.append({
            "test_id": f"C{qid.replace('VQ', '')}",
            "question": question,
            "citation_id": cite.get("citation_id", ""),
            "source_type": cite.get("source_type", ""),
            "source_ref": cite.get("source_ref", ""),
            "timestamp_label": cite.get("timestamp_label", "N/A"),
            "start_time": cite.get("start_time", None),
            "end_time": cite.get("end_time", None),
            "snippet": cite.get("snippet", "")[:80] + "..." if len(cite.get("snippet", "")) > 80 else cite.get("snippet", ""),
            "score": cite.get("score", 0),
            "chunk_index": cite.get("chunk_index", 0),
        })
    
    return citations

if __name__ == "__main__":
    print("\n🎬 SAGE Video Module QA Test Runner\n")
    
    # Step 1: Health check
    if not health_check():
        sys.exit(1)
    
    # Step 2: Get or find video source
    source = None
    if VIDEO_SOURCE_ID:
        print(f"Using override source_id: {VIDEO_SOURCE_ID}")
        try:
            _, data = request_json("GET", f"/sources")
            sources = [s for s in data if s.get("source_id") == VIDEO_SOURCE_ID]
            source = sources[0] if sources else None
            if not source:
                print("! Override source not found. Falling back to latest ready video source.")
                source = list_sources()
        except:
            pass
    else:
        # Find latest ready video
        source = list_sources()
        if not source:
            print("✗ No ready video source found")
            sys.exit(1)
    
    # Print source info
    if not print_source_info(source):
        sys.exit(1)
    
    source_id = source.get("source_id")
    kb_id = source.get("knowledgebase_id")
    
    # Step 3: Run QA tests
    qa_results = run_qa_tests(source_id, kb_id)
    
    # Step 4: Extract and display citation data (sample)
    print("\nSAMPLE CITATION DATA (from first 5 QA results):")
    print("="*90)
    all_citations = []
    for (qid, result) in qa_results[:5]:
        citations = extract_citation_data(qid, result.question, result)
        all_citations.extend(citations)
        if citations:
            print(f"\n{qid}: {result.question}")
            for cite in citations[:2]:  # Show first 2 citations per question
                print(f"  - Timestamp: {cite['timestamp_label']}")
                print(f"    Snippet: {cite['snippet']}")
                print(f"    Score: {cite['score']:.3f}, Chunk: {cite['chunk_index']}")
    
    print("\n" + "="*90)
    print("✓ Video QA testing complete\n")
