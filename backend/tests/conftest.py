import pytest
import os
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import get_settings
from app.core.supabase_client import get_supabase_client

@pytest.fixture(scope="session")
def client():
    """FastAPI TestClient."""
    return TestClient(app)

@pytest.fixture(scope="session")
def settings():
    """Settings configuration."""
    return get_settings()

@pytest.fixture(scope="session")
def supabase_client():
    """Supabase client for test setup/teardown."""
    return get_supabase_client()

@pytest.fixture
def test_website_url():
    """A real public website for testing."""
    return "https://www.python.org/about/"

@pytest.fixture
def test_invalid_url():
    """An invalid URL for testing error handling."""
    return "https://invalid-domain-that-does-not-exist-12345.com/page"

@pytest.fixture
def test_short_text_url():
    """A URL that might return minimal text (for testing rejection)."""
    return "https://example.com"  # Example.com is minimal

@pytest.fixture
def sample_pdf_path():
    """Path to sample test PDF."""
    return os.path.join(os.path.dirname(__file__), "assets", "sample.pdf")

@pytest.fixture
def blank_pdf_bytes():
    """Generate a blank PDF for testing."""
    try:
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes
    except ImportError:
        # Fallback: return empty bytes if fitz not available
        # This will test that our PDF validation properly rejects empty/invalid PDFs
        return b""
