import ipaddress
import os
from urllib.parse import urlsplit, urlunsplit

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}


def _is_test_loopback() -> bool:
    return os.environ.get("PULSE_ALLOW_LOOPBACK", "") == "1"


def _is_loopback_host(host: str) -> bool:
    """Check if a host string is a literal loopback address."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip in (ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1"))


class UrlPolicyError(ValueError):
    """Raised when a URL is structurally invalid or unsafe."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def parse_and_validate_url(raw_url: str) -> str:
    """Validate a URL string and return a normalized form.

    Raises UrlPolicyError with a machine-readable code on any rejection.
    """
    if not raw_url or not isinstance(raw_url, str):
        raise UrlPolicyError("invalid_url", "Enter an absolute HTTP or HTTPS URL.")

    # Strip whitespace — users paste with trailing spaces
    url = raw_url.strip()

    parts = urlsplit(url)

    # Scheme
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UrlPolicyError(
            "unsupported_scheme",
            "Only http and https URLs are supported.",
        )

    # No embedded credentials (userinfo)
    if parts.username or parts.password:
        raise UrlPolicyError(
            "embedded_credentials",
            "URLs containing usernames or passwords are not allowed.",
        )

    # Host is required
    host = parts.hostname
    if not host:
        raise UrlPolicyError(
            "missing_host",
            "URL must include a host.",
        )

    # Reject literal private/loopback IPs in the host field
    _reject_private_host(host)

    # Port enforcement (80/443 only, or scheme-default)
    port = parts.port
    if port is not None and port not in ALLOWED_PORTS:
        if not (_is_test_loopback() and _is_loopback_host(host)):
            raise UrlPolicyError(
                "prohibited_port",
                "Only ports 80 and 443 are supported.",
            )

    # Normalize: strip default ports, lowercase host, no trailing junk
    normalized = _normalize(parts, host, port, scheme)
    return normalized


def _reject_private_host(host: str) -> None:
    """Reject loopback, private, link-local, multicast, unallocated IPs."""
    try:
        # Try parsing as an IP literal
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Not an IP literal — DNS resolution + IP validation happens in worker
        return

    if not ip.is_global:
        # Test-only escape hatch for loopback addresses
        if _is_test_loopback() and ip in (
            ipaddress.ip_address("127.0.0.1"),
            ipaddress.ip_address("::1"),
        ):
            return
        raise UrlPolicyError(
            "blocked_destination",
            "The destination address is not a public address.",
        )


def _normalize(parts, host: str, port: int | None, scheme: str) -> str:
    """Produce a clean normalized URL (strip default port, lowercase host)."""
    # Remove default port for canonical form
    if port in (80, 443):
        netloc = host
    else:
        netloc = f"{host}:{port}" if port else host

    # Rebuild without userinfo, with lowercased scheme/host
    normalized = urlunsplit(
        (
            scheme,
            netloc,
            parts.path or "",
            parts.query,
            "",  # drop fragment
        )
    )
    return normalized
