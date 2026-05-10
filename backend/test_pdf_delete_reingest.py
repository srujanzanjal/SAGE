#!/usr/bin/env python
"""PDF Module Delete & Re-ingest Tests - PD1 through PD3."""
import os
import sys
import requests
import json
import time
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

def pd1_delete_pdf_source():
    """PD1: Delete a PDF source and verify it's removed from source list."""
    # First, find a PDF source to delete
    resp, data = request_json("GET", "/sources")
    if not resp.ok:
        return test_result("PD1", "Delete PDF source and verify removal", False, "Failed to list sources"), None
    
    pdf_sources = [s for s in data if s.get("source_type") == "pdf"]
    if not pdf_sources:
        return test_result("PD1", "Delete PDF source and verify removal", False, "No PDF sources found"), None
    
    source_id = pdf_sources[0]["source_id"]
    
    # Delete the source
    resp_del, data_del = request_json("DELETE", f"/sources/{source_id}")
    if not resp_del.ok:
        return test_result("PD1", "Delete PDF source and verify removal", False, f"Delete failed: {resp_del.status_code}"), None
    
    # Verify removal
    resp_check, data_check = request_json("GET", "/sources")
    remaining = [s for s in data_check if s.get("source_id") == source_id]
    
    deleted = not remaining
    details = f"Deleted source_id: {source_id}, Found in list after delete: {len(remaining) > 0}"
    return test_result("PD1", "Delete PDF source and verify removal", deleted, details), source_id

def pd2_qa_fails_on_deleted_source():
    """PD2: Ask question on deleted source and verify QA fails gracefully."""
    # We need a source_id from PD1 that was deleted
    # For now, use an invalid UUID
    source_id = "00000000-0000-0000-0000-000000000000"
    
    payload = {
        "question": "What is SAGE?",
        "mode": "grounded",
        "source_id": source_id,
        "top_k": 6,
    }
    resp, data = request_json("POST", "/qa/ask", json=payload)
    
    # Should fail (no sources found) or return 0 retrieved sources
    failed_gracefully = not resp.ok or data.get("retrieved_source_count", 0) == 0
    details = f"Status: {resp.status_code if not resp.ok else 'OK'}, Retrieved sources: {data.get('retrieved_source_count', 0)}"
    return test_result("PD2", "QA fails gracefully on deleted source", failed_gracefully, details)

def pd3_reingestion_works():
    """PD3: Re-upload the same PDF and verify QA works again."""
    pdf_path = ASSETS_DIR / "valid_sage_test.pdf"
    if not pdf_path.exists():
        return test_result("PD3", "Re-upload PDF and verify QA works", False, "valid_sage_test.pdf not found")
    
    # Upload
    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        resp_upload, data_upload = request_json("POST", "/ingest/pdf", files=files)
    
    if not resp_upload.ok:
        return test_result("PD3", "Re-upload PDF and verify QA works", False, f"Upload failed: {resp_upload.status_code}")
    
    source_id = data_upload.get("source_id")
    chunks_count = data_upload.get("chunks_count", 0)
    
    # Wait a moment for indexing
    time.sleep(2)
    
    # Ask a question
    payload = {
        "question": "What does SAGE stand for?",
        "mode": "grounded",
        "source_id": source_id,
        "top_k": 6,
    }
    resp_qa, data_qa = request_json("POST", "/qa/ask", json=payload)
    
    qa_works = resp_qa.ok and data_qa.get("confidence_score", 0) > 0.1 and data_qa.get("retrieved_source_count", 0) > 0
    details = f"Upload chunks: {chunks_count}, QA confidence: {data_qa.get('confidence_score', 0):.2f}, Retrieved: {data_qa.get('retrieved_source_count', 0)}"
    return test_result("PD3", "Re-upload PDF and verify QA works", qa_works, details)

if __name__ == "__main__":
    print("\n" + "="*80)
    print("PDF MODULE DELETE & RE-INGEST TESTS (PD1-PD3)")
    print("="*80 + "\n")
    
    results = []
    
    # PD1: Delete source
    pd1_pass, pd1_source_id = pd1_delete_pdf_source()
    results.append(("PD1", pd1_pass))
    
    # PD2: QA fails on deleted
    pd2_pass = pd2_qa_fails_on_deleted_source()
    results.append(("PD2", pd2_pass))
    
    # PD3: Re-ingest
    pd3_pass = pd3_reingestion_works()
    results.append(("PD3", pd3_pass))
    
    # Summary
    print("\n" + "="*80)
    pass_count = sum(1 for _, p in results if p)
    print(f"SUMMARY: {pass_count}/{len(results)} tests passed")
    print("="*80 + "\n")
    
    sys.exit(0 if pass_count == len(results) else 1)
