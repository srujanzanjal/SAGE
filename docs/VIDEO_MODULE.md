# Video Intelligence Module

1. Module purpose

- Ingest YouTube videos to enable timestamped, source-grounded QA and summaries.

2. Accepted input

- Public YouTube video URLs (watch links).

3. Ingestion flow

- Try `youtube-transcript-api` to obtain existing transcripts/captions.
- If unavailable, optional auto-transcription uses `yt-dlp` to fetch audio and `faster-whisper` for STT.
- Transcript is chunked into timestamped segments and stored.

4. Universal Source Overview Chunk behavior

- The first chunk is a deterministic video overview derived from transcript metadata.
- Metadata: `chunk_kind=source_overview`, `is_sage_overview=true`, `overview_type=video`.
- Marker: `__SAGE_VIDEO_OVERVIEW__`.

5. QA behavior

- Grounded answers include timestamped citations (snippet + start/end times).
- Exploratory mode can summarize broader themes but still surfaces evidence when available.

6. Citation behavior

- Citations include `source_id`, `timestamp_label` (e.g. '00:00 - 02:10'), `start_time`, `end_time`, `snippet`, and `score`.

7. Testing summary

- Auto-transcription fallback, timestamped chunking, evidence rendering, and frontend checks were validated.

8. Known limitations

- Auto-transcription can be time-consuming on CPU; for demos use pre-analyzed videos.

9. Demo notes

- Prefer a short, pre-analyzed video (under ~10–15 minutes) to keep demo time reasonable.
