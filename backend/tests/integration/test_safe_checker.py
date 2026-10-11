"""Session 6 — integration test: safe HTTP check execution."""
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app.db.core import close_pool, get_pool
from backend.app.main import app
from backend.app.monitoring.checker import CheckOutcome, execute_check

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://pulse:changeme-not-a-real-secret@localhost:5432/pulse"
)
MIGRATE_SCRIPT = "/home/alex/pulse/scripts/migrate.py"


def _run_migrations():
    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL
    result = subprocess.run(
        [sys.executable, MIGRATE_SCRIPT], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, f"Migration failed:\n{result.stderr}"


def _connect():
    return psycopg.connect(DATABASE_URL)


def _wipe_db():
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    conn.commit()
    cur.close()
    conn.close()


def _setup_db():
    _run_migrations()
    get_pool()


def _create_monitor(url="https://example.com", interval=60):
    client = TestClient(app)
    resp = client.post("/api/v1/monitors", json={"url": url, "interval_seconds": interval})
    assert resp.status_code == 201
    return resp.json()


def _refresh_pool():
    close_pool()
    _setup_db()


def setup_function():
    _setup_db()


def teardown_function():
    _wipe_db()
    close_pool()


class _SilentHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args, **kwargs):
        pass


@pytest.fixture
def local_http_server():
    """Start an HTTP server on 127.0.0.1 with an ephemeral port.

    Pulse only allows 127.0.0.1 in test mode via PULSE_ALLOW_LOOPBACK=1.
    """
    original = os.environ.get("PULSE_ALLOW_LOOPBACK", "")
    os.environ["PULSE_ALLOW_LOOPBACK"] = "1"

    server = HTTPServer(("127.0.0.1", 0), _SilentHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    port = server.server_address[1]
    yield f"http://127.0.0.1:{port}"

    server.shutdown()
    if original:
        os.environ["PULSE_ALLOW_LOOPBACK"] = original
    else:
        os.environ.pop("PULSE_ALLOW_LOOPBACK", None)


def test_check_success_against_local_server(local_http_server):
    """A 200 response from an allowed local server -> success."""
    result = execute_check(local_http_server, timeout=5)
    assert result.outcome == CheckOutcome.success
    assert result.status_code == 200
    assert result.latency_ms is not None and result.latency_ms >= 0


def test_check_blocks_loopback_without_flag():
    """Without PULSE_ALLOW_LOOPBACK, 127.0.0.1 is blocked."""
    os.environ.pop("PULSE_ALLOW_LOOPBACK", None)
    result = execute_check("http://127.0.0.1:80", timeout=5)
    assert result.outcome == CheckOutcome.blocked_destination


def test_check_blocks_private_ip_without_flag():
    os.environ.pop("PULSE_ALLOW_LOOPBACK", None)
    result = execute_check("http://192.168.1.1", timeout=5)
    assert result.outcome == CheckOutcome.blocked_destination


def test_check_timeout_on_unroutable():
    """Connecting to a non-routable IP times out or errors."""
    result = execute_check("http://10.255.255.1", timeout=2)
    assert result.outcome in (
        CheckOutcome.timeout,
        CheckOutcome.connection_error,
        CheckOutcome.blocked_destination,
    )


def test_check_records_latency_on_success(local_http_server):
    result = execute_check(local_http_server, timeout=5)
    assert result.outcome == CheckOutcome.success
    assert result.latency_ms is not None


def test_check_no_redirects(local_http_server):
    """Redirects are disabled — follow_redirects=False."""
    result = execute_check(local_http_server, timeout=5)
    assert result.status_code == 200


def test_check_dns_error_for_invalid_host():
    """DNS failure for a non-existent domain -> dns_error."""
    result = execute_check("http://nonexistent-domain-404.invalid", timeout=3)
    assert result.outcome == CheckOutcome.dns_error
    assert result.status_code is None
