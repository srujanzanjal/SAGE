# SAGE — Semantic Analysis and Generation Engine

## Project Overview

SAGE is a source-grounded AI knowledge engine that converts websites, PDFs, YouTube videos, and public GitHub repositories into searchable, conversational knowledgebases. It returns grounded answers with citations, snippets, and confidence scores.

## Problem Statement

Users struggle to search and understand dispersed information across web pages, documents, videos, and repositories. Generic chatbots may hallucinate or give ungrounded answers. SAGE addresses this by retrieving relevant chunks from ingested sources, reranking evidence, and producing source-grounded responses.

## Objectives

- Ingest multiple source types (website, PDF, video, GitHub)
- Generate semantic chunks and deterministic overview chunks
- Store vectors in ChromaDB and metadata in Supabase
- Support source-grounded QA with citations and confidence scores
- Provide Grounded and Exploratory modes
- Offer a website-only Chrome side panel for quick website QA

## Features

- Website Intelligence
- PDF / Document Intelligence
- YouTube / Video Intelligence
- GitHub Repository Intelligence
- Universal Source Overview Chunks (deterministic, no LLM)
- Grounded and Exploratory modes
- Confidence scoring and source citations
- Source history, delete and re-ingest support
- Website-only Chrome side panel extension

## Tech Stack

Frontend:
- React
- Vite
- TailwindCSS

Backend:
- Python
- FastAPI

AI / NLP:
- sentence-transformers (all-MiniLM-L6-v2)
- Google Gemini API (primary LLM, free tier)
- Groq API (automatic fallback LLM, free tier)

Database & Storage:
- Supabase (Postgres metadata)
- ChromaDB (vector storage)

Extraction:
- Playwright (web pages)
- PyMuPDF (PDFs)
- youtube-transcript-api (YouTube transcripts)
- yt-dlp + faster-whisper (auto-transcription fallback)
- git clone / ZIP fallback (GitHub)

Extension:
- Chrome Manifest V3 side panel (website-only)

## Final Architecture (high-level flow)

User Input
→ Ingestion Pipeline
→ Extraction
→ Chunking
→ Source Overview Chunk Creation
→ Embeddings
→ ChromaDB Vector Storage
→ Supabase Metadata Storage
→ QA Request
→ Query Rewrite
→ Retrieval
→ Reranking
→ LLM Answer Generation
→ Citations + Confidence

## Universal Source Overview Chunks

Every knowledgebase receives a deterministic overview chunk generated from source metadata and statistics (no LLM used). Types: Website, PDF, Video, Repository. These chunks improve broad questions (summary, beginner explanation, main points) without fabricating facts.

Overview metadata example:

```
chunk_kind=source_overview
is_sage_overview=true
overview_type=website|pdf|video|github
```

Markers used:

```
__SAGE_WEBSITE_OVERVIEW__
__SAGE_PDF_OVERVIEW__
__SAGE_VIDEO_OVERVIEW__
__SAGE_REPO_OVERVIEW__
```

## Module Summary

Website Intelligence:
- Crawls websites using Playwright and stores page-grounded chunks plus a website overview chunk.

PDF Intelligence:
- Extracts selectable text with PyMuPDF, chunks by page, and stores a PDF overview chunk.

Video Intelligence:
- Uses available YouTube transcripts; if missing, optional auto-transcription via `yt-dlp` + `faster-whisper`. Adds timestamped chunks and a video overview chunk.

GitHub Intelligence:
- Ingests public repositories, chunks files with file path and line ranges, and creates a repository overview chunk.

Chrome Extension:
- Website-only side panel for quick website QA (use main web app for PDFs, Videos, GitHub).

## Folder Structure (high-level)

SAGE/

├── backend/
 
├── frontend/

├── extension/

├── docs/

├── README.md

└── .gitignore

### Backend highlights
- `backend/app/` — FastAPI app, ingestion pipelines, services
- `backend/sql/` — Supabase schema and migrations
- `backend/tests/` — Unit and integration tests

### Frontend highlights
- `frontend/src/` — React components

## Environment variables

Required (copy `backend/.env.example` to `backend/.env`):

```
SUPABASE_URL=
SUPABASE_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=
STORE_QUERY_HISTORY=false
WHISPER_MODEL_SIZE=tiny
```

Never commit real secrets to the repo.

## Supabase setup

Run required SQL:

```
backend/sql/schema.sql
backend/sql/2026_05_04_sage_v15_hardening.sql
```

## Backend setup

```bash
cd backend
source ../venv/bin/activate   # or source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python run.py
```

Or run via uvicorn for development:

```bash
uvicorn app.main:app --reload
```

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

For final verification only:

```bash
npm run build
```

## Chrome extension setup

1. Open `chrome://extensions` and enable Developer Mode
2. Click "Load unpacked" and select the `extension/` folder
3. Start backend and open the side panel on a website

## Demo Flow (short)

- Website: https://www.python.org/about/ — Ask: "What is Python?"
- PDF: upload a small PDF — Ask: "What does SAGE stand for?"
- Video: use pre-analyzed short video — Ask: "What is this video about?"
- GitHub: https://github.com/0xTheProDev/fastapi-clean-example — Ask: "What does this repo do?"

## Testing summary

- Website: ready for demo (Playwright required for full integration)
- PDF: ready for demo (selectable text required)
- Video: ready for demo with pre-analyzed video recommended
- GitHub: ready for demo (public repos)

## Known limitations

- No authentication (prototype)
- Auto-transcription can be slow on CPU
- Scanned PDFs need OCR (future work)
- Private GitHub repos not supported
- Free-tier LLM quotas: if Gemini is rate-limited, SAGE falls back to Groq automatically

## Future work

- User authentication, cloud deployment, OCR, private repo support, Redis/Celery job queue, production vector DB.
