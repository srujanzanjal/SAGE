# Brief for a fresh Claude Code session: write 2 IEEE papers on SAGE

Paste everything below as your first message in a new chat, in this same
project directory (`/Users/srujan/Downloads/sage-mvp 2`).

---

## What went wrong last time (read this first, don't repeat it)

A previous session wrote two IEEE-format papers about this project
(they're sitting in `research-papers/` — `SAGE_Research_Paper.tex` and
`SAGE_Survey_Paper.tex`, plus compiled PDFs). They are **not good enough**
and should not be reused or lightly edited — start fresh. The core
problems, so you don't reproduce them:

1. **Wrong center of gravity.** Both papers spent too much of their page
   budget on (a) comparing SAGE to NotebookLM and generic frameworks like
   LangChain/LlamaIndex, and (b) security topics (SSRF defense, indirect
   prompt injection). Those are real things the system does, but they are
   NOT the point of the project and should be at most one short
   subsection each — a paragraph or two, not a organizing theme, not a
   dedicated major section, not a table repeated in both papers. **The
   actual point of the project is the multi-source retrieval-augmented
   QA engine itself: how it ingests four very different source types,
   how it chunks and embeds them, how it retrieves and reranks, how it
   generates grounded answers with citations, and the specific original
   design choices it makes (see "What actually deserves the page budget"
   below).** That is what must occupy 80-90% of both papers.
2. **Drifting title.** The name of the project is fixed:
   **SAGE — Semantic Analysis and Generation Engine**, a system for
   turning heterogeneous knowledgebases (websites, documents, videos,
   code repositories — "diff diff knowledgebases & codebases") into
   grounded, citable, conversational Q&A. The previous session gave the
   two papers different, invented subtitles ("A Security-Aware,
   Multi-Source..." vs. "Source-Grounded, Multi-Modal...") instead of
   using one stable name consistently. **Do not invent a new subtitle
   framing per paper.** Both papers must open with the same name and the
   same one-line expansion, verbatim: *"SAGE (Semantic Analysis and
   Generation Engine)"*. After that first mention, just say "SAGE."
   Titles can differ in their descriptive tail (a research paper and a
   survey paper are naturally titled a little differently), but the core
   name/expansion must never vary, and don't bolt on adjective subtitles
   like "Security-Aware" that overweight one theme.

## Required checkpoint before you write full drafts

Before producing complete LaTeX, show the user a short outline for both
papers with an estimated page/section allocation (e.g. "Section IV,
Ingestion Pipelines, ~2.5 pages; Section VII, Security, ~0.5 pages") and
get explicit confirmation that the balance looks right. This is the
single most important process fix — the balance was wrong last time and
nobody caught it until both full drafts were already written.

## Step 1 — understand the actual application, from the actual code

Do not rely on any prior summary (including this brief's appendix below,
which is a snapshot and may be stale). Read the real source. At minimum:

- `backend/app/services/qa_pipeline.py` — the whole retrieval → rerank →
  diversity-floor → context-build → generate → cite → confidence flow,
  including the streaming variant.
- `backend/app/services/reranker.py`, `confidence.py` — exact scoring
  formulas.
- `backend/app/services/source_overview.py` — the deterministic
  overview-chunk generator per modality (this is the project's most
  original idea; give it real depth, not a passing mention).
- `backend/app/services/ingestion_pipeline.py`, `website_crawler.py`,
  `web_scraper.py`, `pdf_extractor.py`, `video_transcript.py`,
  `video_transcriber.py`, `github_repo.py`, `chunker.py` — the actual
  per-modality extraction and chunking mechanics.
- `backend/app/services/vector_store.py`, `backend/app/core/config.py` —
  embedding model, Chroma config, chunk size/overlap, top-k defaults.
- `backend/app/services/llm.py` — grounded vs. exploratory mode, query
  rewriting, streaming generation.
- `backend/app/models/schemas.py`, `backend/app/api/v1/endpoints/*.py` —
  the actual request/response contract and endpoint list.
- `frontend/src/components/*.jsx`, `frontend/src/lib/api.js` — how
  streaming, multi-source selection, memory, and the Summary card
  actually work client-side.
- `extension/*` — what the Chrome side panel actually does now
  (it was brought to feature parity with the web app: streaming,
  memory, multi-source).
- `backend/tests/` — what's actually tested, as real evidence for a
  validation section (don't invent numbers).

Use Explore agents / grep liberally. Get every formula, threshold,
default, and cap right by reading code, not by guessing or trusting the
appendix below blindly.

## Step 2 — fresh literature research

Do real research (WebSearch/WebFetch, the `deep-research` skill if
useful, or an MCP server if the user has connected one by the time you
read this — ask them if unsure what's available). Every citation must be
real and verifiable (arXiv/ACL/ACM/official docs), never fabricated.
Focus the research on what actually explains SAGE's real mechanisms:
dense retrieval and RAG foundations, sentence embeddings, reranking
(including hybrid lexical+dense retrieval), chunking strategies for
long/structured documents, video/transcript QA, code-repository-aware
retrieval, multi-source/multi-document retrieval fusion, and confidence/
calibration in RAG. Security and NotebookLM-style products are legitimate
but minor citations here, not the research focus.

## What actually deserves the page budget

These are SAGE's real, specific, checkable technical contributions —
build both papers around them:

- A single shared ingestion → chunk → embed → index contract across four
  very different source types (website, PDF, video, GitHub repo), each
  with its own extractor but a common metadata/citation schema.
- Deterministic, non-generative **source-overview chunks** — generated
  once per knowledgebase from source statistics/excerpts, not a second
  LLM call — specifically to make broad ("what is this about") questions
  retrievable. This is the most original idea in the project; give it
  real technical and evaluative depth (how it's built per modality, what
  changed with vs. without it).
- The **reranking formula** (semantic + lexical blend) and the
  **diversity-floor mechanism** that guarantees fair citation
  representation across sources in a combined, multi-source query — a
  concrete bug-fix-turned-design-feature discovered during this project's
  own testing.
- The **confidence-scoring heuristic** and how it gates Grounded Mode's
  refusal behavior.
- Query rewriting using conversational history; the two answer modes
  (Grounded vs. Exploratory); SSE streaming architecture with
  incremental citation/answer delivery; multi-turn memory.
- Real prototype validation: what was actually ingested and tested
  (website, PDF, video, GitHub repo), what broke and got fixed during
  development (cite this project's own real findings, e.g. the
  diversity-floor fix), and honest limitations.

## Deliverables

- Two `.tex` files, IEEE conference format (`IEEEtran`), self-contained
  (`thebibliography`, no external `.bib` needed), real citations only.
- **Research paper**: deep technical dive on SAGE itself as described
  above. Target 10-12 pages (confirm with the user if their program has
  a hard cap).
- **Survey paper**: broader survey of multi-source/multi-modal
  retrieval-augmented QA techniques, using SAGE as one illustrative case
  study near the end — not the dominant subject, and not organized
  around NotebookLM or security either. Confirm target length with the
  user.
- Compile both with `tectonic` (available on this machine) or `pdflatex`
  and confirm zero errors and a sane page count before calling it done.
  Render a page or two to PNG (PyMuPDF is available in
  `venv/`) and actually look at them — check tables/figures/algorithms
  render cleanly, no overfull-hbox visual breakage.
- Use new filenames (e.g. `SAGE_Research_Paper_v2.tex`,
  `SAGE_Survey_Paper_v2.tex`) so the old drafts remain for reference/diff
  rather than being silently overwritten.
- Low-plagiarism requirement: write all prose originally; cite ideas,
  never copy phrasing from abstracts or source text.

---

## Appendix: verified technical facts as of 2026-07-12 (snapshot — verify against current code, it may have changed)

**Stack**: FastAPI 0.115.6, ChromaDB 0.5.23, sentence-transformers 3.3.1
(`all-MiniLM-L6-v2`, L2-normalized), Groq SDK 0.13.1, Playwright 1.46.0,
PyMuPDF 1.25.1, faster-whisper 1.0.3, Supabase client 2.10.0; React
19.2.5, Vite 8.0.10, Tailwind 4.2.4; Chrome MV3 extension v1.6.0.

**Chunking**: 1200 chars/chunk, 180-char overlap, sentence-aware with
tail-overlap carry. `DEFAULT_TOP_K=6`.

**Reranking**: `score = 0.78*semantic + 0.22*keyword_overlap` (semantic =
1 - cosine distance from Chroma; keyword overlap = Jaccard-like
non-stopword token overlap).

**Diversity floor**: for multi-source queries, reserve each source's
single best-ranked chunk first, then fill remaining top-k slots by pure
score, re-sort by score.

**Confidence**: `κ = clip[0,1](0.65*best_score + 0.35*avg_score(top-3) +
min(len(chunks),5)*0.025)`. Grounded-mode refusal if no chunks or κ <
0.28 (video sources get a warning instead of hard refusal).

**Context building**: max_context_chars 12,000 (10,000 for GitHub),
max_chunk_chars 1,600 (1,200 for GitHub); truncates rather than citing
chunks that didn't make it into context.

**GitHub caps**: 300 files, 1200 chunks, 2,000,000 total chars, 250KB/file,
100,000 lines/file.

**Video**: transcript API first, `yt-dlp` + `faster-whisper` fallback,
capped at 900s duration / 100MB audio.

**PDF**: 25MB cap, `%PDF` signature check, born-digital text only (no
OCR in core pipeline).

**Endpoints** (`/api/v1`): `POST /qa/ask`, `POST /qa/ask/stream`,
`POST /ingest/{website,pdf,video,video-auto-transcribe}`,
`GET/POST /jobs/*`, `GET /sources`, `GET /sources/{id}/summary`,
`DELETE /sources/{id}`, and knowledgebase-level variants.

**Tests**: 12 files, ~95 test functions across chunking, URL
normalization, GitHub parsing, reranker+confidence math, overview-chunk
generation, vector-store metadata, video transcript/fallback flows, plus
an API integration suite.
