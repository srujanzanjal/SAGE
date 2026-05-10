#!/usr/bin/env python3
"""
SAGE GitHub Module - QA, Mode, & Citation Tests (Fast Version)
Runs 15 QA questions + 3 mode tests + 5 citation tests sequentially
"""

import json
import requests
import time
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"
SOURCE_ID = "8caa6131-9cd6-4bec-8f52-7efc84b07655"

class Results:
    def __init__(self):
        self.tests = []
    
    def add(self, test_id, question, status, conf, cits, notes=""):
        self.tests.append({"id": test_id, "status": status, "conf": conf, "cits": cits, "notes": notes})
        conf_str = f"{conf:.2f}" if isinstance(conf, float) else "N/A"
        print(f"  [{test_id:2}] {status:7} Conf: {conf_str:5} Cits: {cits:1}  {notes[:40] if notes else ''}")

def ask(session, q, mode="grounded"):
    """Quick QA request"""
    try:
        started = time.perf_counter()
        r = session.post(
            f"{BASE_URL}/api/v1/qa/ask",
            json={"question": q, "source_id": SOURCE_ID, "mode": mode},
            timeout=60
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        if r.status_code == 200:
            payload = r.json()
            payload["elapsed_ms"] = elapsed_ms
            return payload
        return {"error": f"HTTP {r.status_code}", "elapsed_ms": elapsed_ms}
    except Exception as e:
        elapsed_ms = 0.0
        print(f"    ERROR: {str(e)[:50]}")
        return {"error": str(e), "elapsed_ms": elapsed_ms}

# Category C: 15 GitHub QA Questions
print("\n" + "="*70)
print("CATEGORY C: GITHUB QA QUESTIONS (15 Questions in Grounded Mode)")
print("="*70)

res_c = Results()
session = requests.Session()

questions = [
    ("C1", "What does this repository do?"),
    ("C2", "Explain the overall architecture of this repository."),
    ("C3", "Where is the main application entry point?"),
    ("C4", "Which files define the API routes or controllers?"),
    ("C5", "Which files define database models or schemas?"),
    ("C6", "What dependencies does this project use?"),
    ("C7", "How can I run this project locally?"),
    ("C8", "Does this project use clean architecture or repository pattern? Explain."),
    ("C9", "What are the important files I should read first?"),
    ("C10", "Are there tests in this repository? If yes, where?"),
    ("C11", "Find any configuration files and explain their purpose."),
    ("C12", "What database or persistence layer is used?"),
    ("C13", "Does the repository have Docker support?"),
    ("C14", "What are possible limitations or missing features?"),
    ("C15", "Summarize this repository for a beginner."),
]

for index, (test_id, q) in enumerate(questions, start=1):
    resp = ask(session, q, "grounded")
    if resp:
        conf = resp.get("confidence_score", 0.0)
        cits = len(resp.get("citations", []))
        elapsed_ms = resp.get("elapsed_ms", 0.0)
        
        # Determine status
        if conf > 0.3 and cits > 0:
            status = "PASS"
        elif conf > 0.15 or cits > 0:
            status = "PARTIAL"
        else:
            status = "FAIL"
        
        notes = f"{cits} cit, {elapsed_ms:.0f}ms" if cits > 0 else f"no cite, {elapsed_ms:.0f}ms"
        res_c.add(test_id, q, status, conf, cits, notes)
    else:
        res_c.add(test_id, q, "FAIL", 0.0, 0, "request failed")
    if index < len(questions):
        time.sleep(1)

c_pass = len([t for t in res_c.tests if t["status"] == "PASS"])
c_partial = len([t for t in res_c.tests if t["status"] == "PARTIAL"])
c_fail = len([t for t in res_c.tests if t["status"] == "FAIL"])
print(f"\nC Summary: {c_pass}/15 PASS, {c_partial} PARTIAL, {c_fail} FAIL")

# Category D: Mode Behavior
print("\n" + "="*70)
print("CATEGORY D: MODE BEHAVIOR TESTS")
print("="*70)

res_d = Results()

# D1: Irrelevant question
print("\n  [D1] Irrelevant question in grounded mode")
resp_d1 = ask(session, "What is the capital of Japan?", "grounded")
if resp_d1:
    conf_d1 = resp_d1.get("confidence_score", 0.0)
    cits_d1 = len(resp_d1.get("citations", []))
    if conf_d1 < 0.3:
        res_d.add("D1", "Irrelevant Q", "PASS", conf_d1, cits_d1, "low conf")
    else:
        res_d.add("D1", "Irrelevant Q", "FAIL", conf_d1, cits_d1, "too high")
else:
    res_d.add("D1", "Irrelevant Q", "FAIL", 0.0, 0, "failed")

# D2: Question rephrasing
print("\n  [D2] Question rephrasing consistency")
resp_d2a = ask(session, "Where is the main app defined?", "grounded")
resp_d2b = ask(session, "Which file starts the API server?", "grounded")
if resp_d2a and resp_d2b:
    conf_d2a = resp_d2a.get("confidence_score", 0.0)
    conf_d2b = resp_d2b.get("confidence_score", 0.0)
    cits_d2a = len(resp_d2a.get("citations", []))
    cits_d2b = len(resp_d2b.get("citations", []))
    
    conf_diff = abs(conf_d2a - conf_d2b)
    if conf_diff < 0.2:
        res_d.add("D2", "Rephrasing", "PASS", conf_d2a, cits_d2a, f"diff: {conf_diff:.2f}")
    else:
        res_d.add("D2", "Rephrasing", "PARTIAL", conf_d2a, cits_d2a, f"diff: {conf_diff:.2f}")
else:
    res_d.add("D2", "Rephrasing", "FAIL", 0.0, 0, "one failed")

# D3: Vague question
print("\n  [D3] Vague question")
resp_d3 = ask(session, "setup?", "grounded")
if resp_d3:
    conf_d3 = resp_d3.get("confidence_score", 0.0)
    cits_d3 = len(resp_d3.get("citations", []))
    if cits_d3 > 0 or conf_d3 > 0.15:
        res_d.add("D3", "Vague Q", "PASS", conf_d3, cits_d3, "found setup")
    else:
        res_d.add("D3", "Vague Q", "PARTIAL", conf_d3, cits_d3, "query rewrite OK")
else:
    res_d.add("D3", "Vague Q", "FAIL", 0.0, 0, "failed")

d_pass = len([t for t in res_d.tests if t["status"] == "PASS"])
d_partial = len([t for t in res_d.tests if t["status"] == "PARTIAL"])
d_fail = len([t for t in res_d.tests if t["status"] == "FAIL"])
print(f"\nD Summary: {d_pass}/3 PASS, {d_partial} PARTIAL, {d_fail} FAIL")

# Category E: Citation Accuracy
print("\n" + "="*70)
print("CATEGORY E: CITATION ACCURACY TESTS (5 Answers)")
print("="*70)

res_e = Results()

citation_qs = [
    ("E1", "What is the project structure?"),
    ("E2", "List the main modules or directories"),
    ("E3", "What files are in the root directory?"),
    ("E4", "How are API routes configured?"),
    ("E5", "What is in the requirements file?"),
]

for index, (test_id, q) in enumerate(citation_qs, start=1):
    resp = ask(session, q, "grounded")
    if resp:
        citations = resp.get("citations", [])
        conf = resp.get("confidence_score", 0.0)
        cits_count = len(citations)
        
        # Check citation structure
        all_valid = True
        for cit in citations:
            if not all([cit.get("file_path"), cit.get("start_line"), cit.get("end_line"), cit.get("snippet")]):
                all_valid = False
                break
        
        if all_valid and cits_count > 0 and conf > 0.2:
            status = "PASS"
            notes = f"{cits_count} valid cit"
        elif all_valid and cits_count > 0:
            status = "PARTIAL"
            notes = f"{cits_count} cit, low conf"
        else:
            status = "FAIL"
            notes = f"{cits_count} invalid"
        
        res_e.add(test_id, q, status, conf, cits_count, notes)
    else:
        res_e.add(test_id, q, "FAIL", 0.0, 0, "failed")
    if index < len(citation_qs):
        time.sleep(1)

e_pass = len([t for t in res_e.tests if t["status"] == "PASS"])
e_partial = len([t for t in res_e.tests if t["status"] == "PARTIAL"])
e_fail = len([t for t in res_e.tests if t["status"] == "FAIL"])
print(f"\nE Summary: {e_pass}/5 PASS, {e_partial} PARTIAL, {e_fail} FAIL")

# Final summary
print("\n" + "="*70)
print("OVERALL SUMMARY")
print("="*70)
total_pass = c_pass + d_pass + e_pass
total_partial = c_partial + d_partial + e_partial
total_fail = c_fail + d_fail + e_fail
total = total_pass + total_partial + total_fail

print(f"\nCategory C (QA): {c_pass}/15 PASS, {c_partial} PARTIAL, {c_fail} FAIL")
print(f"Category D (Mode): {d_pass}/3 PASS, {d_partial} PARTIAL, {d_fail} FAIL")
print(f"Category E (Citations): {e_pass}/5 PASS, {e_partial} PARTIAL, {e_fail} FAIL")
print(f"\nTOTAL: {total_pass}/{total} PASS ({total_partial} PARTIAL, {total_fail} FAIL)")
print(f"Pass Rate: {100*total_pass/total:.1f}%\n")

session.close()
