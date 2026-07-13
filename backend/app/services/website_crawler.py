"""
Website crawler using Playwright for rendering JavaScript-heavy sites.
Supports internal link following with domain restriction and duplicate detection.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Set
from urllib.parse import urljoin, urlparse, urlunparse
from collections import deque

from app.services.url_utils import assert_public_http_url, normalize_url
from app.utils.exceptions import (
    SourceExtractionError,
    UnsafeUrlError,
    WebsiteCrawlTimeoutError,
    WebsiteInvalidUrlError,
    WebsiteNoUsableTextError,
)
from app.core.config import get_settings


@dataclass
class CrawlSummary:
    """Summary of a website crawl operation."""
    starting_url: str
    normalized_url: str
    pages_attempted: int
    pages_successfully_ingested: int
    pages_skipped: int
    failed_pages: dict[str, str]  # URL -> error message
    total_chunks_created: int
    extraction_method: str = "playwright"
    warnings: list[str] = field(default_factory=list)


@dataclass
class CrawledPage:
    """A single page crawled from a website."""
    url: str
    normalized_url: str
    title: str
    text: str
    final_url: str


@dataclass
class WebExtractionResult:
    """Result from extracting a page using Playwright."""
    title: str
    text: str
    final_url: str
    links: list[str]
    warnings: list[str]


async def _check_playwright_installed() -> None:
    """Check if Playwright and Chromium are installed."""
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        raise SourceExtractionError(
            "Playwright is not installed. Install it with: pip install playwright && "
            "python -m playwright install chromium"
        )


async def extract_page_with_playwright(
    page, url: str, base_domain: str, settings, preferred_netloc: str | None = None
) -> WebExtractionResult:
    """
    Extract text and links from a page using Playwright.
    
    Args:
        page: Playwright page object
        url: URL to extract
        base_domain: Base domain for link filtering
        settings: Application settings
    
    Returns:
        WebExtractionResult with text, title, and internal links
    """
    warnings: list[str] = []

    # Fail fast on the starting URL; the route handler below also blocks any
    # redirect hop that lands on an internal/private address mid-navigation.
    assert_public_http_url(url)

    try:
        # Navigate with resource blocking for performance
        await page.route(
            "**/*",
            _handle_route
        )

        # Navigate to the page
        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=15000  # 15 second timeout
        )
    except UnsafeUrlError:
        raise
    except Exception as e:
        if "timeout" in str(e).lower() or "timed out" in str(e).lower():
            raise WebsiteCrawlTimeoutError() from e
        raise SourceExtractionError(f"Failed to navigate to {url}: {str(e)}")
    
    # Extract rendered text content
    try:
        text = await page.evaluate("document.body.innerText")
        text = " ".join(text.split())  # Normalize whitespace
    except Exception as e:
        raise SourceExtractionError(f"Failed to extract text from {url}: {str(e)}")
    
    # Extract title
    try:
        title = await page.title()
        if not title:
            title = await page.evaluate(
                "document.querySelector('h1')?.innerText || 'Website Source'"
            )
    except Exception:
        title = "Website Source"
    
    # Extract links for crawling
    links: list[str] = []
    try:
        link_elements = await page.query_selector_all("a[href]")
        for element in link_elements:
            href = await element.get_attribute("href")
            if href:
                try:
                    absolute_url = urljoin(url, href)
                    # Remove fragments
                    absolute_url = absolute_url.split("#")[0]
                    normalized = _normalize_page_url(absolute_url, base_domain)
                    if normalized:
                        links.append(_prefer_host_variant(normalized, preferred_netloc or base_domain, base_domain))
                except Exception:
                    pass  # Skip invalid URLs
    except Exception as e:
        warnings.append(f"Failed to extract links: {str(e)}")
    
    # Validate text length
    if len(text) > settings.max_website_chars:
        text = text[: settings.max_website_chars]
        warnings.append(
            f"Website text was truncated to {settings.max_website_chars} characters for MVP ingestion."
        )
    
    if len(text) < settings.min_source_text_chars:
        raise WebsiteNoUsableTextError()
    
    # Get final URL after redirects
    final_url = page.url
    
    return WebExtractionResult(
        title=title,
        text=text,
        final_url=final_url,
        links=links,
        warnings=warnings
    )


async def _handle_route(route) -> None:
    """
    Route handler to block unnecessary resources, and to block navigation
    (including mid-navigation redirects) to internal/private addresses.
    Allows: documents, scripts, XHR/fetch, stylesheets
    Blocks: images, fonts, media, videos, non-public document requests
    """
    request = route.request
    request_type = request.resource_type

    if request_type in ["image", "font", "media"]:
        await route.abort()
        return

    if request_type == "document":
        try:
            assert_public_http_url(request.url)
        except UnsafeUrlError:
            await route.abort()
            return

    await route.continue_()


def _normalize_page_url(url: str, base_domain: str) -> str | None:
    """
    Normalize a URL and return it if it belongs to the same domain.
    Returns None if the URL is external or invalid.
    """
    try:
        normalized = normalize_url(url)
        parsed = urlparse(normalized)
        # Only allow same domain
        if parsed.netloc == base_domain:
            return normalized
        return None
    except Exception:
        return None


def _prefer_host_variant(url: str, preferred_netloc: str, base_domain: str) -> str:
    try:
        parsed = urlparse(url)
        if parsed.netloc.lower() == base_domain and preferred_netloc and preferred_netloc != base_domain:
            return urlunparse((parsed.scheme, preferred_netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    except Exception:
        pass
    return url


async def crawl_website_async(
    starting_url: str,
    max_pages: int = 10,
    max_depth: int = 1,
) -> tuple[list[CrawledPage], CrawlSummary]:
    """
    Asynchronously crawl a website using Playwright.
    
    Args:
        starting_url: The URL to start crawling from
        max_pages: Maximum number of pages to crawl (default 10, max 100)
        max_depth: Maximum depth of crawl (default 1, max 3)
    
    Returns:
        Tuple of (crawled_pages, crawl_summary)
    
    Raises:
        SourceExtractionError: If Playwright is not installed or starting URL fails
    """
    # Check Playwright installation
    await _check_playwright_installed()
    
    from playwright.async_api import async_playwright
    
    # Validate parameters
    if max_pages < 1 or max_pages > 100:
        max_pages = min(max(max_pages, 1), 100)
    if max_depth < 1 or max_depth > 3:
        max_depth = min(max(max_depth, 1), 3)
    
    settings = get_settings()
    
    # Normalize the starting URL for dedupe, but keep the original host variant for navigation.
    try:
        normalized_start = normalize_url(starting_url)
    except Exception as e:
        raise WebsiteInvalidUrlError(f"Invalid starting URL: {str(e)}") from e
    
    navigation_start = str(starting_url).strip()
    parsed_start = urlparse(normalized_start)
    base_domain = parsed_start.netloc
    preferred_netloc = urlparse(navigation_start).netloc or base_domain
    
    if not base_domain:
        raise WebsiteInvalidUrlError("Invalid starting URL: no domain found")
    
    crawled_pages: list[CrawledPage] = []
    visited_urls: Set[str] = set()
    failed_pages: dict[str, str] = {}
    pages_skipped = 0
    all_warnings: list[str] = []
    
    # BFS queue: (url, depth)
    queue = deque([(navigation_start, 0)])
    visited_urls.add(normalized_start)
    
    # Launch browser once for all pages
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as e:
            if "Chromium" in str(e) or "not found" in str(e):
                raise SourceExtractionError(
                    "Playwright/Chromium is not installed. Run: python -m playwright install chromium"
                )
            raise SourceExtractionError(f"Browser error: {str(e)}")

        try:
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="SAGE-MVP/1.0 (+https://example.local) Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            )
            try:
                while queue and len(crawled_pages) < max_pages:
                    current_url, current_depth = queue.popleft()

                    # Create a new page for this request
                    page = await context.new_page()

                    try:
                        # Extract page content
                        result = await extract_page_with_playwright(
                            page, current_url, base_domain, settings, preferred_netloc
                        )

                        page_obj = CrawledPage(
                            url=current_url,
                            normalized_url=current_url,
                            title=result.title,
                            text=result.text,
                            final_url=result.final_url
                        )
                        crawled_pages.append(page_obj)
                        all_warnings.extend(result.warnings)

                        # Extract links if we haven't reached max depth
                        if current_depth < max_depth:
                            for link in result.links:
                                if link not in visited_urls and len(crawled_pages) < max_pages:
                                    visited_urls.add(link)
                                    queue.append((link, current_depth + 1))
                                elif link not in visited_urls:
                                    pages_skipped += 1

                    except SourceExtractionError as e:
                        failed_pages[current_url] = str(e)
                    except asyncio.TimeoutError:
                        failed_pages[current_url] = "Page load timeout"
                    except Exception as e:
                        failed_pages[current_url] = f"Unexpected error: {str(e)}"
                    finally:
                        await page.close()
            finally:
                await context.close()
        finally:
            await browser.close()
    
    summary = CrawlSummary(
        starting_url=starting_url,
        normalized_url=normalized_start,
        pages_attempted=len(crawled_pages) + len(failed_pages),
        pages_successfully_ingested=len(crawled_pages),
        pages_skipped=pages_skipped,
        failed_pages=failed_pages,
        total_chunks_created=0,  # Will be filled by ingestion pipeline
        warnings=all_warnings
    )
    
    return crawled_pages, summary


def crawl_website(
    starting_url: str,
    max_pages: int = 10,
    max_depth: int = 1,
) -> tuple[list[CrawledPage], CrawlSummary]:
    """
    Synchronous wrapper for async website crawling.
    
    This function runs the async crawler in a new event loop.
    """
    return asyncio.run(
        crawl_website_async(starting_url, max_pages, max_depth)
    )
