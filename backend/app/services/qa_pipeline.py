import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from time import perf_counter

from app.core.config import get_settings
from app.models.schemas import AnswerResponse, Citation, QuestionRequest
from app.services.confidence import calculate_confidence, confidence_label_and_reason
from app.services.embeddings import get_embedding_service
from app.services.llm import LLMServiceTimeoutError, get_llm_service, should_rewrite
from app.services.reranker import rerank_chunks
from app.services.supabase_repo import get_supabase_repository
from app.services.text_utils import make_snippet
from app.services.retrieval_types import RetrievedChunk
from app.services.vector_store import get_vector_store


LOW_CONFIDENCE_THRESHOLD = 0.28
GITHUB_QA_TOP_K = 6
GITHUB_QA_MAX_SEARCH_RESULTS = 8
GITHUB_QA_MAX_CONTEXT_CHARS = 10_000
GITHUB_QA_MAX_CHUNK_CHARS = 1_200
DEFAULT_QA_MAX_CONTEXT_CHARS = 12_000
DEFAULT_QA_MAX_CHUNK_CHARS = 1_600
QUERY_HISTORY_WRITE_TIMEOUT_SECONDS = 2.0

logger = logging.getLogger(__name__)
_history_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qa-history")


def _build_follow_up_question(question: str, ranked_chunks: list[RetrievedChunk]) -> str:
    text = question.strip().lower().rstrip("?")
    if "summar" in text:
        return "Would you like a short summary, key takeaways, or a section-by-section breakdown?"
    if any(word in text for word in ("who", "speaker", "said", "talking")):
        return "Would you like a speaker-focused summary or the main points by topic?"
    if any(word in text for word in ("when", "timestamp", "time", "minute", "second")):
        return "Would you like me to focus on a specific timestamp or clip in the video?"
    if ranked_chunks and ranked_chunks[0].metadata.get("source_type") == "video":
        return "Would you like a summary, a topic overview, or help finding a specific timestamp?"
    return "Could you be more specific about what you want to know from this source?"


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _overview_label(metadata: dict[str, object]) -> str:
    overview_type = str(metadata.get("overview_type") or "").lower()
    return {
        "website": "Website Overview",
        "pdf": "PDF Overview",
        "video": "Video Overview",
        "github": "Repository Overview",
    }.get(overview_type, "Source Overview")


def _resolve_source_type(request: QuestionRequest, repo) -> str | None:
    if request.source_id:
        source = repo.get_source(request.source_id)
        if source and source.get("source_type"):
            return str(source.get("source_type"))
    if request.knowledgebase_id:
        knowledgebase = repo.get_knowledgebase(request.knowledgebase_id)
        if knowledgebase and knowledgebase.get("source_type"):
            return str(knowledgebase.get("source_type"))
    return None


def build_context(
    chunks: list[RetrievedChunk],
    *,
    max_context_chars: int = DEFAULT_QA_MAX_CONTEXT_CHARS,
    max_chunk_chars: int = DEFAULT_QA_MAX_CHUNK_CHARS,
) -> tuple[str, list[Citation]]:
    context_parts: list[str] = []
    citations: list[Citation] = []
    context_chars = 0

    for i, chunk in enumerate(chunks, start=1):
        citation_id = f"S{i}"
        metadata = chunk.metadata
        snippet = make_snippet(chunk.text)
        truncated_text = make_snippet(chunk.text, max_chunk_chars)
        source_type = metadata.get("source_type", "website")
        file_path = metadata.get("file_path")
        
        # Special handling for synthetic overview chunks
        if metadata.get("chunk_kind") in {"source_overview", "repo_overview"}:
            source_label = _overview_label(metadata)
            context_lines = [f"[{citation_id}] Source: {source_label}"]
            context_lines.extend([
                f"Chunk ID: {chunk.chunk_id}",
                f"Snippet: {snippet}",
                f"Text:\n{chunk.text}",  # Include full overview text, not truncated
            ])
        else:
            source_label = metadata.get("source_title") or metadata.get("source_ref") or "Unknown source"
            context_lines = [f"[{citation_id}] Source: {source_label}"]
            if source_type == "video" and metadata.get("timestamp_label"):
                context_lines.append(f"Timestamp: {metadata.get('timestamp_label')}")
            if source_type == "github" and file_path:
                # Add file path and line-range (only for non-overview chunks)
                lang = metadata.get("language")
                start_line = metadata.get("start_line")
                end_line = metadata.get("end_line")
                owner = metadata.get("repo_owner")
                repo_name = metadata.get("repo_name")
                branch = metadata.get("branch") or "HEAD"
                github_link = f"https://github.com/{owner}/{repo_name}/blob/{branch}/{file_path}#L{start_line}-L{end_line}"
                context_lines.append(f"File: {file_path} (lines {start_line}-{end_line})")
                context_lines.append(f"Language: {lang}")
                context_lines.append(f"GitHub: {github_link}")
            context_lines.extend([
                f"Chunk ID: {chunk.chunk_id}",
                f"Snippet: {snippet}",
                f"Text:\n{truncated_text}",
            ])
        
        context_block = "\n".join(context_lines)
        remaining = max_context_chars - context_chars
        if remaining <= 0:
            citations.append(
                Citation(
                    citation_id=citation_id,
                    chunk_id=chunk.chunk_id,
                    source_id=str(metadata.get("source_id")),
                    source_type=source_type,
                    source_ref=str(metadata.get("source_ref")),
                    source_title=metadata.get("source_title"),
                    snippet=snippet,
                    page_number=metadata.get("page_number"),
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    score=float(chunk.score),
                    video_id=metadata.get("video_id"),
                    timestamp_label=metadata.get("timestamp_label"),
                    start_time=metadata.get("start_time"),
                    end_time=metadata.get("end_time"),
                    file_path=metadata.get("file_path"),
                    language=metadata.get("language"),
                    start_line=metadata.get("start_line"),
                    end_line=metadata.get("end_line"),
                    repo_owner=metadata.get("repo_owner"),
                    repo_name=metadata.get("repo_name"),
                    branch=metadata.get("branch"),
                    file_url=(
                        f"https://github.com/{metadata.get('repo_owner')}/{metadata.get('repo_name')}/blob/{metadata.get('branch') or 'HEAD'}/{metadata.get('file_path')}#L{metadata.get('start_line')}-L{metadata.get('end_line')}"
                            if metadata.get("source_type") == "github" and metadata.get("file_path") and metadata.get("repo_owner") and metadata.get("repo_name") and metadata.get("chunk_kind") not in {"source_overview", "repo_overview"}
                        else None
                    ),
                )
            )
            continue

        if len(context_block) > remaining:
            context_block = _truncate_text(context_block, remaining)
        context_parts.append(context_block)
        context_chars += len(context_block) + 2
        citations.append(
            Citation(
                citation_id=citation_id,
                chunk_id=chunk.chunk_id,
                source_id=str(metadata.get("source_id")),
                source_type=source_type,
                source_ref=str(metadata.get("source_ref")),
                source_title=metadata.get("source_title"),
                snippet=snippet,
                page_number=metadata.get("page_number"),
                chunk_index=int(metadata.get("chunk_index", 0)),
                score=float(chunk.score),
                video_id=metadata.get("video_id"),
                timestamp_label=metadata.get("timestamp_label"),
                start_time=metadata.get("start_time"),
                end_time=metadata.get("end_time"),
                file_path=metadata.get("file_path"),
                language=metadata.get("language"),
                start_line=metadata.get("start_line"),
                end_line=metadata.get("end_line"),
                repo_owner=metadata.get("repo_owner"),
                repo_name=metadata.get("repo_name"),
                branch=metadata.get("branch"),
                file_url=(
                    f"https://github.com/{metadata.get('repo_owner')}/{metadata.get('repo_name')}/blob/{metadata.get('branch') or 'HEAD'}/{metadata.get('file_path')}#L{metadata.get('start_line')}-L{metadata.get('end_line')}"
                    if metadata.get("source_type") == "github" and metadata.get("file_path") and metadata.get("repo_owner") and metadata.get("repo_name") and metadata.get("chunk_kind") not in {"source_overview", "repo_overview"}
                    else None
                ),
            )
        )

    return "\n\n---\n\n".join(context_parts), citations


def answer_question(request: QuestionRequest) -> AnswerResponse:
    started_at = perf_counter()
    settings = get_settings()
    repo = get_supabase_repository()
    llm = get_llm_service()
    source_type = _resolve_source_type(request, repo)
    is_github_source = source_type == "github"
    effective_top_k = min(request.top_k, GITHUB_QA_TOP_K) if is_github_source else request.top_k
    search_top_k = min(max(effective_top_k * 2, effective_top_k), GITHUB_QA_MAX_SEARCH_RESULTS) if is_github_source else max(request.top_k * 2, request.top_k)
    max_context_chars = GITHUB_QA_MAX_CONTEXT_CHARS if is_github_source else DEFAULT_QA_MAX_CONTEXT_CHARS
    max_chunk_chars = GITHUB_QA_MAX_CHUNK_CHARS if is_github_source else DEFAULT_QA_MAX_CHUNK_CHARS

    retrieval_started = perf_counter()

    rewritten_query = request.question
    if should_rewrite(request.question):
        try:
            rewritten_query = llm.rewrite_query(request.question)
        except LLMServiceTimeoutError as exc:
            rewritten_query = request.question
            logger.warning("qa_rewrite_timeout source_type=%s top_k=%s", source_type or "unknown", effective_top_k)

    query_embedding = get_embedding_service().embed_query(rewritten_query)
    raw_chunks = get_vector_store().search(
        query_embedding=query_embedding,
        knowledgebase_id=request.knowledgebase_id,
        source_id=request.source_id,
        top_k=search_top_k,
    )
    retrieval_ms = (perf_counter() - retrieval_started) * 1000

    rerank_started = perf_counter()
    ranked_chunks = rerank_chunks(rewritten_query, raw_chunks)[:effective_top_k]
    rerank_ms = (perf_counter() - rerank_started) * 1000

    confidence = calculate_confidence(ranked_chunks)
    confidence_label, confidence_reason = confidence_label_and_reason(rewritten_query, ranked_chunks, confidence)

    follow_up_question = None
    llm_ms = 0.0
    context_chars = 0
    # If no chunks retrieved, we must refuse.
    if not ranked_chunks:
        answer = "I couldn't produce a reliable grounded answer from the selected source."
        context = ""
        citations: list[Citation] = []
        warnings = ["No relevant transcript evidence found."]
        follow_up_question = _build_follow_up_question(request.question, ranked_chunks)
    else:
        # For video sources, allow grounded answers even when confidence is low
        is_video = source_type == "video" or any((c.metadata.get("source_type") == "video" or c.metadata.get("chunk_kind") == "video_overview") for c in ranked_chunks)
        if request.mode == "grounded" and confidence < LOW_CONFIDENCE_THRESHOLD and not is_video:
            answer = "I couldn't produce a reliable grounded answer from the selected source."
            context = ""
            citations = []
            warnings = ["Low retrieval confidence. No grounded answer was generated."]
            follow_up_question = _build_follow_up_question(request.question, ranked_chunks)
        else:
            # Build context and produce an answer. For low-confidence video answers, include a caution warning but still return citations.
            context, citations = build_context(
                ranked_chunks,
                max_context_chars=max_context_chars,
                max_chunk_chars=max_chunk_chars,
            )
            context_chars = len(context)
            llm_started = perf_counter()
            try:
                answer = llm.generate_answer(question=request.question, context=context, mode=request.mode)
            except LLMServiceTimeoutError as exc:
                answer = str(exc)
                warnings = [str(exc)]
                llm_ms = (perf_counter() - llm_started) * 1000
                logger.warning("qa_llm_timeout source_type=%s top_k=%s context_chars=%s", source_type or "unknown", effective_top_k, context_chars)
            else:
                llm_ms = (perf_counter() - llm_started) * 1000
                warnings = []
            if confidence < 0.45:
                # for videos, produce a more descriptive warning
                if is_video:
                    warnings.append("Low confidence but transcript evidence exists. Verify citations.")
                else:
                    warnings.append("Answer is based on weak source matches. Verify citations carefully.")
    retrieved_sources = [
        {
            "chunk_id": c.chunk_id,
            "source_ref": c.metadata.get("source_ref"),
            "source_type": c.metadata.get("source_type"),
            "source_title": c.metadata.get("source_title"),
            "page_number": c.metadata.get("page_number"),
            "chunk_index": c.metadata.get("chunk_index"),
            "score": c.score,
            "snippet": make_snippet(c.text, 220),
            "video_id": c.metadata.get("video_id"),
            "timestamp_label": c.metadata.get("timestamp_label"),
            "start_time": c.metadata.get("start_time"),
            "end_time": c.metadata.get("end_time"),
            # GitHub metadata for UI
            "file_path": c.metadata.get("file_path"),
            "start_line": c.metadata.get("start_line"),
            "end_line": c.metadata.get("end_line"),
            "language": c.metadata.get("language"),
            "repo_owner": c.metadata.get("repo_owner"),
            "repo_name": c.metadata.get("repo_name"),
        }
        for c in ranked_chunks
    ]
    retrieved_source_count = len({str(c.metadata.get("source_id")) for c in ranked_chunks if c.metadata.get("source_id")})

    history_write_ms = 0.0
    if settings.store_query_history:
        history_started = perf_counter()
        try:
            future = _history_executor.submit(
                repo.save_query_history,
                knowledgebase_id=request.knowledgebase_id,
                source_id=request.source_id,
                question=request.question,
                rewritten_query=rewritten_query,
                mode=request.mode,
                answer=answer,
                confidence=confidence,
                retrieved_chunk_ids=[c.chunk_id for c in ranked_chunks],
            )
            future.result(timeout=settings.query_history_timeout_seconds)
        except FuturesTimeoutError:
            logger.warning("qa_history_write_timeout source_type=%s top_k=%s", source_type or "unknown", effective_top_k)
            warnings.append("Could not save query history.")
        except Exception:
            logger.warning("qa_history_write_failed source_type=%s top_k=%s", source_type or "unknown", effective_top_k, exc_info=True)
            # Query history must not break the user's answer.
            warnings.append("Could not save query history.")
        finally:
            history_write_ms = (perf_counter() - history_started) * 1000

    total_ms = (perf_counter() - started_at) * 1000
    logger.info(
        "qa_timing source_type=%s top_k=%s context_chars=%s retrieval_ms=%.1f rerank_ms=%.1f llm_ms=%.1f history_write_ms=%.1f total_ms=%.1f",
        source_type or "unknown",
        effective_top_k,
        context_chars,
        retrieval_ms,
        rerank_ms,
        llm_ms,
        history_write_ms,
        total_ms,
    )

    return AnswerResponse(
        answer=answer,
        mode=request.mode,
        question=request.question,
        rewritten_query=rewritten_query,
        confidence_score=confidence,
        confidence_label=confidence_label,
        confidence_reason=confidence_reason,
        retrieved_source_count=retrieved_source_count,
        citations=citations,
        retrieved_sources=retrieved_sources,
        follow_up_question=follow_up_question,
        warnings=warnings,
    )
