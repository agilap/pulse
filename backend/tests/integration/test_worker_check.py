import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app.db.core import close_pool, get_pool
from backend.app.main import app
from backend.app.worker.check_loop import run_check_cycle

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


def _count_check_results():
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM check_results")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


def _get_monitor(monitor_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT last_outcome, last_status_code, next_check_at, "
        "consecutive_failures, lease_token FROM monitors WHERE id = %s",
        (monitor_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


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


class _NotFoundHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"not found")

    def log_message(self, *args, **kwargs):
        pass


@pytest.fixture
def local_http_server():
    original = os.environ.get("PULSE_ALLOW_LOOPBACK", "")
    os.environ["PULSE_ALLOW_LOOPBACK"] = "1"

    server = HTTPServer(("127.0.0.1", 0), _SilentHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    if original:
        os.environ["PULSE_ALLOW_LOOPBACK"] = original
    else:
        os.environ.pop("PULSE_ALLOW_LOOPBACK", None)


@pytest.fixture
def error_http_server():
    original = os.environ.get("PULSE_ALLOW_LOOPBACK", "")
    os.environ["PULSE_ALLOW_LOOPBACK"] = "1"

    server = HTTPServer(("127.0.0.1", 0), _NotFoundHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    if original:
        os.environ["PULSE_ALLOW_LOOPBACK"] = original
    else:
        os.environ.pop("PULSE_ALLOW_LOOPBACK", None)


def _create_monitor(url, interval=60):
    client = TestClient(app)
    resp = client.post("/api/v1/monitors", json={"url": url, "interval_seconds": interval})
    assert resp.status_code == 201
    return resp.json()


def test_worker_persists_success_result(local_http_server):
    m = _create_monitor(local_http_server, 60)
    before = _count_check_results()

    checked = run_check_cycle(worker_id="test-worker")
    assert checked == 1
    assert _count_check_results() == before + 1

    row = _get_monitor(m["id"])
    assert row[0] == "success"   # last_outcome
    assert row[1] == 200         # last_status_code
    assert row[2] is not None    # next_check_at advanced
    assert row[3] == 0          # consecutive_failures reset
    assert row[4] is None       # lease_token cleared


def test_worker_persists_http_error_result(error_http_server):
    m = _create_monitor(error_http_server, 60)
    before = _count_check_results()

    checked = run_check_cycle(worker_id="test-worker")
    assert checked == 1
    assert _count_check_results() == before + 1

    row = _get_monitor(m["id"])
    assert row[0] == "http_error"
    assert row[1] == 404
    assert row[3] == 1  # consecutive_failures incremented


def test_worker_increments_consecutive_failures(error_http_server):
    # Use the 404 server — each check produces an http_error
    m = _create_monitor(error_http_server, 60)

    conn = _connect()
    cur = conn.cursor()
    for _ in range(4):
        # Make the monitor due now (in case it was scheduled out)
        cur.execute(
            "UPDATE monitors SET next_check_at = NOW() - INTERVAL '1 second' "
            "WHERE id = %s",
            (m["id"],),
        )
        # Clear any existing lease so the worker can reclaim
        cur.execute(
            "UPDATE monitors SET lease_until = NULL, lease_token = NULL WHERE id = %s",
            (m["id"],),
        )
        conn.commit()

        run_check_cycle(worker_id="test-worker")
        time.sleep(0.1)

    cur.close()
    conn.close()

    row = _get_monitor(m["id"])
    assert row[0] == "http_error"  # last_outcome
    assert row[3] == 4  # consecutive_failures
    assert _count_check_results() == 4


def test_worker_advances_next_check_at(local_http_server):
    m = _create_monitor(local_http_server, 120)
    # next_check_at is already NOW() from INSERT — but the worker sets it
    # to checked_at + 120s after the check
    run_check_cycle(worker_id="test-worker")

    row = _get_monitor(m["id"])
    next_check = row[2]
    assert next_check is not None
    # next_check should be ~120s in the future
    now = datetime.now(timezone.utc)
    delta = (next_check - now).total_seconds()
    assert 100 < delta <= 120


def test_worker_clears_lease_on_completion(local_http_server):
    m = _create_monitor(local_http_server, 60)
    run_check_cycle(worker_id="test-worker")

    row = _get_monitor(m["id"])
    assert row[4] is None  # lease_token cleared


def test_worker_does_not_reclaim_during_live_lease(local_http_server):
    m = _create_monitor(local_http_server, 3600)

    # First cycle claims + checks it
    run_check_cycle(worker_id="worker-a")

    # next_check_at is now ~3600s out — monitor not due
    row = _get_monitor(m["id"])
    assert row[2] is not None
    assert row[4] is None  # lease cleared

    # Second cycle should not claim it (not due)
    checked = run_check_cycle(worker_id="worker-b")
    assert checked == 0
