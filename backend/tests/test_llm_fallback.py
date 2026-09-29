import pytest

from app.core.config import Settings
from app.services import llm as llm_module
from app.services.llm import LLMService, LLMServiceTimeoutError, _ProviderError


def _service(monkeypatch, gemini, groq):
    service = object.__new__(LLMService)
    service.settings = Settings(GEMINI_API_KEY="g", GROQ_API_KEY="q", GROQ_FALLBACK_MODELS="")
    service.groq = object()
    service._cooldown_until = {}
    monkeypatch.setattr(service, "_gemini_complete", gemini)
    monkeypatch.setattr(service, "_groq_complete", groq)
    return service


def test_falls_back_to_groq_when_gemini_is_rate_limited(monkeypatch):
    def gemini(messages, model, t, n):
        raise _ProviderError("429", transient=True)

    service = _service(monkeypatch, gemini, lambda messages, model, t, n: f"answer from {model}")
    messages = [{"role": "user", "content": "q"}]
    assert service._complete(messages, temperature=0, max_tokens=10) == "answer from qwen/qwen3.8-27b"


def test_raises_friendly_error_when_every_provider_fails(monkeypatch):
    def fail(messages, model, t, n):
        raise _ProviderError("down", transient=True)

    monkeypatch.setattr(llm_module.time, "sleep", lambda s: None)
    service = _service(monkeypatch, fail, fail)
    with pytest.raises(LLMServiceTimeoutError, match="quota"):
        service._complete([{"role": "user", "content": "q"}], temperature=0, max_tokens=10)
