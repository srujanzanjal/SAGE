#!/usr/bin/env python3
"""
SAGE Website Module QA runner.

- Auto-detects the latest ready website source, preferring python.org/about.
- Supports override via WEBSITE_SOURCE_ID.
- Runs website-only QA questions in grounded/exploratory mode.
- Prints source metadata, confidence, citations, retrieved source count, and response time.
- Re-ingests python.org/about only if no ready website source exists.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

BASE_URL = os.environ.get("SAGE_BASE_URL", "http://127.0.0.1:8000")
TEST_URL = "https://www.python.org/about/"
TEST_MAX_PAGES = 3
TEST_MAX_DEPTH = 1
REQUEST_TIMEOUT = 60
SLEEP_BETWEEN_QUESTIONS = 1

QUESTIONS: list[tuple[str, str, str]] = [
    ("WQ1", "What is Python?", "grounded"),
    ("WQ2", "Who maintains Python?", "grounded"),
    ("WQ3", "What are the main uses of Python?", "grounded"),
    ("WQ4", "Summarize this website page.", "grounded"),
    ("WQ5", "contact?", "grounded"),
    ("WQ6", "fees?", "grounded"),
    ("WQ7", "What is the capital of Japan?", "grounded"),
    ("WQ8", "Explain Python for a beginner.", "exploratory"),
    ("WQ9", "What does the Python website say about Python being easy to learn?", "grounded"),
    ("WQ10", "What programming language is this website about?", "grounded"),
]


@dataclass
class SelectedSource:
    source_id: str
    knowledgebase_id: str
    title: str
    canonical_ref: str
    original_ref: str
    chunks_count: int
    crawled_pages: int | None
    status: str
    created_at: str | None
    updated_at: str | None
    source_type: str


class TestResults:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.severe_failure = False

    def add(self, row: dict[str, Any]) -> None:
        self.rows.append(row)

    def counts(self) -> tuple[int, int, int]:
        pass_count = sum(1 for row in self.rows if row["status"] == "PASS")
        partial_count = sum(1 for row in self.rows if row["status"] == "PARTIAL")
        fail_count = sum(1 for row in self.rows if row["status"] == "FAIL")
        return pass_count, partial_count, fail_count


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def request_json(session: requests.Session, method: str, path: str, **kwargs) -> tuple[int, Any, float]:
    url = f"{BASE_URL}{path}"
    started = time.perf_counter()
    response = session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
    elapsed_ms = (time.perf_counter() - started) * 1000
    try:
        payload = response.json()
    except Exception:
        payload = response.text
    return response.status_code, payload, elapsed_ms


def pick_latest_website_source(sources: list[dict[str, Any]], preferred_url: str = TEST_URL) -> SelectedSource | None:
    website_sources = [
        source for source in sources
        if source.get("source_type") == "website" and source.get("status") == "ready" and (source.get("chunks_count") or 0) > 0
    ]
    if not website_sources:
        return None

    preferred = [
        source for source in website_sources
        if preferred_url.rstrip("/") in (source.get("canonical_ref") or "").rstrip("/")
        or preferred_url.rstrip("/") in (source.get("original_ref") or "").rstrip("/")
    ]
    pool = preferred or website_sources
    pool.sort(key=lambda source: (
        parse_timestamp(source.get("updated_at") or source.get("created_at")),
        source.get("chunks_count") or 0,
    ), reverse=True)
    source = pool[0]
    return SelectedSource(
        source_id=source["source_id"],
        knowledgebase_id=source["knowledgebase_id"],
        title=source.get("title") or source.get("original_ref") or source.get("canonical_ref") or "Untitled website",
        canonical_ref=source.get("canonical_ref") or "",
        original_ref=source.get("original_ref") or "",
        chunks_count=int(source.get("chunks_count") or 0),
        crawled_pages=source.get("crawled_pages"),
        status=source.get("status") or "unknown",
        created_at=source.get("created_at"),
        updated_at=source.get("updated_at"),
        source_type=source.get("source_type") or "website",
    )


def ingest_website(session: requests.Session) -> SelectedSource:
    print("No ready website source found. Ingesting python.org/about...")
    status_code, payload, elapsed_ms = request_json(
        session,
        "POST",
        "/api/v1/ingest/website",
        json={"url": TEST_URL, "max_pages": TEST_MAX_PAGES, "max_depth": TEST_MAX_DEPTH},
    )
    print(f"Ingest response: HTTP {status_code} in {elapsed_ms:.0f}ms")
    if status_code != 200:
        raise RuntimeError(f"Website ingest failed: {payload}")

    sources_created = payload.get("sources_created") or []
    if not sources_created:
        raise RuntimeError("Website ingest succeeded but no sources_created were returned.")

    source = sources_created[0]
    return SelectedSource(
        source_id=source["source_id"],
        knowledgebase_id=source["knowledgebase_id"],
        title=source.get("title") or "Untitled website",
        canonical_ref=source.get("canonical_ref") or TEST_URL,
        original_ref=TEST_URL,
        chunks_count=int(source.get("chunks_count") or 0),
        crawled_pages=source.get("crawled_pages"),
        status=source.get("status") or "ready",
        created_at=now_iso(),
        updated_at=now_iso(),
        source_type=source.get("source_type") or "website",
    )


def print_selected_source(source: SelectedSource) -> None:
    print("\n" + "=" * 80)
    print("SELECTED WEBSITE SOURCE")
    print("=" * 80)
    print(f"source_id: {source.source_id}")
    print(f"knowledgebase_id: {source.knowledgebase_id}")
    print(f"title: {source.title}")
    print(f"canonical_ref: {source.canonical_ref}")
    print(f"original_ref: {source.original_ref}")
    print(f"chunks_count: {source.chunks_count}")
    print(f"crawled_pages: {source.crawled_pages}")
    print(f"status: {source.status}")
    print("=" * 80)


def classify_status(question_id: str, question: str, mode: str, payload: dict[str, Any]) -> str:
    confidence = float(payload.get("confidence_score") or 0.0)
    citations = payload.get("citations") or []
    retrieved_count = int(payload.get("retrieved_source_count") or 0)
    answer = (payload.get("answer") or "").lower()

    if question_id in {"WQ7"}:
        if confidence < 0.35 and retrieved_count == 0:
            return "PASS"
        if confidence < 0.5 and retrieved_count <= 1:
            return "PARTIAL"
        return "FAIL"

    if question_id in {"WQ5", "WQ6"}:
        if confidence < 0.4 and retrieved_count <= 1 and not any(term in answer for term in ("fees", "contact")):
            return "PASS"
        if confidence < 0.6:
            return "PARTIAL"
        return "FAIL"

    if confidence > 0.0 and len(citations) > 0 and retrieved_count > 0:
        return "PASS"
    if confidence > 0.0 or len(citations) > 0 or retrieved_count > 0:
        return "PARTIAL"
    return "FAIL"


def run_qa_tests(session: requests.Session, source: SelectedSource) -> TestResults:
    results = TestResults()
    for index, (question_id, question, mode) in enumerate(QUESTIONS, start=1):
        started = time.perf_counter()
        status_code, payload, elapsed_ms = request_json(
            session,
            "POST",
            "/api/v1/qa/ask",
            json={
                "question": question,
                "mode": mode,
                "source_id": source.source_id,
            },
        )
        response_time_ms = (time.perf_counter() - started) * 1000

        if status_code != 200 or not isinstance(payload, dict):
            results.add({
                "id": question_id,
                "question": question,
                "mode": mode,
                "confidence": 0.0,
                "citations": 0,
                "retrieved_sources": 0,
                "response_time_ms": response_time_ms,
                "status": "FAIL",
                "notes": f"HTTP {status_code}",
                "payload": payload,
            })
        else:
            confidence = float(payload.get("confidence_score") or 0.0)
            citations = payload.get("citations") or []
            retrieved_count = int(payload.get("retrieved_source_count") or 0)
            result_status = classify_status(question_id, question, mode, payload)
            notes = payload.get("confidence_reason") or payload.get("warnings", [""])[0] or ""
            results.add({
                "id": question_id,
                "question": question,
                "mode": mode,
                "confidence": confidence,
                "citations": len(citations),
                "retrieved_sources": retrieved_count,
                "response_time_ms": response_time_ms,
                "status": result_status,
                "notes": notes,
                "payload": payload,
            })

        row = results.rows[-1]
        conf_str = f"{row['confidence']:.2f}"
        print(
            f"[{row['id']}] {row['status']:<7} Conf: {conf_str:<5} "
            f"Cits: {row['citations']:<2} Retrieved: {row['retrieved_sources']:<2} "
            f"Time: {row['response_time_ms']:.0f}ms | {row['notes']}"
        )
        if row["citations"] and isinstance(row.get("payload"), dict):
            for citation in (row["payload"].get("citations") or [])[:2]:
                source_ref = citation.get("source_ref") or citation.get("file_url") or ""
                snippet = (citation.get("snippet") or "").replace("\n", " ")[:120]
                print(f"     - {citation.get('citation_id')} | {source_ref} | score={citation.get('score')} | {snippet}")

        if index < len(QUESTIONS):
            time.sleep(SLEEP_BETWEEN_QUESTIONS)

    return results


def main() -> int:
    session = requests.Session()
    try:
        health_status, health_payload, _ = request_json(session, "GET", "/health")
        if health_status != 200 or not isinstance(health_payload, dict) or health_payload.get("status") != "ok":
            raise RuntimeError(f"Backend health check failed: {health_payload}")

        override_source_id = os.environ.get("WEBSITE_SOURCE_ID", "").strip()
        if override_source_id:
            source_status, source_payload, _ = request_json(session, "GET", f"/api/v1/sources/{override_source_id}")
            if source_status != 200 or not isinstance(source_payload, dict):
                raise RuntimeError(f"WEBSITE_SOURCE_ID not found: {override_source_id}")
            source = SelectedSource(
                source_id=source_payload["source_id"],
                knowledgebase_id=source_payload["knowledgebase_id"],
                title=source_payload.get("title") or source_payload.get("original_ref") or "Untitled website",
                canonical_ref=source_payload.get("canonical_ref") or "",
                original_ref=source_payload.get("original_ref") or "",
                chunks_count=int(source_payload.get("chunks_count") or 0),
                crawled_pages=source_payload.get("crawled_pages"),
                status=source_payload.get("status") or "unknown",
                created_at=source_payload.get("created_at"),
                updated_at=source_payload.get("updated_at"),
                source_type=source_payload.get("source_type") or "website",
            )
        else:
            sources_status, sources_payload, _ = request_json(session, "GET", "/api/v1/sources")
            if sources_status != 200 or not isinstance(sources_payload, list):
                raise RuntimeError(f"Could not list sources: {sources_payload}")
            source = pick_latest_website_source(sources_payload)
            if source is None:
                source = ingest_website(session)

        if source.status != "ready" or source.chunks_count <= 0:
            raise RuntimeError(f"Selected website source is not ready for QA: {source}")

        print_selected_source(source)
        results = run_qa_tests(session, source)
        pass_count, partial_count, fail_count = results.counts()
        total = pass_count + partial_count + fail_count
        print("\n" + "=" * 80)
        print("WEBSITE QA SUMMARY")
        print("=" * 80)
        print(f"Pass: {pass_count}")
        print(f"Partial: {partial_count}")
        print(f"Fail: {fail_count}")
        print(f"Total: {total}")
        print(f"Pass rate: {pass_count / total * 100:.1f}%")

        # Severe failures only: backend unavailable or no usable source selected.
        return 0
    except Exception as exc:
        print(f"SEVERE FAILURE: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
