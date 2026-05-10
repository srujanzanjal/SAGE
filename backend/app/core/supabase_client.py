from functools import lru_cache
from typing import Any

from app.core.config import get_settings


@lru_cache
def get_supabase_client() -> Any:
    """Create one Supabase client per process.

    Import is intentionally lazy so pure unit tests can import repository modules
    without requiring the Supabase SDK until a real DB call is made.
    """
    try:
        from supabase import create_client
        from supabase.lib.client_options import SyncClientOptions
    except ImportError as exc:
        raise RuntimeError("supabase is not installed. Run: pip install -r backend/requirements.txt") from exc

    settings = get_settings()
    settings.require_supabase()
    options = SyncClientOptions(postgrest_client_timeout=settings.request_timeout_seconds)
    return create_client(settings.supabase_url, settings.supabase_key, options=options)  # type: ignore[arg-type]
