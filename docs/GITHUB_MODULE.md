# GitHub Repository Intelligence Module

1. Module purpose

- Ingest public GitHub repositories to enable code-aware QA with file/line citations.

2. Accepted input

- Public GitHub repository URLs (owner/repo optionally with branch/path).

3. Ingestion flow

- Shallow `git clone` or ZIP download of repository contents.
- Filter files by size/type and skip binaries; enforce configured file/chunk limits.
- Chunk files by logical line ranges and store file path + start/end lines in metadata.

4. Universal Source Overview Chunk behavior

-- A deterministic repository overview chunk is created from repository metadata (files, languages, detected important files).
-- Metadata: `chunk_kind=source_overview`, `is_sage_overview=true`, `overview_type=github`.
-- Marker: `__SAGE_REPO_OVERVIEW__`.

5. QA behavior

- Grounded QA returns file path + line-range citations and snippets; reranker promotes relevant code snippets.

6. Citation behavior

- Citations include `source_id`, `file_path`, `start_line`, `end_line`, `snippet`, and `score`.

7. Testing summary

- URL validation, overview chunk generation, ingestion stability, and QA stability were validated; unit tests for overview generation are included.

8. Known limitations

- Private repositories are not supported in this prototype.
- Large repositories are limited by file/chunk caps.

9. Demo notes

- Recommended demo repository: https://github.com/0xTheProDev/fastapi-clean-example
