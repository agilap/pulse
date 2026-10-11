"""Session 8 — integration tests: incident lifecycle.

Per FR-09 and §12 incident state transition.
"""
import os
import subprocess
import sys
import time
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


def _create_monitor(url, interval=60):
    client = TestClient(app)
    resp = client.post("/api/v1/monitors", json={"url": url, "interval_seconds": interval})
    assert resp.status_code == 201
    return resp.json()


def _make_due(monitor_id):
    """Force a monitor due and clear its lease so the worker will reclaim it."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE monitors SET next_check_at = NOW() - INTERVAL '1 second', "
        "lease_until = NULL, lease_token = NULL WHERE id = %s",
        (monitor_id,),
    )
    conn.commit()
    cur.close()
    conn.close()


def _open_incident_count(monitor_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM incidents WHERE monitor_id = %s AND resolved_at IS NULL",
        (monitor_id,),
    )
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


def _total_incident_count(monitor_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM incidents WHERE monitor_id = %s", (monitor_id,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


def _incident_state(monitor_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT started_at, last_failure_at, resolved_at, failure_count_at_open "
        "FROM incidents WHERE monitor_id = %s ORDER BY id DESC LIMIT 1",
        (monitor_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def _consecutive_failures(monitor_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT consecutive_failures FROM monitors WHERE id = %s", (monitor_id,)
    )
    row = cur.fetchone()[0]
    cur.close()
    conn.close()
    return row


def setup_function():
    _setup_db()


def teardown_function():
    _wipe_db()
    close_pool()


class _NotFoundHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"not found")

    def log_message(self, *args, **kwargs):
        pass


class _OkHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args, **kwargs):
        pass


@pytest.fixture
def error_http_server():
    original = os.environ.get("PULSE_ALLOW_LOOPBACK", "")
    os.environ["PULSE_ALLOW_LOOPBACK"] = "1"
    server = HTTPServer(("127.0.0.1", 0), _NotFoundHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    if original:
        os.environ["PULSE_ALLOW_LOOPBACK"] = original
    else:
        os.environ.pop("PULSE_ALLOW_LOOPBACK", None)


@pytest.fixture
def ok_http_server():
    original = os.environ.get("PULSE_ALLOW_LOOPBACK", "")
    os.environ["PULSE_ALLOW_LOOPBACK"] = "1"
    server = HTTPServer(("127.0.0.1", 0), _OkHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    if original:
        os.environ["PULSE_ALLOW_LOOPBACK"] = original
    else:
        os.environ.pop("PULSE_ALLOW_LOOPBACK", None)


def test_no_incident_before_threshold(error_http_server):
    """Failures below the threshold must not open an incident."""
    m = _create_monitor(error_http_server, 60)

    for _ in range(2):  # threshold is 3
        _make_due(m["id"])
        run_check_cycle(worker_id="test-worker")
        time.sleep(0.1)

    assert _consecutive_failures(m["id"]) == 2
    assert _open_incident_count(m["id"]) == 0
    assert _total_incident_count(m["id"]) == 0


def test_incident_opens_on_third_failure(error_http_server):
    """Exactly three consecutive failures open one incident."""
    m = _create_monitor(error_http_server, 60)

    for _ in range(3):
        _make_due(m["id"])
        run_check_cycle(worker_id="test-worker")
        time.sleep(0.1)

    assert _consecutive_failures(m["id"]) == 3
    assert _open_incident_count(m["id"]) == 1
    assert _total_incident_count(m["id"]) == 1

    state = _incident_state(m["id"])
    assert state[0] is not None  # started_at
    assert state[1] is not None  # last_failure_at
    assert state[2] is None      # resolved_at — open
    assert state[3] == 3         # failure_count_at_open


def test_fourth_failure_does_not_open_duplicate(error_http_server):
    """Further failures extend the open incident; no duplicate is created."""
    m = _create_monitor(error_http_server, 60)

    for _ in range(5):  # well past the threshold of 3
        _make_due(m["id"])
        run_check_cycle(worker_id="test-worker")
        time.sleep(0.1)

    assert _consecutive_failures(m["id"]) == 5
    assert _open_incident_count(m["id"]) == 1
    assert _total_incident_count(m["id"]) == 1


def test_success_resolves_incident(error_http_server, ok_http_server):
    """A successful check resets the counter and resolves the open incident."""
    m = _create_monitor(error_http_server, 60)

    # 3 failures -> open incident
    for _ in range(3):
        _make_due(m["id"])
        run_check_cycle(worker_id="test-worker")
        time.sleep(0.1)
    assert _open_incident_count(m["id"]) == 1

    # Repoint the monitor at the healthy server, then succeed
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE monitors SET url = %s WHERE id = %s", (ok_http_server, m["id"])
    )
    conn.commit()
    cur.close()
    conn.close()

    _make_due(m["id"])
    run_check_cycle(worker_id="test-worker")

    assert _consecutive_failures(m["id"]) == 0
    assert _open_incident_count(m["id"]) == 0
    assert _total_incident_count(m["id"]) == 1

    state = _incident_state(m["id"])
    assert state[2] is not None  # resolved_at set


def test_new_incident_after_recovery_and_new_failure(
    error_http_server, ok_http_server
):
    """After a resolve, a fresh failure streak opens a new incident."""
    m = _create_monitor(error_http_server, 60)

    for _ in range(3):
        _make_due(m["id"])
        run_check_cycle(worker_id="test-worker")
        time.sleep(0.1)
    assert _open_incident_count(m["id"]) == 1

    # Recover
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE monitors SET url = %s WHERE id = %s", (ok_http_server, m["id"])
    )
    conn.commit()
    cur.close()
    conn.close()

    _make_due(m["id"])
    run_check_cycle(worker_id="test-worker")
    assert _open_incident_count(m["id"]) == 0

    # Fail again 3 times -> new incident
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE monitors SET url = %s WHERE id = %s", (error_http_server, m["id"])
    )
    conn.commit()
    cur.close()
    conn.close()

    for _ in range(3):
        _make_due(m["id"])
        run_check_cycle(worker_id="test-worker")
        time.sleep(0.1)

    assert _open_incident_count(m["id"]) == 1
    assert _total_incident_count(m["id"]) == 2  # one resolved, one open


def test_one_open_incident_constraint_enforced_by_db():
    """The partial unique index must prevent a second open incident."""
    m = _create_monitor("https://example.com", 60)
    conn = _connect()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO incidents (monitor_id, started_at, last_failure_at, "
        "failure_count_at_open) VALUES (%s, NOW(), NOW(), 3) RETURNING id",
        (m["id"],),
    )
    conn.commit()

    # Second open incident for the same monitor must violate the constraint
    with pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO incidents (monitor_id, started_at, last_failure_at, "
            "failure_count_at_open) VALUES (%s, NOW(), NOW(), 3)",
            (m["id"],),
        )
        conn.commit()

    conn.rollback()
    cur.close()
    conn.close()


def test_stale_worker_cannot_commit(error_http_server):
    """A worker whose lease was superseded must not persist a result."""
    from datetime import datetime, timezone

    from backend.app.db.queries import persist_check_result
    from backend.app.monitoring.checker import CheckOutcome, CheckResult

    m = _create_monitor(error_http_server, 60)

    # Claim the monitor legitimately, then simulate a newer claim stealing it
    from backend.app.worker.claim import claim_due_monitors

    claimed = claim_due_monitors(worker_id="worker-a")
    assert len(claimed) == 1
    token_a = claimed[0].lease_token

    # Worker B forcibly reclaims (expire the lease, then claim)
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE monitors SET lease_until = NOW() - INTERVAL '1 second' WHERE id = %s",
        (m["id"],),
    )
    conn.commit()
    cur.close()
    conn.close()

    claimed_b = claim_due_monitors(worker_id="worker-b")
    assert len(claimed_b) == 1
    assert claimed_b[0].lease_token != token_a

    # Worker A now tries to persist with its stale token — must be rejected
    result = CheckResult(
        outcome=CheckOutcome.http_error,
        status_code=404,
        latency_ms=10,
    )
    committed = persist_check_result(
        monitor_id=m["id"],
        claim_token=token_a,  # stale
        checked_at=datetime.now(timezone.utc),
        result=result,
        interval_seconds=60,
    )
    assert committed is False

    # And no check_result row was written by the stale worker
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM check_results WHERE monitor_id = %s", (m["id"],))
    assert cur.fetchone()[0] == 0
    cur.close()
    conn.close()
