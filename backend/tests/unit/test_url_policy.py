"""Unit tests: URL policy + IP validation logic — no network."""
import ipaddress

import pytest

from backend.app.monitoring.checker import resolve_and_validate
from backend.app.monitoring.url_policy import UrlPolicyError, parse_and_validate_url


@pytest.mark.parametrize("url", [
    "https://example.com",
    "http://example.com",
    "https://sub.example.com/path?query=1",
    "https://Example.COM",
])
def test_valid_urls_accepted(url):
    result = parse_and_validate_url(url)
    assert result.startswith("http://") or result.startswith("https://")
    assert "username" not in result


@pytest.mark.parametrize("url", [
    "ftp://example.com",
    "javascript:alert(1)",
    "file:///etc/passwd",
])
def test_invalid_schemes_rejected(url):
    with pytest.raises(UrlPolicyError) as exc_info:
        parse_and_validate_url(url)
    assert exc_info.value.code == "unsupported_scheme"


def test_empty_url_rejected():
    with pytest.raises(UrlPolicyError) as exc_info:
        parse_and_validate_url("")
    assert exc_info.value.code == "invalid_url"


def test_embedded_credentials_rejected():
    with pytest.raises(UrlPolicyError) as exc_info:
        parse_and_validate_url("https://user:pass@example.com")
    assert exc_info.value.code == "embedded_credentials"


def test_username_only_rejected():
    with pytest.raises(UrlPolicyError) as exc_info:
        parse_and_validate_url("https://user@example.com")
    assert exc_info.value.code == "embedded_credentials"


@pytest.mark.parametrize("ip_url", [
    "http://127.0.0.1",
    "https://127.0.0.1",
])
def test_loopback_literal_rejected(ip_url):
    with pytest.raises(UrlPolicyError) as exc_info:
        parse_and_validate_url(ip_url)
    assert exc_info.value.code == "blocked_destination"


@pytest.mark.parametrize("ip_url", [
    "https://10.0.0.1",
    "https://192.168.1.1",
    "https://172.16.0.1",
    "https://169.254.1.1",
    "https://[::1]",
    "https://[fc00::1]",
    "https://[fe80::1]",
])
def test_private_and_reserved_ips_rejected(ip_url):
    with pytest.raises(UrlPolicyError) as exc_info:
        parse_and_validate_url(ip_url)
    assert exc_info.value.code == "blocked_destination"


@pytest.mark.parametrize("ip_url", [
    "https://example.com:8080",
    "https://example.com:22",
    "http://example.com:3000",
    "https://example.com:9000",
])
def test_non_standard_ports_rejected(ip_url):
    with pytest.raises(UrlPolicyError) as exc_info:
        parse_and_validate_url(ip_url)
    assert exc_info.value.code == "prohibited_port"


@pytest.mark.parametrize("ip_url", [
    "http://example.com:80",
    "https://example.com:443",
    "http://example.com",
    "https://example.com",
])
def test_standard_ports_accepted(ip_url):
    result = parse_and_validate_url(ip_url)
    assert ":80" not in result
    assert ":443" not in result


def test_missing_host_rejected():
    with pytest.raises(UrlPolicyError) as exc_info:
        parse_and_validate_url("https://")
    assert exc_info.value.code == "missing_host"


def test_normalizes_to_lowercase_scheme():
    result = parse_and_validate_url("HTTPS://Example.COM/Path")
    assert result.startswith("https://")
    host_part = result.split("//")[1].split("/")[0]
    assert host_part == host_part.lower()


def test_ipv4_mapped_ipv6_rejected():
    """::ffff:127.0.0.1 should be rejected as loopback."""
    with pytest.raises(UrlPolicyError) as exc_info:
        parse_and_validate_url("https://[::ffff:127.0.0.1]")
    assert exc_info.value.code == "blocked_destination"


# --- Checker IP validation unit tests ---


def test_resolve_and_validate_all_safe():
    import socket

    def mock_public(host, port, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port)),
        ]

    original = socket.getaddrinfo
    socket.getaddrinfo = mock_public
    try:
        result = resolve_and_validate("example.com", 443)
        assert result is not None
        assert str(result.ip) == "1.1.1.1"
    finally:
        socket.getaddrinfo = original


def test_resolve_and_validate_blocks_loopback():
    import socket

    def mock_loopback(host, port, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port)),
        ]

    original = socket.getaddrinfo
    socket.getaddrinfo = mock_loopback
    try:
        result = resolve_and_validate("evil.local", 443)
        assert result is None
    finally:
        socket.getaddrinfo = original


def test_resolve_and_validate_blocks_when_any_ip_is_private():
    import socket

    def mock_mixed(host, port, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port)),
        ]

    original = socket.getaddrinfo
    socket.getaddrinfo = mock_mixed
    try:
        result = resolve_and_validate("evil.local", 443)
        assert result is None
    finally:
        socket.getaddrinfo = original


def test_resolve_and_validate_raises_on_dns_error():
    import socket

    def mock_fail(host, port, **kwargs):
        raise socket.gaierror("DNS failure")

    original = socket.getaddrinfo
    socket.getaddrinfo = mock_fail
    try:
        with pytest.raises(socket.gaierror):
            resolve_and_validate("nonexistent.invalid", 443)
    finally:
        socket.getaddrinfo = original


def test_ipv4_mapped_ipv6_validation():
    """::ffff:10.0.0.1 should be treated as private 10.0.0.1."""
    ip = ipaddress.ip_address("::ffff:10.0.0.1")
    assert ip.ipv4_mapped is not None
    assert not ip.ipv4_mapped.is_global
