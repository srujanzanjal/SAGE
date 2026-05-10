import re


def clean_whitespace(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def make_snippet(text: str, max_len: int = 420) -> str:
    text = clean_whitespace(text).replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def estimate_tokens(text: str) -> int:
    # Simple approximation good enough for metadata and UI.
    return max(1, len(text) // 4)
