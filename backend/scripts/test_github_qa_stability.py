#!/usr/bin/env python3
"""Sequential GitHub QA stability check for demo verification."""

from __future__ import annotations

import argparse
import os
import time
from typing import Any

import requests


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_SOURCE_ID = "56667dc6-1e54-49d5-b781-768af2e53fc8"
QUESTIONS = [
    "What does this repository do?",
    "Explain the overall architecture.",
    "Where is the main application entry point?",
    "Which files define API routes or controllers?",
    "Which files define database models or schemas?",
    "What dependencies does this project use?",
    "How can I run this project locally?",
    "Does this project use repository pattern?",
    "What are the important files to read first?",
    "Does this project have Docker support?",
]


def build_payload(question: str, source_id: str | None, knowledgebase_id: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"question": question, "mode": "grounded"}
    if source_id:
        payload["source_id"] = source_id
    if knowledgebase_id:
        payload["knowledgebase_id"] = knowledgebase_id
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a sequential GitHub QA stability check.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend base URL.")
    parser.add_argument("--source-id", default=os.getenv("GITHUB_SOURCE_ID", DEFAULT_SOURCE_ID), help="GitHub source ID.")
    parser.add_argument("--knowledgebase-id", default=os.getenv("GITHUB_KNOWLEDGEBASE_ID"), help="Knowledgebase ID.")
    args = parser.parse_args()

    if not args.source_id and not args.knowledgebase_id:
        print("Provide --source-id or --knowledgebase-id.")
        return 1

    session = requests.Session()
    passes = 0
    failures = 0

    print("=" * 90)
    print("GITHUB QA STABILITY CHECK")
    print("=" * 90)

    try:
        for index, question in enumerate(QUESTIONS, start=1):
            payload = build_payload(question, args.source_id, args.knowledgebase_id)
            started = time.perf_counter()
            try:
                response = session.post(
                    f"{args.base_url}/api/v1/qa/ask",
                    json=payload,
                    timeout=60,
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                if response.status_code == 200:
                    data = response.json()
                    confidence = float(data.get("confidence_score", 0.0) or 0.0)
                    citations = data.get("citations", []) or []
                    answer = data.get("answer", "")
                    status = "PASS" if answer else "FAIL"
                    if status == "PASS":
                        passes += 1
                    else:
                        failures += 1
                    print(
                        f"[{index:02}] {status:4} {elapsed_ms:7.0f}ms  conf={confidence:.2f}  cites={len(citations):2}  {question}"
                    )
                    if status == "FAIL":
                        print(f"     error={data.get('warnings', ['No answer'])[0] if data.get('warnings') else 'No answer'}")
                else:
                    failures += 1
                    print(f"[{index:02}] FAIL {elapsed_ms:7.0f}ms  http={response.status_code}  {question}")
                    try:
                        detail = response.json().get("detail")
                        if detail:
                            print(f"     error={detail}")
                    except Exception:
                        pass
            except Exception as exc:
                failures += 1
                elapsed_ms = (time.perf_counter() - started) * 1000
                print(f"[{index:02}] FAIL {elapsed_ms:7.0f}ms  {question}")
                print(f"     error={exc}")

            if index < len(QUESTIONS):
                time.sleep(1)
    finally:
        session.close()

    total = passes + failures
    print("=" * 90)
    print(f"RESULT: {passes}/{total} passed, {failures} failed")
    print("=" * 90)
    return 0 if passes >= 8 else 2


if __name__ == "__main__":
    raise SystemExit(main())