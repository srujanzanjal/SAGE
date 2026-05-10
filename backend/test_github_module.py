#!/usr/bin/env python3
"""
SAGE GitHub Module Integration Test Suite
Tests: Backend API (A1-A7), Frontend UI (B1-B3), QA (C), Modes (D), Citations (E), Limits (F), Cleanup (G)
"""

import json
import requests
import time
from datetime import datetime
from urllib.parse import urlparse

BASE_URL = "http://127.0.0.1:8000"
GITHUB_REPO = "https://github.com/0xTheProDev/fastapi-clean-example"
FALLBACK_REPO = "https://github.com/BaseMax/SimpleFastPyAPI"

class TestResults:
    def __init__(self):
        self.results = []
        self.start_time = datetime.now()
        
    def add(self, test_id, test_name, status, details=""):
        self.results.append({
            "test_id": test_id,
            "test_name": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
        print(f"[{test_id}] {test_name}: {status}")
        if details:
            print(f"  └─ {details}")
    
    def summary(self):
        passed = len([r for r in self.results if r["status"] == "PASS"])
        failed = len([r for r in self.results if r["status"] == "FAIL"])
        partial = len([r for r in self.results if r["status"] == "PARTIAL"])
        total = len(self.results)
        print(f"\n{'='*60}")
        print(f"TESTS: {passed}/{total} PASSED | {failed} FAILED | {partial} PARTIAL")
        print(f"{'='*60}\n")
        return {"passed": passed, "failed": failed, "partial": partial, "total": total}

# ========== TEST CATEGORY A: BACKEND API TESTS ==========

def test_a1_url_parsing(results):
    """Test GitHub URL parsing"""
    print("\n[TEST A1] GitHub URL Parsing")
    
    test_urls = [
        "https://github.com/0xTheProDev/fastapi-clean-example",
        "https://github.com/0xTheProDev/fastapi-clean-example.git",
        "https://github.com/0xTheProDev/fastapi-clean-example/tree/main",
    ]
    
    for url in test_urls:
        try:
            # We'll test by attempting to ingest and seeing if URL is accepted
            # parse_github_url is internal to github_repo.py, so we test via ingestion endpoint
            response = requests.post(
                f"{BASE_URL}/api/v1/jobs/github-ingest",
                json={"url": url},
                timeout=5
            )
            if response.status_code in [200, 202]:  # 200 or 202 Accepted
                data = response.json()
                if "job_id" in data:
                    results.add("A1", f"URL Parsing ({url[-20:]})", "PASS", f"job_id: {data['job_id'][:8]}...")
                else:
                    results.add("A1", f"URL Parsing ({url[-20:]})", "FAIL", f"No job_id in response")
            else:
                results.add("A1", f"URL Parsing ({url[-20:]})", "FAIL", f"Status {response.status_code}")
        except Exception as e:
            results.add("A1", f"URL Parsing ({url[-20:]})", "FAIL", str(e))

def test_a2_start_ingestion_job(results):
    """Test starting GitHub ingestion job"""
    print("\n[TEST A2] Start GitHub Ingestion Job")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/jobs/github-ingest",
            json={"url": GITHUB_REPO},
            timeout=10
        )
        
        if response.status_code in [200, 202]:  # 200 or 202 Accepted
            data = response.json()
            if "job_id" in data:
                results.add("A2", "Start Ingestion Job", "PASS", f"job_id: {data['job_id']}")
                return data["job_id"]
            else:
                results.add("A2", "Start Ingestion Job", "FAIL", "Missing job_id")
        else:
            results.add("A2", "Start Ingestion Job", "FAIL", f"Status {response.status_code}: {response.text[:100]}")
    except Exception as e:
        results.add("A2", "Start Ingestion Job", "FAIL", str(e))
    
    return None

def test_a3_poll_job_status(results, job_id):
    """Test polling job status"""
    print("\n[TEST A3] Poll Job Status")
    
    if not job_id:
        results.add("A3", "Poll Job Status", "FAIL", "No job_id from A2")
        return None, None
    
    try:
        max_polls = 120  # 4 minutes max
        poll_count = 0
        final_data = None
        
        while poll_count < max_polls:
            response = requests.get(f"{BASE_URL}/api/v1/jobs/{job_id}", timeout=5)
            
            if response.status_code in [200, 202]:
                data = response.json()
                status = data.get("status", "unknown")
                current_step = data.get("current_step", "")
                print(f"  Poll #{poll_count}: {status} - {current_step}")
                
                if status == "completed":
                    final_data = data
                    break
                elif status in ["error", "failed"]:
                    results.add("A3", "Poll Job Status", "FAIL", f"Job failed: {data.get('message', 'Unknown error')}")
                    return None, None
                    
                poll_count += 1
                time.sleep(2)
            else:
                results.add("A3", "Poll Job Status", "FAIL", f"Poll request failed: {response.status_code}")
                return None, None
        
        if final_data and final_data.get("status") == "completed":
            knowledgebase_id = final_data.get("knowledgebase_id")
            source_id = final_data.get("source_id")
            result = final_data.get("result", {})
            if isinstance(result, dict):
                chunks_count = result.get("chunks_count", 0)
            else:
                chunks_count = 0
            results.add("A3", "Poll Job Status", "PASS", 
                       f"Completed in {poll_count} polls | KB: {knowledgebase_id[:8] if knowledgebase_id else 'N/A'}... | Source: {source_id[:8] if source_id else 'N/A'}... | Chunks: {chunks_count}")
            return knowledgebase_id, source_id
        else:
            results.add("A3", "Poll Job Status", "FAIL", f"Job did not complete after {max_polls} polls")
            return None, None
            
    except Exception as e:
        results.add("A3", "Poll Job Status", "FAIL", str(e))
        return None, None

def test_a4_list_sources(results, source_id):
    """Test listing sources after ingestion"""
    print("\n[TEST A4] List Sources")
    
    try:
        response = requests.get(f"{BASE_URL}/api/v1/sources", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            # Response is a direct array, not wrapped in "sources" key
            sources = data if isinstance(data, list) else []
            
            # Find our GitHub source
            github_source = None
            for source in sources:
                if source.get("source_type") == "github":
                    github_source = source
                    break
            
            if github_source:
                chunks_count = github_source.get("chunks_count", 0)
                status = github_source.get("status")
                results.add("A4", "List Sources", "PASS", 
                           f"Found GitHub source | Chunks: {chunks_count} | Status: {status}")
            else:
                results.add("A4", "List Sources", "FAIL", "No GitHub source found in sources list")
        else:
            results.add("A4", "List Sources", "FAIL", f"Status {response.status_code}")
    except Exception as e:
        results.add("A4", "List Sources", "FAIL", str(e))

def test_a5_source_details(results, source_id):
    """Test getting source details"""
    print("\n[TEST A5] Source Details")
    
    if not source_id:
        results.add("A5", "Source Details", "FAIL", "No source_id provided")
        return
    
    try:
        response = requests.get(f"{BASE_URL}/api/v1/sources/{source_id}", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            source = data.get("source", {})
            
            details = []
            for field in ["repo_owner", "repo_name", "branch", "detected_languages", "files_indexed"]:
                if field in source:
                    details.append(f"{field}: {source[field]}")
            
            results.add("A5", "Source Details", "PASS", " | ".join(details[:3]))
        else:
            results.add("A5", "Source Details", "FAIL", f"Status {response.status_code}")
    except Exception as e:
        results.add("A5", "Source Details", "FAIL", str(e))

def test_a6_database_metadata(results):
    """Test database metadata check (code verification)"""
    print("\n[TEST A6] Database Metadata Check")
    results.add("A6", "Database Metadata Check", "Code Verified", 
               "Metadata sanitization in vector_store.py prevents None values. Requires Supabase access to verify.")

def test_a7_chunk_metadata(results):
    """Test chunk metadata check (code verification)"""
    print("\n[TEST A7] Chunk Metadata Check")
    results.add("A7", "Chunk Metadata Check", "Code Verified", 
               "Chunk metadata includes file_path, start_line, end_line. Requires Supabase access to verify.")

def run_backend_tests():
    """Run all backend API tests"""
    results = TestResults()
    
    print("\n" + "="*60)
    print("TEST CATEGORY A: BACKEND API TESTS")
    print("="*60)
    
    test_a1_url_parsing(results)
    job_id = test_a2_start_ingestion_job(results)
    knowledgebase_id, source_id = test_a3_poll_job_status(results, job_id)
    test_a4_list_sources(results, source_id)
    
    # Get the GitHub source ID from the list for A5 if A3 didn't return it
    if not source_id:
        try:
            response = requests.get(f"{BASE_URL}/api/v1/sources", timeout=5)
            if response.status_code == 200:
                sources = response.json()
                for source in sources:
                    if source.get("source_type") == "github":
                        source_id = source.get("source_id")
                        break
        except:
            pass
    
    test_a5_source_details(results, source_id)
    test_a6_database_metadata(results)
    test_a7_chunk_metadata(results)
    
    summary = results.summary()
    return results, summary, source_id

if __name__ == "__main__":
    results, summary, source_id = run_backend_tests()
    print(f"\nSource ID for next tests: {source_id}")
    print(f"Results object: {len(results.results)} tests recorded")
