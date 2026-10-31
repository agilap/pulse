import hashlib
import hmac
import ipaddress
import json
import os
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from backend.app.monitoring.checker import resolve_and_validate
from backend.app.monitoring.url_policy import UrlPolicyError, parse_and_validate_url


@dataclass
class WebhookSendResult:
    delivered: bool
    retryable: bool
    status_code: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None


def _is_loopback_host(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback


def parse_and_validate_webhook_url(raw_url: str) -> str:
    """Require HTTPS for webhook destinations, except test-only loopback URLs."""
    try:
        parts = urlsplit(raw_url.strip())
        port = parts.port
    except (AttributeError, ValueError):
        raise UrlPolicyError("invalid_url", "Enter a valid absolute webhook URL.") from None

    host = parts.hostname or ""
    scheme = parts.scheme.lower()
    test_http = (
        scheme == "http"
        and os.environ.get("PULSE_ALLOW_LOOPBACK", "") == "1"
        and _is_loopback_host(host)
    )

    if scheme != "https" and not test_http:
        raise UrlPolicyError(
            "https_required",
            "Webhook destinations must use HTTPS.",
        )

    if scheme == "https" and port not in (None, 443):
        raise UrlPolicyError(
            "prohibited_port",
            "HTTPS webhook destinations must use port 443.",
        )

    return parse_and_validate_url(raw_url)


def send_webhook(
    *,
    url: str,
    secret: str,
    event_id: str,
    delivery_id: int,
    event_type: str,
    payload: dict,
    timeout: float,
) -> WebhookSendResult:
    """POST a signed event to a DNS-validated, IP-pinned webhook destination.

    Redirects and environment proxies are disabled. A webhook response body is
    deliberately not retained because it may contain sensitive receiver data.
    """
    started = time.monotonic()
    parts = urlsplit(url)
    host = parts.hostname or ""
    scheme = parts.scheme.lower()
    port = parts.port or (443 if scheme == "https" else 80)

    try:
        vetted = resolve_and_validate(host, port)
    except socket.gaierror:
        return WebhookSendResult(
            delivered=False,
            retryable=True,
            error_code="dns_error",
            error_message="Could not resolve webhook hostname.",
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    if vetted is None:
        return WebhookSendResult(
            delivered=False,
            retryable=False,
            error_code="blocked_destination",
            error_message="Webhook destination resolved to a non-public address.",
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    ip_host = str(vetted.ip)
    if isinstance(vetted.ip, ipaddress.IPv6Address):
        ip_host = f"[{ip_host}]"

    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    request_url = f"{scheme}://{ip_host}:{port}{path}"

    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    host_header = host if port in (80, 443) else f"{host}:{port}"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Pulse/0.2",
        "Host": host_header,
        "X-Pulse-Event": event_type,
        "X-Pulse-Event-ID": str(event_id),
        "X-Pulse-Delivery": str(delivery_id),
        "X-Pulse-Signature": f"sha256={digest}",
    }
    extensions = {}
    if scheme == "https":
        extensions["sni_hostname"] = host.encode("idna")

    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            request = client.build_request(
                "POST",
                request_url,
                content=body,
                headers=headers,
                extensions=extensions,
            )
            response = client.send(request)

        duration_ms = int((time.monotonic() - started) * 1000)
        status_code = response.status_code

        if 200 <= status_code < 300:
            return WebhookSendResult(
                delivered=True,
                retryable=False,
                status_code=status_code,
                duration_ms=duration_ms,
            )

        if status_code in (408, 425, 429) or status_code >= 500:
            return WebhookSendResult(
                delivered=False,
                retryable=True,
                status_code=status_code,
                error_code="receiver_error",
                error_message=f"Webhook receiver returned HTTP {status_code}.",
                duration_ms=duration_ms,
            )

        error_code = "redirect_not_allowed" if 300 <= status_code < 400 else "receiver_rejected"
        return WebhookSendResult(
            delivered=False,
            retryable=False,
            status_code=status_code,
            error_code=error_code,
            error_message=f"Webhook receiver returned HTTP {status_code}.",
            duration_ms=duration_ms,
        )

    except httpx.TimeoutException:
        return WebhookSendResult(
            delivered=False,
            retryable=True,
            error_code="timeout",
            error_message="Webhook request timed out.",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except httpx.HTTPError:
        return WebhookSendResult(
            delivered=False,
            retryable=True,
            error_code="network_error",
            error_message="Could not deliver webhook request.",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception:
        return WebhookSendResult(
            delivered=False,
            retryable=True,
            error_code="internal_error",
            error_message="Unexpected error while delivering webhook.",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
