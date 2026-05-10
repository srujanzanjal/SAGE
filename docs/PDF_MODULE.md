# PDF / Document Intelligence Module

1. Module purpose

- Extract selectable text from PDFs and provide page-grounded QA with citations.

2. Accepted input

- PDF files with selectable text (not scanned images). Upload via the web UI or API.

3. Ingestion flow

- PyMuPDF extracts selectable text from each page.
- Text is chunked with page metadata (`page_number`) and stored for retrieval.

4. Universal Source Overview Chunk behavior

- The first chunk is a deterministic PDF overview derived from metadata and chunk counts.
- Metadata: `chunk_kind=source_overview`, `is_sage_overview=true`, `overview_type=pdf`.
- Marker: `__SAGE_PDF_OVERVIEW__`.

5. QA behavior

- Grounded QA returns page-level citations and snippets; exploratory mode produces broader explanations.

6. Citation behavior

- Citations include `source_id`, `source_ref`, `page_number`, `chunk_index`, `snippet`, and `score`.

7. Testing summary

- Valid PDF ingestion, empty-PDF rejection, unsupported-file rejection, QA and delete/re-ingest flows validated.

8. Known limitations

- Scanned (image-only) PDFs are not OCRed; OCR is future work.

9. Demo notes

- Use a short, 1–3 page PDF with selectable text for the fastest demo.
