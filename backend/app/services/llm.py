import logging
from functools import lru_cache

import groq

from app.core.config import get_settings


logger = logging.getLogger(__name__)


class LLMServiceTimeoutError(RuntimeError):
    pass


class LLMService:
    def __init__(self) -> None:
        settings = get_settings()
        settings.require_groq()
        self.settings = settings
        try:
            from groq import Groq
        except ImportError as exc:
            raise RuntimeError("groq is not installed. Run: pip install -r backend/requirements.txt") from exc
        self.client = Groq(api_key=settings.groq_api_key, timeout=settings.llm_timeout_seconds, max_retries=1)

    def _is_timeout_exception(self, exc: Exception) -> bool:
        return isinstance(exc, (groq.APITimeoutError, groq.APIConnectionError, TimeoutError))

    def _raise_timeout_error(self, exc: Exception) -> None:
        raise LLMServiceTimeoutError("LLM provider timed out. Please try again.") from exc

    def rewrite_query(self, question: str) -> str:
        prompt = (
            "Rewrite the user question into a clear retrieval search query. "
            "Preserve the user's intent. Do not add facts. Return only the rewritten query."
        )
        try:
            response = self.client.chat.completions.create(
                model=self.settings.groq_model,
                temperature=0.0,
                max_tokens=80,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": question},
                ],
                timeout=self.settings.llm_timeout_seconds,
            )
            rewritten = response.choices[0].message.content or question
            rewritten = rewritten.strip().strip('"')
            return rewritten if rewritten else question
        except Exception as exc:
            if self._is_timeout_exception(exc):
                self._raise_timeout_error(exc)
            return question

    def generate_answer(self, *, question: str, context: str, mode: str) -> str:
        if mode == "grounded":
            system_prompt = """
You are SAGE, a source-grounded AI assistant.
Answer ONLY using the supplied source context.
Use citation markers like [S1], [S2] wherever you rely on a source.
If the answer is not available in the source context, say: "Not available in the provided source."
Do not invent details, URLs, names, dates, or numbers.
Keep the answer clear and concise.
""".strip()
        else:
            system_prompt = """
You are SAGE, an AI assistant with two clearly separated answer sections.
First write "Source-based answer:" and answer using only the supplied source context with citation markers like [S1].
Then write "General explanation:" and provide broader helpful explanation only if useful.
Clearly label anything not directly supported by the source as general explanation.
Do not pretend unsupported claims are from the source.
""".strip()

        user_prompt = f"""
Question:
{question}

Source context:
{context}
""".strip()

        response = self.client.chat.completions.create(
            model=self.settings.groq_model,
            temperature=0.1 if mode == "grounded" else 0.3,
            max_tokens=900,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=self.settings.llm_timeout_seconds,
        )
        return (response.choices[0].message.content or "").strip()


@lru_cache(maxsize=1)
def get_llm_service() -> LLMService:
    return LLMService()


def should_rewrite(question: str) -> bool:
    words = [w for w in question.strip().split() if w]
    vague_terms = {"fees", "contact", "about", "deadline", "eligibility", "cost", "price", "summary"}
    return len(words) <= 5 or question.strip().lower().rstrip("?") in vague_terms
