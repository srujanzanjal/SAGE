import ipaddress
import socket
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.utils.exceptions import UnsafeUrlError

TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid"}

# Blocks the classic SSRF targets: loopback, private/RFC1918, link-local
# (this covers the 169.254.169.254 cloud metadata address), and friends.
_BLOCKED_HOSTNAMES = {"metadata.google.internal"}


def assert_public_http_url(url: str) -> None:
    """Raise UnsafeUrlError if `url` doesn't resolve to a public, fetchable address.

    Guards against SSRF: a user-supplied ingestion URL that points at the
    local machine, an internal network address, or a cloud metadata endpoint.
    """
    parsed = urlparse(str(url).strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"Unsupported URL scheme: {parsed.scheme or '(none)'}. Use http or https.")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeUrlError("URL has no hostname.")
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise UnsafeUrlError(f"Refusing to fetch blocked host: {hostname}")

    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Could not resolve host: {hostname}") from exc

    for _family, _type, _proto, _canonname, sockaddr in resolved:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise UnsafeUrlError(
                f"Refusing to fetch {hostname}: it resolves to a non-public address ({ip})."
            )


def normalize_url(url: str) -> str:
    """Normalize URL to prevent duplicate knowledgebases for the same page."""
    parsed = urlparse(str(url).strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()

    if netloc.startswith("www."):
        netloc = netloc[4:]

    # Remove default ports.
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    if scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")

    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        key_lower = key.lower()
        if key_lower in TRACKING_KEYS or any(key_lower.startswith(prefix) for prefix in TRACKING_PREFIXES):
            continue
        query_items.append((key, value))
    query = urlencode(sorted(query_items))

    return urlunparse((scheme, netloc, path, "", query, ""))


def safe_title_from_ref(ref: str, fallback: str = "Untitled Source") -> str:
    parsed = urlparse(ref)
    if parsed.netloc:
        path = parsed.path.strip("/")
        return f"{parsed.netloc}/{path}" if path else parsed.netloc
    return fallback
