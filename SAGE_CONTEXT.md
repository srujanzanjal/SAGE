# SAGE — Complete Context & Handoff Document

> **Purpose of this file:** a single, exhaustive brief so another agent (or human) can understand SAGE entirely — the system, the code, the research paper, the deployment story, the git state, and every open thread — without re-deriving it. Written 2026-10-23. Convert relative dates to absolute when updating.
>
> **If anything here names a file, function, flag, or number, verify it still exists before acting on it** — code drifts.

---

## 0. TL;DR

**SAGE (Semantic Analysis and Generation Engine)** is a multi-source Retrieval-Augmented Generation (RAG) system that ingests **four structurally different source types** — crawled **websites**, **PDFs**, **YouTube videos**, and **GitHub repositories** — through one shared *ingest → chunk → embed → index* contract, and answers questions over one/several/all of them through one *retrieve → rerank → confidence-gate → generate* pipeline, streaming cited answers.

It is a **student major-year project** by 5 authors, built to be **zero-cost** (free tiers only) and **demo-first**, and its research paper has been **accepted (oral, Full Paper) at IEEE IDICAIHEI-2026**.

Three design decisions are its contribution (it introduces **no new ML model**):
1. **Deterministic source-overview chunk** — a non-LLM summary chunk per source so broad "what is this about" questions are retrievable.
2. **Hybrid rerank + diversity floor** — semantic+lexical blend, plus a rule that guarantees each combined source at least one citation slot.
3. **Confidence-gated refusal** — a scalar score from retrieval evidence decides whether Grounded Mode answers or refuses, before any generation call.

**Recent major change (this session):** vector storage was **migrated from ChromaDB → Supabase pgvector**. Chroma is fully removed. See §7.

---

## 1. People, intent, constraints

- **Authors:** Srujan Zanjal (lead), Rimanshu Sonule, Pratik Bhoyar, Tanisha Shingne, Prof. Ayaz Khan.
- **Institution:** St. Vincent Pallotti College of Engineering and Technology, Nagpur, Maharashtra, India.
- **Owner's git identity:** `srujan <zanjalsrujan94@gmail.com>`, GitHub `srujanzanjal`. Account email on file: `ubasvpcetproject@gmail.com`.
- **Hard constraints (from the owner):**
  - **Zero cost.** Everything runs on free tiers. No paid APIs, no paid hosting.
  - **Demo-first.** Reliability during a live demo matters more than scale.
  - **Keep the paper in sync** with what the system actually does.
- **Free-tier limits that shape the design:**
  - **Gemini:** ~20 requests/day **per model** (free tier).
  - **Groq:** ~8k tokens/minute **per model**.
  - These are why there is a multi-model fallback chain (§5) and why the system is careful about LLM call count.

---

## 2. Repository layout

Repo root: `/Users/srujan/Downloads/sage-mvp 2` (note the space in the path). GitHub: `https://github.com/srujanzanjal/SAGE`.

```
sage-mvp 2/
├── backend/                  # FastAPI app (Python 3.11)
│   ├── app/
│   │   ├── main.py           # FastAPI app factory, CORS, router mount
│   │   ├── run.py            # uvicorn entrypoint
│   │   ├── core/
│   │   │   ├── config.py          # pydantic-settings; all env vars live here
│   │   │   └── supabase_client.py # one cached Supabase client per process
│   │   │   # NOTE: chroma_client.py was DELETED in the pgvector migration
│   │   ├── models/schemas.py # pydantic request/response + SourceType enum
│   │   ├── api/v1/endpoints/  # ingest.py, jobs.py, qa.py, sources.py
│   │   └── services/          # all the logic — see §3
│   ├── eval/                  # evaluation harness — see §9
│   ├── sql/                   # Supabase schema + migrations — see §6
│   ├── tests/                 # pytest; ~17 test_*.py files, 95 offline tests
│   ├── requirements.txt
│   ├── .env                   # real secrets (gitignored); .env.example is the template
│   └── chroma_data/           # DELETED — stale Chroma dir, gone
├── frontend/                 # Vite + React + Tailwind web client
│   └── src/
│       ├── App.jsx, main.jsx, styles.css
│       ├── lib/api.js         # fetch wrappers incl. SSE stream reader
│       └── components/        # ChatPanel, AnswerCard, SourceBrief, SourceList,
│                              #   SourceIngestPanel, ModeSelector, LandingPage, ErrorBoundary
├── extension/                # Chrome Manifest V3 side-panel (website-focused)
│   ├── manifest.json, service_worker.js, sidepanel.{html,css,js}, icons/
├── research-papers/          # LaTeX sources (see §10)
│   ├── SAGE_Research_Paper_v2.tex   # == the camera-ready; committed
│   ├── SAGE_Research_Paper_v2.pdf
│   └── SAGE_Survey_Paper_v2.tex
├── docs/                     # per-module notes (WEBSITE/GITHUB/PDF/VIDEO _MODULE.md)
├── start.sh                  # dev launcher (backend :8000 + frontend :5173) — UNTRACKED
├── README.md
└── SAGE_CONTEXT.md           # this file
```

---

## 3. Backend architecture (FastAPI)

**Stack:** FastAPI 0.115, uvicorn, pydantic-settings, supabase-py 2.10, sentence-transformers 3.3 (torch), groq SDK, requests, BeautifulSoup4, PyMuPDF (fitz), Playwright 1.46, youtube-transcript-api, yt-dlp, faster-whisper, langdetect. (Chromadb was removed.)

### The two halves
- **Ingestion half:** each modality has its own extractor, all converging on a common `TextChunk` list → embed → upsert to the vector store (+ a deterministic overview chunk per source).
- **Query half:** every question flows through one pipeline: query-rewrite → retrieve → rerank + diversity floor → confidence gate → generate (Grounded or Exploratory) → stream with citations.

### Services (`backend/app/services/`)
- **`ingestion_pipeline.py`** — orchestrates ingestion for all four modalities. Calls extractor → chunker → overview → embeddings → **both** `vector_store.upsert_chunks()` **and** `repo.insert_chunks()` (see the two-writer note in §7).
- **`ingestion_jobs.py` / `job_tracker.py`** — async job tracking for GitHub/video ingestion. **In-process dict, non-persistent** (lost on restart — a known limitation).
- **`website_crawler.py`** — Playwright breadth-first, same-domain crawl; re-validates every link (incl. redirects) against a public-address check to block SSRF. Dedup on normalized URL.
- **`pdf_extractor.py`** — PyMuPDF per-page text; `%PDF` magic-byte check; 25MB cap; fails explicitly on scanned/image-only PDFs ("OCR not implemented"). Dedup on SHA-256 of bytes.
- **`video_transcriber.py` / `video_transcript.py`** — YouTube transcript API first; explicit user-triggered Whisper (`faster-whisper`) fallback over downloaded audio (yt-dlp). Caps 900s / 100MB. Timestamps become `[MM:SS--MM:SS]` citation labels.
- **`github_repo.py`** — shallow `git clone --depth 1` (ZIP fallback with zip-slip protection). Caps: 300 files, 1200 chunks, 2,000,000 chars, 250KB/file, 100k lines/file. Line-range chunking (40–120 lines).
- **`chunker.py`** — shared sentence-aware chunker: 1200-char budget, 180-char overlap (seeds new chunk with prior chunk's tail). Video uses a band chunker (900 target, 700–1000 band).
- **`source_overview.py` / `source_brief.py`** — builds the deterministic overview chunk (chunk index 0) from source stats + excerpts (term-frequency topic line over a stopword list, first/last excerpts). GitHub overview is filesystem-introspective (walks the tree). `source_brief.py` powers the UI "Source Brief".
- **`embeddings.py`** — `EmbeddingService`: `sentence-transformers` model `all-MiniLM-L6-v2`, **384-dim**, L2-normalized. Applies role prefixes for e5/bge models (MiniLM uses none). `@lru_cache` on construction (model loads once).
- **`vector_store.py`** — **the vector abstraction, now backed by Supabase pgvector** (was Chroma). Public API unchanged: `upsert_chunks`, `search`, `get_chunk`, `get_source_chunks`, `get_overview_chunks`, `get_overview_text`, `get_edge_chunks`, `delete_by_source`, `delete_by_knowledgebase`. See §7 for internals.
- **`retrieval_types.py`** — `RetrievedChunk` dataclass (chunk_id, text, metadata, distance, semantic_score, score).
- **`reranker.py`** — BM25 helpers + the hybrid rerank blend. See §4.
- **`qa_pipeline.py`** — **the heart of the query half.** `_retrieve_and_build_context()` (retrieve → rerank → diversity floor → build context → confidence), `answer_question()` (sync), `stream_answer_question()` (SSE generator: `meta` event → `delta` events → `done` event), `format_sse_event()`.
- **`confidence.py`** — the κ confidence score and the user-facing label heuristic. See §4.
- **`llm.py`** — `LLMService`: Gemini-first, Groq-fallback provider chain with per-model cooldowns on 429. `generate_answer()`, `generate_answer_stream()`, `rewrite_query()`, translation. `thinkingBudget: 0` on Gemini to cut latency. See §5.
- **`translation.py`** — translates non-English source text / queries via the fast LLM (bounded segment/char caps).
- **`evidence.py`** — `find_evidence(chunk_id, claims)` — matches answer claims back to chunk text for the clickable-citation / evidence-highlight feature.
- **`source_management.py`** — delete/recrawl a source or knowledgebase. **Deleting chunk rows now deletes the vectors too** (same table), so the old best-effort Chroma cleanup is gone.
- **`supabase_repo.py`** — `SupabaseRepository`: all relational DB access (knowledgebases, sources, chunks, query_history). `insert_chunks()`, `get_*`, `delete_*`, `save_query_history()`. `make_chunk_id()` = truncated SHA-256(kb_id:source_id:index:text)[:24].
- **`text_utils.py`, `url_utils.py`** — helpers (normalization, URL canonicalization).

### Endpoints (`backend/app/api/v1/endpoints/`, prefix `/api/v1`)
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| POST | `/qa/ask` | synchronous QA |
| POST | `/qa/ask/stream` | **SSE streaming QA** (meta→delta→done) |
| POST | `/qa/evidence` | map claims to chunk evidence |
| POST | `/ingest/website`, `/ingest/pdf` | synchronous crawl / upload |
| POST | `/ingest/video`, `/ingest/video-auto-transcribe` | transcript API / Whisper fallback (two explicit endpoints, no server-side chaining) |
| POST | `/jobs/github-ingest` | async GitHub ingest (only async ingest path) |
| GET | `/jobs/{job_id}` | poll async job status |
| GET | `/sources`, `/sources/grouped`, `/sources/{id}/summary` | list / overview text |
| DELETE | `/sources/{id}` | delete source + its vectors |
| POST | `/sources/website/recrawl` | async re-crawl |

---

## 4. Core algorithms (verify exact constants in code)

### Embedding
`all-MiniLM-L6-v2`, 384-dim, `normalize_embeddings=True`. Query and documents embedded the same way (MiniLM has no role prefix).

### Hybrid rerank (`reranker.py`, formula in paper Eq. 1)
- Semantic score `s = clip_[0,1](1 - d)` where `d` = cosine distance from the vector store.
- Lexical term-recall `ℓ = |Q ∩ T| / |Q|` (fraction of query tokens ≥3 chars, minus stopwords, literally appearing in the chunk).
- **Final score = `0.78·s + 0.22·ℓ`** (rounded to 4 dp). No second neural pass.
- Candidate pool sizing: GitHub-only `min(2k,8)`; other single-source `2k`; combined `n≥2` sources `2k·n` capped at 40 (so the diversity floor has real per-source candidates).

### Diversity floor (`qa_pipeline.py`, Algorithm 1 in paper)
Activates **only** when a request explicitly names **≥2 combined `source_ids`**. Reserve one slot (the best chunk) per source first, then fill remaining slots by pure score, re-sort, truncate to k. Fixes "silent single-source starvation" where one source gets zero citations.

### Confidence κ (`confidence.py`, Eq. 2 in paper)
`κ = clip_[0,1](0.65·b + 0.35·ā + 0.025·min(n,5))` where `b` = top chunk's blended score, `ā` = mean of top 3, `n` = #retrieved. Coverage bonus up to 0.125.

**IMPORTANT — paper vs. code drift on refusal logic:**
- The **published/camera-ready paper** describes refusing when `κ < 0.28` (video exempt).
- The **current code** (newer behavior, per `research-papers/SAGE_Research_Paper_v2.tex` which was written to match it) refuses outright **only when nothing is retrieved**; otherwise the generator answers from context and answers with **`κ < 0.45`** carry a verify-citations warning. User-facing label thresholds are **High ≥ 0.75 / Medium ≥ 0.45**.
- **Trust `confidence.py` + `qa_pipeline.py` for the real thresholds**, not this summary.

### Context assembly
Total-context budget 12,000 chars (10,000 all-GitHub); per-chunk 1,600 (1,200 GitHub). Overview chunks exempt/always included. Citation markers `[S1]…`. GitHub chunks carry `blob/…#Lstart-end` permalinks; video chunks `[MM:SS--MM:SS]`.

### Query rewriting (current code behavior)
Every question is rewritten before retrieval by one temp-0, 80-token call: fixes spelling, expands abbreviations, **translates non-English → English** (corpus is indexed in English), resolves references from the last 3 turns (passed as quoted context, plus selected source titles). Retrieval then searches with **both** the original and rewritten query, keeping each chunk's best score (so exact identifiers aren't lost to paraphrase). Timeout → silent fallback to original.

### Answer modes
- **Grounded Mode** (temp 0.1): answer only from context, else "Not available in the provided source". Citation-only.
- **Exploratory Mode** (temp 0.3): always attempts an answer; for brainstorming.

---

## 5. LLM provider chain (`llm.py`)

All LLM calls (answering, rewriting, translation) run on **free tiers** through an ordered fallback chain:
1. **Google Gemini 2.5 Flash** (answers), **2.5 Flash-Lite** (rewrite/translate) — primary.
2. **Groq-hosted open models** — `qwen/qwen3.8-27b`, then `openai/gpt-oss-20b`, `openai/gpt-oss-120b`.

Each model has an independent quota. A 429 benches **only that model** for the provider-reported reset (≈1h for an exhausted daily quota); the next model answers immediately. If all are briefly exhausted, a request waits ≤20s for capacity then returns a retry notice (`QUOTA_EXHAUSTED_MESSAGE`) rather than failing. Gemini calls set `thinkingConfig.thinkingBudget: 0` to cut latency. Streaming supported for both providers (`_gemini_stream`, `_groq_stream`).

Env knobs: `GEMINI_MODEL`, `GEMINI_FAST_MODEL`, `GROQ_MODEL`, `GROQ_FALLBACK_MODELS` (see §8).

---

## 6. Data model & vector storage (Supabase)

**Supabase (Postgres) is the single store of record** for both relational data **and** vectors (post-migration).

SQL files in `backend/sql/`, run in the Supabase SQL Editor **in this order**:
1. `schema.sql` — base tables + triggers.
2. `2026_05_04_sage_v15_hardening.sql` — adds video/github source types, query-history purge fn.
3. `2026_10_13_pgvector.sql` — **enables `vector` extension, adds `chunks.embedding vector(384)`, HNSW cosine index, `match_chunks` RPC.** (Required for the app post-migration.)
4. `2026_10_14_eval_embeddings.sql` — `eval_chunk_embeddings` table + `match_chunks_eval` RPC (only needed for the eval model sweep, §9).

### Tables
- **`knowledgebases`** — id (uuid), name, source_type (website/pdf/video/github), canonical_ref (unique), status (processing/ready/failed), timestamps.
- **`sources`** — id, knowledgebase_id (FK cascade), source_type, original_ref, canonical_ref (unique), title, status, content_hash, text_length, meta (jsonb), timestamps.
- **`chunks`** — `id text PK` (the content-addressed chunk_id), knowledgebase_id, source_id (FK cascade), chunk_index, text, token_estimate, char_count, source_ref, page_number, section_title, **metadata (jsonb)**, created_at, **`embedding vector(384)`** (added by migration).
- **`query_history`** — opt-in (`STORE_QUERY_HISTORY`, default false); question/answer/confidence/retrieved_chunk_ids. Purge fn `purge_old_query_history(retention_days)`.

### Chunk metadata
`chunks.metadata` jsonb carries `source_type`, `chunk_kind` (e.g. `source_overview`), and modality extras (video_id, timestamp_label, start/end_time, repo_owner/name, branch, file_path, start/end_line, language, source_title, etc.). `vector_store._row_to_chunk()` reconstructs the flat metadata dict callers expect by merging the jsonb with the structural columns.

---

## 7. THE pgvector MIGRATION (most important recent change)

**What & why:** vectors used to live in a local **ChromaDB** file (`backend/chroma_data/`), duplicating chunk text/metadata that already lived in Supabase. Chroma's on-disk persistence is **lost on an ephemeral free host** (e.g. Hugging Face Spaces), so everything was consolidated into Supabase pgvector and Chroma was dropped. Committed as `ee8fc65`.

**What changed:**
- `chunks.embedding vector(384)` column + `match_chunks` RPC (SQL migration `2026_10_13`).
- `vector_store.py` rewritten against Supabase: `search()` → `match_chunks` RPC; `get_*` → PostgREST table selects; `upsert_chunks()` writes the embedding into the chunk row. **Public API unchanged**, so `qa_pipeline`, `ingestion_pipeline`, `evidence`, `source_brief` callers were untouched.
- `backend/app/core/chroma_client.py` **deleted**; `chromadb` removed from `requirements.txt`; `chroma_*` settings removed from `config.py`.
- `source_management.py` simplified: chunk-row deletes remove the vectors too (same table), so the redundant best-effort Chroma cleanup + stale warnings are gone.

**GOTCHAS the next agent must know:**
- **Embedding write format:** pgvector takes a text literal `"[0.1,0.2,…]"` (helper `vector_store._to_vector_literal`). PostgREST **upsert cannot do partial-column updates** on existing rows (NOT NULL columns block the implicit insert) — to backfill/patch embeddings you must `UPDATE … SET embedding …`, not `upsert({id, embedding})`.
- **Two-writer pattern (ponytail debt):** ingestion still calls **both** `vector_store.upsert_chunks()` (full row + embedding) **and** `repo.insert_chunks()` (same row, no embedding), both upserting to `chunks` on `id`. Order-independent because on-conflict update never clears columns absent from a payload. It's redundant (two writes/batch); marked with a `ponytail:` comment to fold into one later. Tests assert on `upsert_chunks`, which is why it stayed.
- **Old chunks need embeddings:** after adding the column, pre-existing chunk rows have `embedding = NULL` and `match_chunks` skips them (`where embedding is not null`). They were **backfilled** this session (340 chunks, all 16 sources, default model). If you add the column to a fresh DB, re-ingest or backfill.
- **Dimension is hardcoded 384** (matches MiniLM). Change the model → change `vector(384)` in the SQL and re-embed.

**Verification done this session:** all 340 chunks embedded; a live `match_chunks` query returned correctly ranked hits; 99 offline tests pass (the ~10 integration tests need live Supabase + the SQL applied).

---

## 8. Environment variables & running

`backend/.env` (template `backend/.env.example`):
```
SUPABASE_URL=            # required
SUPABASE_KEY=            # required (service-role or anon per setup)
GEMINI_API_KEY=          # primary LLM (aistudio.google.com free tier)
GROQ_API_KEY=            # fallback LLM
# optional overrides:
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FAST_MODEL=gemini-2.5-flash-lite
GROQ_MODEL=qwen/qwen3.8-27b
GROQ_FALLBACK_MODELS=openai/gpt-oss-20b,openai/gpt-oss-120b
STORE_QUERY_HISTORY=false
WHISPER_MODEL_SIZE=tiny  # tiny|base|small
# EVAL_EMBEDDING_MODEL=   # eval-only; routes retrieval to eval_chunk_embeddings
```
`config.py` has more knobs (chunk sizes, top_k=6, timeouts, CORS, caps). `extra="ignore"` so unknown env keys are harmless.

**Run (dev):** `./start.sh` from repo root — launches backend (uvicorn :8000, API docs at `/docs`) + frontend (Vite :5173). Requires `venv/` with `pip install -r backend/requirements.txt`, Playwright browsers installed, and the SQL migrations applied to Supabase. An iOS-sim note doesn't apply; this is web.

**First-run heaviness:** sentence-transformers downloads the model (~90MB) and torch loads on first query (cold start). Playwright needs browser binaries; faster-whisper needs ffmpeg + a model download. This is why free *serverless* tiers don't fit — see §12.

---

## 9. Evaluation harness (`backend/eval/`)

- **Eval set:** 50 questions over 6 real sources spanning all four modalities (this paper's PDF, a TED talk transcript, `kennethreitz/records`, the Wikipedia RAG article, a college website, `python.org/about`); 10 deliberately unanswerable; 34 carry labeled evidence spans. Categories: factual(17), typo(5), Hindi/Hinglish(5), paraphrase(4), vague(4), summary(2), multi-source(2), positional(1), + 10 unanswerable.
- **`run_eval.py`** — `--retrieval` (ablation + per-config recall/MRR via the real `_retrieve_and_build_context`), `--answers` (full-system answers, paced for free tiers), `--report` (writes `results/report.md` + `results/tables.tex`). `--model <name>` runs an embedding-model comparison.
- **`reembed.py`** — re-embeds all chunks with another model into `eval_chunk_embeddings` (no re-crawl). **Post-migration:** writes to the eval table (not a Chroma collection). `EVAL_EMBEDDING_MODEL` makes `vector_store.search()` route to `match_chunks_eval` for that model; the default model reads production `chunks.embedding` untouched. **Run `2026_10_14_eval_embeddings.sql` before a model sweep.**
- **Results (real, in `results/`):** Dense-only baseline → Full SAGE: context recall 91%→94%, MRR 0.69→0.77. Answer accuracy 90% (40 answerable), refusal recall 100%, precision 77%. Median answer latency ~2.4s; retrieval+rerank <20ms/query. MiniLM ≥ bge-small ≥ e5-small on this set.
- **Scoring:** keyword-match for answers (contains expected key term); evidence-span match (case/whitespace-insensitive) for retrieval; refusal = correct for unanswerable.

---

## 10. Research paper (ACCEPTED — camera-ready in progress)

- **Title:** *SAGE (Semantic Analysis and Generation Engine): A Cross-Source Reasoning Engine over Heterogeneous Knowledgebases.*
- **Venue:** 4th IEEE DMIHER International Conference on AI in Healthcare, Education and Industry (**IDICAIHEI-2026**), Wardha, India, **Nov 27–28, 2026**. **Accepted — oral, Full Paper**, to IEEE Xplore pending registration + formatting. **Paper ID 1111.** Conference Id 70421.
- **Reviews:** 3 reviewers, all "Accept with Major Revisions." Unanimous substantive ask: **direct comparison vs conventional RAG** + evaluate provenance/citation-correctness/retrieval-quality/latency/failure-cases. Organizers later clarified: **do the reviewer revisions**, but **keep title/authors/abstract the same**; small paragraph edits + adding tables are fine.
- **Mandatory formatting limits:** abstract 150–200 words, keywords 4–5, **≤6 pages**, references ≥20, **≤6 figures / ≤3 tables**, plagiarism/similarity **≤15%**.
- **LaTeX source — TWO copies, now IDENTICAL (camera-ready):**
  - `~/Downloads/main.tex` (the submission working file, **outside the repo** — not git-tracked).
  - `research-papers/SAGE_Research_Paper_v2.tex` (**committed** in repo at `4c99cb0`).
- **What was done to the camera-ready this session:** abstract trimmed 234→**197 words**; keywords 6→**5** (dropped "chunking"); evaluation section upgraded to the **50-question** study with a baseline-vs-SAGE table + per-category answers + failure analysis; consolidated to **3 tables** total (was 6 in a richer draft) to meet the cap; title/authors/abstract substance unchanged. The paper **deliberately still says ChromaDB** (the migration is a post-acceptance code change; "no content changes" + store is an implementation detail).
- **STILL OPEN (owner's action, can't be automated here):**
  1. **Compile** `main.tex` and confirm it's **≤6 pages** (it has a bit more eval prose than the exactly-6-page submission; trim if it spills).
  2. **Similarity check ≤15%** (Turnitin/iThenticate).
  3. **Registration was due Oct 20, 2026** — likely **overdue**; must confirm with the committee ASAP or risk withdrawal.
  4. Final PDF via **IEEE PDF eXpress** + e-Copyright (instructions come after registration).
  5. Optional: Section VIII once said "95 passing, 0 failing" then named 4 failures — reconcile if a reviewer might notice (the current repo tex already fixed this to "120 tests, 95 offline pass").
- **Presentation deck:** `~/Downloads/SAGE_IDICAIHEI_2026.pptx`, built this session from `~/Downloads/Conference Templet 2026-new.pptx` (the fixed IDICAIHEI template). 10 slides; slides 2 (metadata) and 4–8 (Intro/Methodology/Results/Conclusions/References) filled with SAGE content; branding/slides 1,3,9,10 kept. Source build artifacts in the session scratchpad.

---

## 11. Frontend & extension

- **Frontend** (`frontend/`): Vite + React + Tailwind. `src/lib/api.js` has the fetch wrappers and the **SSE stream reader** (consumes `/qa/ask/stream` `meta`/`delta`/`done` events). Components: `ChatPanel` (orchestrates streaming Q&A with a live cursor), `AnswerCard` (renders answer + citations + confidence + evidence), `SourceBrief`, `SourceList`, `SourceIngestPanel`, `ModeSelector`, `LandingPage`, `ErrorBoundary`. Builds to static `frontend/dist/`.
- **Extension** (`extension/`): Chrome Manifest V3 **side panel**. Covers websites, YouTube videos, and GitHub repos (per the current draft; PDF upload is web-client only). Has its own SSE stream reader (`sidepanel.js: streamAnswer`), evidence rendering, and a configurable `backendUrl`. Load unpacked for a demo (Chrome Web Store is a one-time $5 fee — skip for demos).
- **Perceived-latency design (already shipped):** the SSE `meta` event sends citations/confidence/sources **before** the answer streams, so the UI shows sources instantly then streams tokens.

---

## 12. Deployment story (zero-cost, discussed but NOT yet done)

The backend is **heavy ML** (torch ~2GB, Playwright browsers, faster-whisper + ffmpeg) → does **not** fit serverless/512MB free tiers. Recommended free home:
- **Backend → Hugging Face Spaces (Docker)**, free CPU tier (16GB RAM / 2 vCPU) — fits the fat image.
- **Frontend (`dist/`) → Cloudflare Pages / GitHub Pages / Vercel**, point API base at the Space.
- **Supabase** → already free (now holds vectors too, so persistence survives restarts — the whole reason for the pgvector migration).
- **LLM** → Gemini + Groq free keys as Space secrets.
- **Caveats:** free Spaces have **ephemeral disk** (fine now — vectors are in Supabase, not local) and **sleep when idle** (hit `/health` to warm before a demo). Cold start loads torch + the embedding model.
- **Latency-UX quick wins not yet applied:** warm the embedding model at startup (dummy `embed_query`), consider ordering Groq first for raw speed, cache repeated answers.

No deployment has been executed yet — this is a plan.

---

## 13. Git state & conventions

- **Remote:** `origin` = `https://github.com/srujanzanjal/SAGE`. **Default branch:** `main`.
- **Branches:** `main` (default), `demo-hardening` (older shared branch).
- **`main` HEAD:** `4c99cb0` "Trim abstract/keywords and strengthen evaluation for camera-ready" (pushed). Prior: `ee8fc65` pgvector migration.
- **HISTORY WAS REWRITTEN this session:** all `Co-Authored-By: Claude` trailers were stripped from every commit on `main` and `demo-hardening` via `git filter-branch`, then force-pushed (hashes changed). So **any other clone of this repo is now divergent and must re-clone / hard-reset** — tell co-authors.
- **ATTRIBUTION RULE (owner's global preference — follow strictly):** author commits as **`srujan <zanjalsrujan94@gmail.com>`** and add **NO Claude attribution** — no `Co-Authored-By: Claude …` on commits, no "🤖 Generated with Claude Code" on PRs. Verify with `git log -1 --pretty='%an <%ae>'` (should be the owner) and `%(trailers)` (should be empty).
- **Uncommitted working-tree changes at handoff (pre-existing, NOT from the migration):**
  - `M backend/app/api/v1/endpoints/sources.py`
  - `M backend/app/services/supabase_repo.py`
  - `M backend/tests/assets/pdf_module/generate_test_pdfs.py`
  - `?? start.sh` (the dev launcher — untracked; probably worth committing)
  - Their intent is unknown (predate this session). Review before committing/discarding.
- **Commit/push only when the owner asks.** If on `main`, branch first unless told otherwise.

---

## 14. Known limitations & open threads

- **No OCR** for scanned PDFs (fails cleanly).
- **Whisper fallback is manual** (explicit user action, not automatic).
- **Job tracker is in-process / non-persistent** — async job status lost on restart.
- **Website recrawl** deletes + fully re-embeds a knowledgebase (no diffing) — wastes compute on unchanged pages.
- **Confidence formula/thresholds tuned by hand**, checked on the 50-Q set, not a large labeled calibration dataset.
- **Chrome extension** lacks PDF upload (web client only).
- **Two-writer vector/chunk pattern** (§7) is redundant — candidate for cleanup.
- **Eval** is a single-machine, self-authored 50-Q set, not a public benchmark (future work).
- **No deployment executed** yet (§12).
- **Paper camera-ready** not finalized (§10 open items) + **registration likely overdue**.

---

## 15. Conventions / "don'ts" for the next agent

- **Keep it zero-cost and demo-first.** Don't introduce paid services or heavy new deps.
- **Be lazy/minimal** (the owner runs a "ponytail" lazy-senior-dev mode): reuse what exists, stdlib/native before deps, shortest diff that's correct, leave a runnable check for non-trivial logic. Don't over-engineer.
- **Paper stays ChromaDB** in its text unless the owner decides otherwise — the migration is code-only, and the paper is accepted describing Chroma.
- **No Claude attribution in git** (see §13).
- **Verify thresholds/constants in code** (`confidence.py`, `qa_pipeline.py`, `reranker.py`) rather than trusting the paper or this doc — paper and code have drifted on refusal logic.
- **When editing the vector layer**, keep `vector_store.py`'s public API stable (many callers depend on it) and remember the pgvector write/backfill gotchas (§7).
- **Memory files** live at `~/.claude/projects/-Users-srujan-Downloads-sage-mvp-2/memory/` (MEMORY.md index): SAGE project context + free-tier limits.

---

*End of SAGE_CONTEXT.md. Keep this updated as the system, paper, and deployment evolve.*
