#!/usr/bin/env python3
"""Validate citation fields for a set of QA questions against a video source."""
import os
import requests
import time
import json

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000/api/v1")
SOURCE_ID = os.getenv("VIDEO_SOURCE_ID", None)
TIMEOUT = 90

session = requests.Session()

questions = [
    ("VQ2", "Summarize the main points of the video."),
    ("VQ3", "What does the speaker explain in the beginning?"),
    ("VQ4", "List three important ideas from the video."),
    ("VQ5", "What conclusion or final message does the speaker give?"),
    ("VQ10", "Give me a study-note style summary from this video."),
]

def call_qa(q, source_id):
    payload = {"question": q, "source_id": source_id, "mode": "grounded", "top_k": 6}
    resp = session.post(f"{API_BASE}/qa/ask", json=payload, timeout=TIMEOUT)
    if not resp.ok:
        return None, resp.status_code, resp.text
    return resp.json(), resp.status_code, None

def validate_citation(c):
    # Check timestamp_label, start_time/end_time numeric, snippet non-empty, score numeric, chunk_index present
    ok_ts = bool(c.get('timestamp_label'))
    ok_start = isinstance(c.get('start_time'), (int, float))
    ok_end = isinstance(c.get('end_time'), (int, float))
    ok_snip = bool(c.get('snippet'))
    ok_score = isinstance(c.get('score'), (int, float))
    ok_chunk = c.get('chunk_index') is not None
    return ok_ts and ok_start and ok_end and ok_snip and ok_score and ok_chunk, {
        'timestamp_label': ok_ts,
        'start_time': ok_start,
        'end_time': ok_end,
        'snippet': ok_snip,
        'score': ok_score,
        'chunk_index': ok_chunk
    }

def main():
    source_id = SOURCE_ID
    if not source_id:
        try:
            sources = session.get(f"{API_BASE}/sources", timeout=TIMEOUT).json()
            ready_videos = [s for s in sources if s.get("source_type") == "video" and s.get("status") == "ready" and s.get("chunks_count", 0) > 0]
            if ready_videos:
                source_id = ready_videos[-1].get("source_id")
        except Exception:
            source_id = None

    if not source_id:
        print("Set VIDEO_SOURCE_ID env var to a ready video source")
        return

    rows = []
    for qid, qtext in questions:
        data, status, err = call_qa(qtext, source_id)
        if err:
            rows.append((qid, 0, False, f"HTTP {status}", {}))
            time.sleep(1)
            continue

        citations = data.get('citations', [])
        cit_count = len(citations)
        valid = True
        detail = {}
        for c in citations[:5]:
            ok, d = validate_citation(c)
            detail = d
            if not ok:
                valid = False
                break

        rows.append((qid, cit_count, valid, None if valid else 'Invalid citation fields', detail))
        time.sleep(1)

    # Write markdown table
    out_md = ["| Question | Citation Count | Timestamp Valid | Snippet Valid | Link Works | Status |",
              "|---|---:|:---:|:---:|:---:|---|"]
    for r in rows:
        qid, count, ok, err, detail = r
        ts_ok = detail.get('timestamp_label', False)
        sn_ok = detail.get('snippet', False)
        # Link Works unknown here
        out_md.append(f"| {qid} | {count} | {ts_ok} | {sn_ok} | unknown | {'PASS' if ok else 'FAIL ('+str(err)+')'} |")

    with open('CITATION_VALIDATION.md', 'w') as fh:
        fh.write("\n".join(out_md))

    print("Wrote CITATION_VALIDATION.md")

if __name__ == '__main__':
    main()
