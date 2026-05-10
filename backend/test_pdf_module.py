#!/usr/bin/env python
"""PDF Module QA Test Runner - Tests all PDF QA scenarios."""
import os
import sys
import requests
import json
import time
from dataclasses import dataclass
from pathlib import Path


API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000/api/v1")
PDF_SOURCE_ID = os.getenv("PDF_SOURCE_ID", None)
TIMEOUT = 60
SLEEP_BETWEEN = 1  # seconds between questions

session = requests.Session()


@dataclass
class Citation:
    citation_id: str
    source_id: str
    source_type: str
    source_ref: str
    page_number: int | None
    snippet: str
    score: float
    chunk_index: int


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
    """Make HTTP request and parse JSON."""
    url = f"{API_BASE}{path}"
    kwargs.setdefault("timeout", TIMEOUT)
    response = session.request(method, url, **kwargs)
    if not response.ok:
        raise Exception(f"{response.status_code}: {response.text}")
    return response.json()


def health_check():
    """Check backend health."""
    try:
        data = request_json("GET", "/../../health")
        print(f"✓ Backend health: {data.get('status')} ({data.get('app_name')})")
        return True
    except Exception as e:
        print(f"✗ Backend health check failed: {e}")
        return False


def list_sources():
    """List all sources and find latest ready PDF."""
    try:
        data = request_json("GET", "/sources")
        pdf_sources = [s for s in data if s.get("source_type") == "pdf" and s.get("status") == "ready" and s.get("chunks_count", 0) > 0]
        if pdf_sources:
            # Return latest by created_at or just the first ready one
            latest = max(pdf_sources, key=lambda x: x.get("created_at", ""), default=pdf_sources[0])
            return latest
        return None
    except Exception as e:
        print(f"✗ Failed to list sources: {e}")
        return None


def upload_pdf(pdf_path):
    """Upload PDF and return source data."""
    try:
        with open(pdf_path, "rb") as f:
            files = {"file": (os.path.basename(pdf_path), f, "application/pdf")}
            data = request_json("POST", "/ingest/pdf", files=files)
        print(f"✓ Uploaded PDF: {data.get('title', 'Unknown')} (chunks: {data.get('chunks_count')})")
        return data
    except Exception as e:
        print(f"✗ PDF upload failed: {e}")
        return None


def print_source_info(source):
    """Print selected PDF source info."""
    if not source:
        print("✗ No PDF source selected")
        return False
    
    print("\n" + "="*70)
    print("SELECTED PDF SOURCE")
    print("="*70)
    print(f"source_id:       {source.get('source_id')}")
    print(f"knowledgebase_id: {source.get('knowledgebase_id')}")
    print(f"title:           {source.get('title', 'N/A')}")
    print(f"canonical_ref:   {source.get('canonical_ref', 'N/A')}")
    print(f"original_ref:    {source.get('original_ref', 'N/A')}")
    print(f"chunks_count:    {source.get('chunks_count', 0)}")
    print(f"page_count:      {source.get('page_count', 'N/A')}")
    print(f"status:          {source.get('status')}")
    print("="*70 + "\n")
    return True


def ask_question(source_id, kb_id, question, mode="grounded"):
    """Ask a question and return QA result."""
    try:
        start = time.time()
        payload = {
            "question": question,
            "mode": mode,
            "source_id": source_id,
            "top_k": 6,
        }
        data = request_json("POST", "/qa/ask", json=payload)
        elapsed = time.time() - start
        
        citations = data.get("citations", [])
        
        result = QAResult(
            question=question,
            mode=mode,
            confidence=data.get("confidence_score", 0),
            citations_count=len(citations),
            retrieved_sources=data.get("retrieved_source_count", 0),
            response_time=elapsed,
            answer=data.get("answer", ""),
            citations=citations,
            status="PASS" if data.get("confidence_score", 0) > 0.1 else "PARTIAL" if data.get("answer") else "FAIL"
        )
        return result
    except Exception as e:
        return QAResult(
            question=question,
            mode=mode,
            confidence=0,
            citations_count=0,
            retrieved_sources=0,
            response_time=0,
            answer="",
            citations=[],
            status=f"FAIL: {e}"
        )


def run_qa_tests(source_id, kb_id):
    """Run all QA tests PQ1-PQ10."""
    tests = [
        ("PQ1", "What does SAGE stand for?", "grounded"),
        ("PQ2", "Which intelligence modules does SAGE support?", "grounded"),
        ("PQ3", "How does the PDF module work?", "grounded"),
        ("PQ4", "Summarize this PDF.", "grounded"),
        ("PQ5", "What database stores metadata?", "grounded"),
        ("PQ6", "What database stores vectors?", "grounded"),
        ("PQ7", "What is the capital of Japan?", "grounded"),
        ("PQ8", "fees?", "grounded"),
        ("PQ9", "Explain SAGE to a beginner.", "exploratory"),
        ("PQ10", "What tool is used to extract text from PDFs?", "grounded"),
    ]
    
    results = []
    print("\n" + "="*80)
    print("QA TEST RESULTS")
    print("="*80)
    print(f"{'QID':<6} {'Question':<40} {'Mode':<12} {'Conf':<6} {'Cit':<4} {'Status':<10}")
    print("-"*80)
    
    for qid, question, mode in tests:
        result = ask_question(source_id, kb_id, question, mode)
        results.append((qid, result))
        
        conf_str = f"{result.confidence:.2f}"
        print(f"{qid:<6} {question[:37]:<40} {mode:<12} {conf_str:<6} {result.citations_count:<4} {result.status:<10}")
        time.sleep(SLEEP_BETWEEN)
    
    print("-"*80)
    pass_count = sum(1 for _, r in results if r.status == "PASS")
    partial_count = sum(1 for _, r in results if r.status == "PARTIAL")
    fail_count = sum(1 for _, r in results if r.status.startswith("FAIL"))
    print(f"SUMMARY: {pass_count} Pass, {partial_count} Partial, {fail_count} Fail / {len(results)} Total")
    print("="*80 + "\n")
    
    return results


def extract_citation_data(qid, question, result):
    """Extract citation data from QA result."""
    if not result.citations:
        return []
    
    citations = []
    for cite in result.citations[:6]:  # First 6 citations
        citations.append({
            "test_id": f"C{qid.replace('PQ', '')}",
            "question": question,
            "citation_id": cite.get("citation_id", ""),
            "source_type": cite.get("source_type", ""),
            "source_ref": cite.get("source_ref", ""),
            "page_number": cite.get("page_number", None),
            "snippet": cite.get("snippet", "")[:80] + "..." if len(cite.get("snippet", "")) > 80 else cite.get("snippet", ""),
            "score": cite.get("score", 0),
            "chunk_index": cite.get("chunk_index", 0),
        })
    
    return citations


if __name__ == "__main__":
    print("\n🔍 SAGE PDF Module QA Test Runner\n")
    
    # Step 1: Health check
    if not health_check():
        sys.exit(1)
    
    # Step 2: Get or upload PDF source
    source = None
    if PDF_SOURCE_ID:
        print(f"Using override source_id: {PDF_SOURCE_ID}")
        # Try to fetch source details
        try:
            data = request_json("GET", f"/sources")
            sources = [s for s in data if s.get("source_id") == PDF_SOURCE_ID]
            source = sources[0] if sources else None
        except:
            pass
    else:
        # List and find latest ready PDF
        source = list_sources()
        if not source:
            print("No ready PDF source found. Uploading valid_sage_test.pdf...")
            pdf_path = Path(__file__).parent / "valid_sage_test.pdf"
            if pdf_path.exists():
                source = upload_pdf(str(pdf_path))
            else:
                print(f"✗ PDF not found at {pdf_path}")
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
    print("="*80)
    all_citations = []
    for (qid, result) in qa_results[:5]:
        citations = extract_citation_data(qid, result.question, result)
        all_citations.extend(citations)
        if citations:
            print(f"\n{qid}: {result.question}")
            for cite in citations[:2]:  # Show first 2 citations per question
                print(f"  - Page {cite['page_number']}: {cite['snippet']}")
                print(f"    Score: {cite['score']:.3f}, Chunk: {cite['chunk_index']}")
    
    print("\n" + "="*80)
    print("✓ PDF QA testing complete\n")
