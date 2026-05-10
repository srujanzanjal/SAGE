from fastapi import APIRouter, HTTPException

from app.models.schemas import AnswerResponse, QuestionRequest
from app.services.qa_pipeline import answer_question

router = APIRouter(prefix="/qa", tags=["question-answering"])


@router.post("/ask", response_model=AnswerResponse)
def ask_question(payload: QuestionRequest):
    if not payload.knowledgebase_id and not payload.source_id:
        raise HTTPException(status_code=400, detail="Provide knowledgebase_id or source_id.")
    try:
        return answer_question(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Question answering failed: {exc}") from exc
