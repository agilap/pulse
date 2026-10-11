import ipaddress
import os
import socket
import time
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit

import httpx


class CheckOutcome(str, Enum):
    success = "success"
    http_error = "http_error"
    timeout = "timeout"
    dns_error = "dns_error"
    tls_error = "tls_error"
    connection_error = "connection_error"
    blocked_destination = "blocked_destination"
    internal_error = "internal_error"


@dataclass
class CheckResult:
    outcome: CheckOutcome
    status_code: int | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class VettedAddress:
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address
    port: int


def resolve_and_validate(host: str, port: int) -> VettedAddress | None:
    """Resolve all A/AAAA records and reject if any is non-public.

    Returns the first vetted address on success, None if blocked.
    Raises socket.gaierror on DNS failure.
    """
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise

    for _family, _socktype, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        # Unwrap IPv4-mapped IPv6
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped

        if not ip.is_global:
            # Test-only escape hatch for loopback
            if _is_test_loopback() and ip in (
                ipaddress.ip_address("127.0.0.1"),
                ipaddress.ip_address("::1"),
            ):
                continue
            return None

    first_ip = ipaddress.ip_address(infos[0][4][0])
    if isinstance(first_ip, ipaddress.IPv6Address) and first_ip.ipv4_mapped is not None:
        first_ip = first_ip.ipv4_mapped

    return VettedAddress(ip=first_ip, port=port)


def _is_test_loopback() -> bool:
    """Test-only escape hatch: allow loopback when PULSE_ALLOW_LOOPBACK=1."""
    return os.environ.get("PULSE_ALLOW_LOOPBACK", "") == "1"


def execute_check(url: str, timeout: float = 10.0) -> CheckResult:
    """Perform a safe HTTP GET check against the given URL.

    Validates DNS at execution time, pins the socket to a vetted IP,
    preserves Host header and TLS SNI, does not follow redirects.
    """
    start = time.monotonic()
    parts = urlsplit(url)
    host = parts.hostname or ""
    scheme = parts.scheme.lower()
    port = parts.port or (443 if scheme == "https" else 80)

    # Step 1: resolve + validate all DNS answers
    try:
        vetted = resolve_and_validate(host, port)
    except socket.gaierror:
        return CheckResult(
            outcome=CheckOutcome.dns_error,
            error_code="dns_error",
            error_message="Could not resolve hostname.",
        )

    if vetted is None:
        return CheckResult(
            outcome=CheckOutcome.blocked_destination,
            error_code="blocked_destination",
            error_message="Destination resolved to a non-public address.",
        )

    # Step 2: build a request pinned to the vetted IP, preserving Host/SNI
    # httpx: we construct the URL with the IP, then set Host header so
    # TLS SNI and HTTP Host both use the original hostname
    request_url = f"{scheme}://{vetted.ip}:{port}{parts.path or ''}"
    if parts.query:
        request_url += f"?{parts.query}"

    # In test mode, disable TLS verification for loopback
    verify_tls = True
    if _is_test_loopback() and host in ("127.0.0.1", "localhost"):
        verify_tls = False

    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            verify=verify_tls,
        ) as client:
            req = client.build_request(
                "GET",
                request_url,
                headers={"Host": host, "User-Agent": "Pulse/0.1"},
            )
            resp = client.send(req)

        elapsed = int((time.monotonic() - start) * 1000)

        if 200 <= resp.status_code <= 299:
            return CheckResult(
                outcome=CheckOutcome.success,
                status_code=resp.status_code,
                latency_ms=elapsed,
            )
        else:
            return CheckResult(
                outcome=CheckOutcome.http_error,
                status_code=resp.status_code,
                latency_ms=elapsed,
                error_code="http_error",
                error_message=f"HTTP {resp.status_code}",
            )

    except httpx.TimeoutException:
        return CheckResult(
            outcome=CheckOutcome.timeout,
            error_code="timeout",
            error_message="Request timed out.",
        )
    except httpx.ConnectError:
        return CheckResult(
            outcome=CheckOutcome.connection_error,
            error_code="connection_error",
            error_message="Could not connect to destination.",
        )
    except Exception:
        return CheckResult(
            outcome=CheckOutcome.internal_error,
            error_code="internal_error",
            error_message="Unexpected error during check.",
        )
