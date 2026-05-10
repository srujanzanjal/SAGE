#!/usr/bin/env python
"""Upload valid PDF and re-run QA tests."""
import os
import requests
import json
import time
from pathlib import Path

API_BASE = "http://127.0.0.1:8000/api/v1"
PDF_PATH = Path(__file__).parent / "tests/assets/pdf_module/valid_sage_test.pdf"

def upload_pdf(pdf_path):
    """Upload PDF."""
    with open(pdf_path, "rb") as f:
        files = {"file": (os.path.basename(pdf_path), f, "application/pdf")}
        response = requests.post(f"{API_BASE}/ingest/pdf", files=files, timeout=60)
        if response.ok:
            data = response.json()
            print(f"✓ Uploaded: {data.get('title')} (chunks: {data.get('chunks_count')}, pages: {data.get('page_count')})")
            print(f"  Source ID: {data.get('source_id')}")
            return data
        else:
            print(f"✗ Upload failed: {response.status_code} {response.text}")
            return None

if __name__ == "__main__":
    print(f"Uploading {PDF_PATH.name}...")
    result = upload_pdf(str(PDF_PATH))
    if result:
        print("\nNow run: python test_pdf_module.py")
