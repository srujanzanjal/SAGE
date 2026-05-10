# Website Intelligence Module

1. Module purpose

- Provide source-grounded QA for websites by crawling pages, extracting rendered text, and creating searchable chunks.

2. Accepted input

- Public website URLs (http/https). Avoid pages behind authentication or anti-bot measures.

3. Ingestion flow

- Playwright renders pages to capture client-side content.
- Crawler follows same-domain links up to configured `max_depth` and `max_pages`.
- Extracted page text is chunked and stored with page metadata.

4. Universal Source Overview Chunk behavior

- The first chunk for each website is a deterministic overview chunk with metadata-derived summary only.
- Metadata: `chunk_kind=source_overview`, `is_sage_overview=true`, `overview_type=website`.
- Marker: `__SAGE_WEBSITE_OVERVIEW__`.

5. QA behavior

- Grounded mode retrieves chunks and returns answers with citations/snippets and a confidence score.
- Exploratory mode allows broader summarization but still surfaces sources when relevant.

6. Citation behavior

- Citations include `source_id`, `source_ref`, `snippet`, `score`, and page/chunk references when available.
- Overview chunk is labeled as Website Overview and may be shown for broad queries.

7. Testing summary

- Crawling, chunking, QA, delete/re-ingest, and frontend integration were validated during development.
- Playwright must be installed in the environment (`python -m playwright install chromium`) for full integration tests.

8. Known limitations

- JS-heavy sites with bot protections may fail to crawl.
- Low-text pages may be rejected; ensure pages have extractable text.

9. Demo notes

- Recommended demo URL: https://www.python.org/about/
- Use `max_pages=2` for fast demo runs.
