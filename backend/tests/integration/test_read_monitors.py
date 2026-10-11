"""Session 4 — integration tests: GET /api/v1/monitors + /{id}."""
import os
import subprocess
import sys

import psycopg
from fastapi.testclient import TestClient

from backend.app.db.core import close_pool, get_pool
from backend.app.main import app

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
    resp = client.post(
        "/api/v1/monitors", json={"url": url, "interval_seconds": interval}
    )
    assert resp.status_code == 201
    return resp.json()


def setup_function():
    _setup_db()


def teardown_function():
    _wipe_db()
    close_pool()


def test_list_returns_empty_when_no_monitors():
    client = TestClient(app)
    resp = client.get("/api/v1/monitors")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_returns_created_monitor():
    created = _create_monitor("https://example.com", 60)
    client = TestClient(app)
    resp = client.get("/api/v1/monitors")
    assert resp.status_code == 200
    monitors = resp.json()
    assert len(monitors) == 1
    assert monitors[0]["id"] == created["id"]
    assert monitors[0]["url"] == "https://example.com"
    assert monitors[0]["enabled"] is True


def test_list_returns_stable_order():
    m1 = _create_monitor("https://site-a.com")
    m2 = _create_monitor("https://site-b.com")
    client = TestClient(app)
    resp = client.get("/api/v1/monitors")
    monitors = resp.json()
    ids = [m["id"] for m in monitors]
    # ORDER BY id DESC — most recent first
    assert ids == [m2["id"], m1["id"]]


def test_get_monitor_by_id():
    created = _create_monitor("https://example.com", 120)
    client = TestClient(app)
    resp = client.get(f"/api/v1/monitors/{created['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == created["id"]
    assert body["url"] == "https://example.com"
    assert body["interval_seconds"] == 120
    assert body["enabled"] is True
    assert "created_at" in body
    assert "next_check_at" in body


def test_get_monitor_not_found():
    client = TestClient(app)
    resp = client.get("/api/v1/monitors/999999")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "not_found"


def test_get_monitor_non_integer_id():
    client = TestClient(app)
    resp = client.get("/api/v1/monitors/not-a-number")
    assert resp.status_code == 422


def test_list_bounded_to_100():
    client = TestClient(app)
    for i in range(105):
        client.post(
            "/api/v1/monitors",
            json={"url": f"https://site-{i}.com", "interval_seconds": 60},
        )
    resp = client.get("/api/v1/monitors")
    assert resp.status_code == 200
    assert len(resp.json()) == 100
