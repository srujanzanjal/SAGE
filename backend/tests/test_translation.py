from app.services import translation


def test_detect_language_identifies_english():
    text = "This is a normal English sentence about a college engineering project, written at reasonable length."
    assert translation.detect_language(text) == "en"


def test_detect_language_identifies_hindi():
    text = "यह एक कॉलेज इंजीनियरिंग परियोजना के बारे में एक सामान्य वाक्य है और यह पर्याप्त रूप से लंबा है।"
    assert translation.detect_language(text) == "hi"


def test_detect_language_identifies_spanish():
    text = "Esta es una oración normal en español sobre un proyecto de ingeniería universitaria, escrita con longitud razonable."
    assert translation.detect_language(text) == "es"


def test_detect_language_returns_none_for_short_text():
    assert translation.detect_language("hi") is None
    assert translation.detect_language("") is None


def test_is_english_true_for_english_and_undetectable_text():
    assert translation.is_english("This is clearly a long enough English sentence to detect confidently.") is True
    assert translation.is_english("ok") is True  # too short to detect -> treated as English (no translation attempted)


def test_is_english_false_for_non_english():
    text = "Esta es una oración normal en español sobre un proyecto de ingeniería universitaria."
    assert translation.is_english(text) is False


def test_translate_if_needed_skips_english_without_calling_llm():
    # No LLM available in this test process at all -- if translate_if_needed
    # tried to reach it for English text, this would raise/hang rather than
    # short-circuit cleanly, since detection alone must gate the LLM call.
    text = "This is a perfectly normal English paragraph that should not trigger any translation call at all."
    result_text, detected, segments_ok, truncated = translation.translate_if_needed(text)
    assert result_text == text
    assert detected is None
    assert segments_ok is True
    assert truncated is False


def test_translate_if_needed_calls_llm_for_non_english(monkeypatch):
    captured = {}

    class FakeLLM:
        def translate_to_english(self, text, source_language=None):
            captured["text"] = text
            captured["source_language"] = source_language
            return "This is the translated English text.", True, False

    import app.services.llm as llm_module
    monkeypatch.setattr(llm_module, "get_llm_service", lambda: FakeLLM())

    spanish_text = "Esta es una oración normal en español sobre un proyecto de ingeniería universitaria."
    result_text, detected, segments_ok, truncated = translation.translate_if_needed(spanish_text)
    assert result_text == "This is the translated English text."
    assert detected == "es"
    assert segments_ok is True
    assert truncated is False
    assert captured["source_language"] == "es"


def test_translate_if_needed_reports_segment_failure_separately_from_truncation(monkeypatch):
    class FlakyLLM:
        def translate_to_english(self, text, source_language=None):
            return text, False, False  # simulates a provider error, not truncation

    import app.services.llm as llm_module
    monkeypatch.setattr(llm_module, "get_llm_service", lambda: FlakyLLM())

    spanish_text = "Esta es una oración normal en español sobre un proyecto de ingeniería universitaria."
    result_text, detected, segments_ok, truncated = translation.translate_if_needed(spanish_text)
    assert result_text == spanish_text
    assert detected == "es"
    assert segments_ok is False
    assert truncated is False


def test_translate_if_needed_reports_truncation_separately_from_failure(monkeypatch):
    class TruncatingLLM:
        def translate_to_english(self, text, source_language=None):
            return "translated head only", True, True  # all attempted segments ok, but page was too long

    import app.services.llm as llm_module
    monkeypatch.setattr(llm_module, "get_llm_service", lambda: TruncatingLLM())

    spanish_text = "Esta es una oración normal en español sobre un proyecto de ingeniería universitaria."
    result_text, detected, segments_ok, truncated = translation.translate_if_needed(spanish_text)
    assert result_text == "translated head only"
    assert detected == "es"
    assert segments_ok is True
    assert truncated is True
