import os
import subprocess
import sys

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app.db.core import close_pool, get_pool
from backend.app.main import app
from backend.app.worker.claim import ClaimedMonitor, claim_due_monitors

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


def test_claim_due_monitor_sets_lease():
    _create_monitor("https://example.com", 60)
    _refresh_pool()

    claimed = claim_due_monitors(worker_id="worker-1")
    assert len(claimed) == 1
    c = claimed[0]
    assert isinstance(c, ClaimedMonitor)
    assert c.url == "https://example.com"
    assert c.lease_token is not None and len(c.lease_token) > 0

    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT lease_until, lease_token FROM monitors WHERE id = %s", (c.id,))
    row = cur.fetchone()
    assert row[1] == c.lease_token
    assert row[0] is not None
    cur.close()
    conn.close()


def test_claim_skips_monitor_with_live_lease():
    _create_monitor("https://example.com", 60)
    _refresh_pool()

    claimed = claim_due_monitors(worker_id="worker-1")
    assert len(claimed) == 1
    token1 = claimed[0].lease_token

    _refresh_pool()
    claimed2 = claim_due_monitors(worker_id="worker-2")
    assert len(claimed2) == 0, "Worker 2 should not claim a monitor with a live lease"

    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT lease_token FROM monitors WHERE id = %s", (claimed[0].id,))
    assert cur.fetchone()[0] == token1
    cur.close()
    conn.close()


def test_claim_reclaims_expired_lease():
    _create_monitor("https://example.com", 60)
    _refresh_pool()

    claimed = claim_due_monitors(worker_id="worker-1")
    assert len(claimed) == 1
    original_token = claimed[0].lease_token

    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE monitors SET lease_until = NOW() - INTERVAL '1 second' WHERE id = %s",
        (claimed[0].id,),
    )
    conn.commit()
    cur.close()
    conn.close()

    _refresh_pool()
    claimed2 = claim_due_monitors(worker_id="worker-2")
    assert len(claimed2) == 1
    assert claimed2[0].id == claimed[0].id
    assert claimed2[0].lease_token != original_token


def test_concurrent_workers_claim_disjoint_batches():
    for i in range(5):
        _create_monitor(f"https://site-{i}.com", 60)
    _refresh_pool()

    w1 = claim_due_monitors(worker_id="worker-1", limit=10)
    w2 = claim_due_monitors(worker_id="worker-2", limit=10)
    assert len(w2) == 0, "All due monitors claimed by worker-1; worker-2 should get none"
    assert len(w1) == 5


def test_claim_disabled_monitor_not_claimed():
    _create_monitor("https://example.com", 60)
    _refresh_pool()

    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE monitors SET enabled = FALSE WHERE id = 1")
    conn.commit()
    cur.close()
    conn.close()

    _refresh_pool()
    claimed = claim_due_monitors(worker_id="worker-1")
    assert len(claimed) == 0


def test_claim_not_due_monitor_not_claimed():
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO monitors (url, interval_seconds, next_check_at) "
        "VALUES (%s, %s, NOW() + INTERVAL '1 hour')",
        ("https://future.com", 60),
    )
    conn.commit()
    cur.close()
    conn.close()

    _refresh_pool()
    claimed = claim_due_monitors(worker_id="worker-1")
    assert len(claimed) == 0


def test_config_rejects_unsafe_lease():
    import importlib

    import backend.app.worker.config as worker_config

    old_timeout = os.environ.get("REQUEST_TIMEOUT_SECONDS")
    old_lease = os.environ.get("LEASE_DURATION_SECONDS")

    os.environ["REQUEST_TIMEOUT_SECONDS"] = "10"
    os.environ["LEASE_DURATION_SECONDS"] = "8"
    importlib.reload(worker_config)

    with pytest.raises(ValueError, match="must exceed"):
        worker_config.validate_worker_config()

    if old_timeout is not None:
        os.environ["REQUEST_TIMEOUT_SECONDS"] = old_timeout
    else:
        os.environ.pop("REQUEST_TIMEOUT_SECONDS", None)
    if old_lease is not None:
        os.environ["LEASE_DURATION_SECONDS"] = old_lease
    else:
        os.environ.pop("LEASE_DURATION_SECONDS", None)
    importlib.reload(worker_config)
