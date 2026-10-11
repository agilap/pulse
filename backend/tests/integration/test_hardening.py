"""Session 11 — integration tests: retention cleanup, concurrency, recovery."""
import os
import subprocess
import sys

import psycopg
from fastapi.testclient import TestClient

from backend.app.db.core import close_pool, get_pool
from backend.app.main import app
from backend.app.worker.check_loop import run_check_cycle
from backend.app.worker.retention import cleanup_expired_check_results

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


def _count_check_results():
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM check_results")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


def setup_function():
    _setup_db()


def teardown_function():
    _wipe_db()
    close_pool()


def test_retention_deletes_only_old_rows():
    """Rows older than the retention window are deleted; recent ones survive."""
    m = _create_monitor("https://example.com", 60)

    conn = _connect()
    cur = conn.cursor()
    # One old row (40 days ago), one fresh row
    cur.execute(
        "INSERT INTO check_results (monitor_id, checked_at, outcome) "
        "VALUES (%s, NOW() - INTERVAL '40 days', 'success'), "
        "        (%s, NOW(), 'success')",
        (m["id"], m["id"]),
    )
    conn.commit()
    cur.close()
    conn.close()

    assert _count_check_results() == 2

    deleted = cleanup_expired_check_results()
    assert deleted == 1
    assert _count_check_results() == 1


def test_retention_keeps_incidents():
    """Incident records remain until the monitor is deleted (FR-12)."""
    m = _create_monitor("https://example.com", 60)

    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO incidents (monitor_id, started_at, last_failure_at, "
        "failure_count_at_open) VALUES (%s, NOW(), NOW(), 3)",
        (m["id"],),
    )
    cur.execute(
        "INSERT INTO check_results (monitor_id, checked_at, outcome) "
        "VALUES (%s, NOW() - INTERVAL '40 days', 'timeout')",
        (m["id"],),
    )
    conn.commit()
    cur.close()
    conn.close()

    cleanup_expired_check_results()

    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM incidents WHERE monitor_id = %s", (m["id"],))
    assert cur.fetchone()[0] == 1
    cur.close()
    conn.close()


def test_retention_no_op_when_nothing_expired():
    m = _create_monitor("https://example.com", 60)
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO check_results (monitor_id, checked_at, outcome) "
        "VALUES (%s, NOW(), 'success')",
        (m["id"],),
    )
    conn.commit()
    cur.close()
    conn.close()

    deleted = cleanup_expired_check_results()
    assert deleted == 0


def test_two_workers_never_claim_same_monitor_twice():
    """FR-06: claim batches are disjoint — no double commit.

    Worker A claims up to worker_concurrency monitors (default 5) and
    commits them; worker B then gets the next batch and never re-claims
    what A already committed.
    """
    from backend.app.config import settings

    total = settings.worker_concurrency * 2  # more than one batch
    for i in range(total):
        _create_monitor(f"https://site-{i}.example.com", 60)

    a_checked = run_check_cycle(worker_id="worker-a")
    assert a_checked == settings.worker_concurrency

    b_checked = run_check_cycle(worker_id="worker-b")
    assert b_checked == settings.worker_concurrency

    # A third cycle finds nothing due — all committed and scheduled out
    c_checked = run_check_cycle(worker_id="worker-c")
    assert c_checked == 0

    # Exactly one result per monitor — no duplicates
    assert _count_check_results() == total


def test_expired_lease_recovered_by_second_worker():
    """FR-06/FR-14: a crashed worker's claim is reclaimed after lease expiry."""
    m = _create_monitor("https://example.com", 60)

    # Worker A claims it
    checked_a = run_check_cycle(worker_id="worker-a")
    assert checked_a == 1

    # Simulate worker A having crashed mid-flight: the check was never
    # persisted. Re-create that state — force due + stale lease.
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE monitors SET next_check_at = NOW() - INTERVAL '1 second', "
        "lease_until = NOW() - INTERVAL '1 second', "
        "lease_token = 'worker-a:crashed' WHERE id = %s",
        (m["id"],),
    )
    # Remove the result worker A would have written
    cur.execute("DELETE FROM check_results WHERE monitor_id = %s", (m["id"],))
    conn.commit()
    cur.close()
    conn.close()

    # Worker B reclaims and completes the check
    checked_b = run_check_cycle(worker_id="worker-b")
    assert checked_b == 1

    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT lease_token FROM monitors WHERE id = %s", (m["id"],))
    token = cur.fetchone()[0]
    cur.close()
    conn.close()

    # The stale worker's token is gone; worker B's claim was committed
    assert token != "worker-a:crashed"
    assert _count_check_results() == 1
