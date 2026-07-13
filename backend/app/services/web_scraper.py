from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.services.text_utils import clean_whitespace
from app.services.url_utils import assert_public_http_url
from app.utils.exceptions import SourceExtractionError, UnsafeUrlError

MAX_REDIRECTS = 5


@dataclass
class WebExtractionResult:
    title: str
    text: str
    final_url: str
    warnings: list[str]


REMOVE_SELECTORS = [
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "iframe",
    "nav",
    "footer",
    "header",
    "form",
    "button",
    "aside",
]


def extract_website_text(url: str) -> WebExtractionResult:
    settings = get_settings()
    headers = {
        "User-Agent": "SAGE-MVP/1.0 (+https://example.local) Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    # Validate the URL (and every redirect hop) against internal/private addresses
    # before fetching, so a same-domain-looking link can't SSRF via a redirect.
    current_url = str(url).strip()
    try:
        for _ in range(MAX_REDIRECTS + 1):
            assert_public_http_url(current_url)
            response = requests.get(
                current_url,
                headers=headers,
                timeout=settings.request_timeout_seconds,
                allow_redirects=False,
            )
            if response.is_redirect and response.headers.get("location"):
                current_url = urljoin(current_url, response.headers["location"])
                continue
            response.raise_for_status()
            break
        else:
            raise SourceExtractionError("Too many redirects while fetching website.")
    except UnsafeUrlError:
        raise
    except requests.RequestException as exc:
        raise SourceExtractionError(f"Could not fetch website: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower():
        raise SourceExtractionError(f"URL did not return HTML content. Content-Type: {content_type or 'unknown'}")

    soup = BeautifulSoup(response.text, "html.parser")
    for selector in REMOVE_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()

    title = clean_whitespace(soup.title.get_text(" ")) if soup.title else "Website Source"

    # Prefer article/main content, then fall back to body.
    candidates = []
    for selector in ["main", "article", "[role='main']", "body"]:
        node = soup.select_one(selector)
        if node:
            candidates.append(node.get_text("\n", strip=True))

    text = max(candidates, key=len) if candidates else soup.get_text("\n", strip=True)
    text = clean_whitespace(text)

    warnings: list[str] = []
    if len(text) > settings.max_website_chars:
        text = text[: settings.max_website_chars]
        warnings.append(f"Website text was truncated to {settings.max_website_chars} characters for MVP ingestion.")

    if len(text) < settings.min_source_text_chars:
        raise SourceExtractionError(
            "Website has too little extractable text. It may be JavaScript-heavy, protected, or mostly media."
        )

    return WebExtractionResult(title=title, text=text, final_url=str(response.url), warnings=warnings)
