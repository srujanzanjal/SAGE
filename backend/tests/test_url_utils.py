from app.services.url_utils import normalize_url


def test_normalize_url_removes_www_trailing_slash_and_tracking_params():
    url = "HTTPS://www.Example.com/path/?utm_source=x&b=2&a=1"
    assert normalize_url(url) == "https://example.com/path?a=1&b=2"


def test_normalize_url_keeps_root_slash():
    assert normalize_url("https://www.example.com") == "https://example.com/"
