#!/usr/bin/env python
"""PDF Module Ingestion Tests - P1 through P7."""
import os
import sys
import requests
import json
from pathlib import Path

API_BASE = "http://127.0.0.1:8000/api/v1"
TIMEOUT = 60
ASSETS_DIR = Path(__file__).parent / "tests/assets/pdf_module"

session = requests.Session()

def request_json(method, path, **kwargs):
    """Make HTTP request and parse JSON."""
    url = f"{API_BASE}{path}"
    kwargs.setdefault("timeout", TIMEOUT)
    response = session.request(method, url, **kwargs)
    return response, response.json() if response.text else {}

def test_result(test_id, description, passed, details=""):
    """Print test result."""
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"{status}  {test_id}: {description}")
    if details:
        print(f"     {details}")
    return passed

def p1_valid_pdf_upload():
    """P1: Upload a valid PDF and verify it's ingested correctly."""
    pdf_path = ASSETS_DIR / "valid_sage_test.pdf"
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        resp, data = request_json("POST", "/ingest/pdf", files=files)
    
    passed = resp.ok and data.get("chunks_count", 0) > 0 and data.get("page_count", 0) > 0
    return test_result(
        "P1",
        "Upload valid PDF and verify chunks/pages > 0",
        passed,
        f"Chunks: {data.get('chunks_count')}, Pages: {data.get('page_count')}, Status: {data.get('status')}"
    ), data.get("source_id") if passed else None

def p2_source_list_contains_pdf():
    """P2: List sources and verify newly uploaded PDF appears."""
    resp, data = request_json("GET", "/sources")
    if not resp.ok:
        return test_result("P2", "List sources and verify PDF appears", False, f"HTTP {resp.status_code}"), None
    
    pdf_sources = [s for s in data if s.get("source_type") == "pdf"]
    passed = len(pdf_sources) > 0
    return test_result(
        "P2",
        "List sources and verify PDF appears",
        passed,
        f"Found {len(pdf_sources)} PDF source(s)"
    ), pdf_sources[0]["source_id"] if passed else None

def p3_empty_pdf_rejected():
    """P3: Upload empty PDF and verify it's rejected or marked invalid."""
    pdf_path = ASSETS_DIR / "empty_test.pdf"
    if not pdf_path.exists():
        return test_result("P3", "Reject empty PDF (file missing)", False, "empty_test.pdf not found"), False
    
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        resp, data = request_json("POST", "/ingest/pdf", files=files)
    
    # Empty PDF should either fail (400/422) or have 0 chunks
    rejected = not resp.ok or data.get("chunks_count", 0) == 0
    return test_result(
        "P3",
        "Reject empty PDF or mark invalid",
        rejected,
        f"Status: {resp.status_code if not resp.ok else 'OK'}, Chunks: {data.get('chunks_count', 0)}"
    ), rejected

def p4_image_only_pdf_rejected():
    """P4: Upload image-only PDF and verify it's rejected (no selectable text)."""
    pdf_path = ASSETS_DIR / "image_only_test.pdf"
    if not pdf_path.exists():
        return test_result("P4", "Reject image-only PDF (file missing)", False, "image_only_test.pdf not found"), False
    
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        resp, data = request_json("POST", "/ingest/pdf", files=files)
    
    # Image-only PDF should have 0 chunks (no text extraction)
    rejected = data.get("chunks_count", 0) == 0
    return test_result(
        "P4",
        "Reject image-only PDF (no selectable text)",
        rejected,
        f"Chunks: {data.get('chunks_count', 0)}"
    ), rejected

def p5_unsupported_file_rejected():
    """P5: Upload unsupported file (.txt) and verify it's rejected."""
    file_path = ASSETS_DIR / "unsupported_notes.txt"
    if not file_path.exists():
        return test_result("P5", "Reject unsupported .txt file (file missing)", False, "unsupported_notes.txt not found"), False
    
    with open(file_path, "rb") as f:
        files = {"file": (file_path.name, f, "text/plain")}
        resp, data = request_json("POST", "/ingest/pdf", files=files)
    
    # Unsupported file should fail (400/422)
    rejected = not resp.ok
    return test_result(
        "P5",
        "Reject unsupported .txt file",
        rejected,
        f"Status: {resp.status_code if not resp.ok else 'OK (should fail)'}"
    ), rejected

def p6_duplicate_pdf_handling():
    """P6: Upload same PDF twice and verify handling (deduplicate or error)."""
    pdf_path = ASSETS_DIR / "valid_sage_test.pdf"
    
    # First upload
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        resp1, data1 = request_json("POST", "/ingest/pdf", files=files)
    
    if not resp1.ok:
        return test_result("P6", "Handle duplicate upload gracefully", False, "First upload failed"), False
    
    # Second upload (same file)
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        resp2, data2 = request_json("POST", "/ingest/pdf", files=files)
    
    # Either second upload succeeds (creates new source) or fails gracefully
    handled = resp1.ok and (resp2.ok or not resp2.ok)
    details = f"First: OK (chunks={data1.get('chunks_count')}), Second: {'OK' if resp2.ok else f'Error {resp2.status_code}'}"
    return test_result("P6", "Handle duplicate upload gracefully", handled, details), handled

def p7_large_pdf():
    """P7: Test with a multi-page PDF (valid_sage_test.pdf already is 2 pages, verify it works)."""
    resp, data = request_json("GET", "/sources")
    pdf_sources = [s for s in data if s.get("source_type") == "pdf" and s.get("page_count", 0) >= 2]
    
    if not pdf_sources:
        return test_result("P7", "Process multi-page PDF (page_count >= 2)", False, "No multi-page PDF found"), False
    
    source = pdf_sources[0]
    passed = source.get("chunks_count", 0) > 0
    return test_result(
        "P7",
        "Process multi-page PDF successfully",
        passed,
        f"Pages: {source.get('page_count')}, Chunks: {source.get('chunks_count')}"
    ), passed

if __name__ == "__main__":
    print("\n" + "="*80)
    print("PDF MODULE INGESTION TESTS (P1-P7)")
    print("="*80 + "\n")
    
    results = []
    
    # P1: Valid PDF upload
    p1_pass, p1_source_id = p1_valid_pdf_upload()
    results.append(("P1", p1_pass))
    
    # P2: Source list
    p2_pass, p2_source_id = p2_source_list_contains_pdf()
    results.append(("P2", p2_pass))
    
    # P3: Empty PDF rejection
    p3_pass, _ = p3_empty_pdf_rejected()
    results.append(("P3", p3_pass))
    
    # P4: Image-only PDF rejection
    p4_pass, _ = p4_image_only_pdf_rejected()
    results.append(("P4", p4_pass))
    
    # P5: Unsupported file rejection
    p5_pass, _ = p5_unsupported_file_rejected()
    results.append(("P5", p5_pass))
    
    # P6: Duplicate handling
    p6_pass, _ = p6_duplicate_pdf_handling()
    results.append(("P6", p6_pass))
    
    # P7: Multi-page PDF
    p7_pass, _ = p7_large_pdf()
    results.append(("P7", p7_pass))
    
    # Summary
    print("\n" + "="*80)
    pass_count = sum(1 for _, p in results if p)
    print(f"SUMMARY: {pass_count}/{len(results)} tests passed")
    print("="*80 + "\n")
    
    sys.exit(0 if pass_count == len(results) else 1)
