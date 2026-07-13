from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.schemas import AnswerResponse, QuestionRequest
from app.services.qa_pipeline import answer_question, format_sse_event, stream_answer_question

router = APIRouter(prefix="/qa", tags=["question-answering"])


def _require_a_source(payload: QuestionRequest) -> None:
    if not payload.knowledgebase_id and not payload.source_id and not payload.source_ids:
        raise HTTPException(status_code=400, detail="Provide knowledgebase_id, source_id, or source_ids.")


@router.post("/ask", response_model=AnswerResponse)
def ask_question(payload: QuestionRequest):
    _require_a_source(payload)
    try:
        return answer_question(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Question answering failed: {exc}") from exc


@router.post("/ask/stream")
def ask_question_stream(payload: QuestionRequest):
    _require_a_source(payload)

    def event_generator():
        try:
            yield from stream_answer_question(payload)
        except Exception as exc:
            # The stream may already be underway (200 sent), so errors surface
            # as an SSE event rather than an HTTP status code.
            yield format_sse_event("error", {"message": f"Question answering failed: {exc}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
