import os
import subprocess
import sys

import psycopg
from fastapi.testclient import TestClient

from backend.app.db import close_pool, get_pool
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
    get_pool()  # pre-warm the app's connection pool


def _count_monitors():
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM monitors")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


def setup_function():
    _setup_db()


def teardown_function():
    _wipe_db()
    close_pool()


def test_create_monitor_valid():
    client = TestClient(app)
    before = _count_monitors()
    resp = client.post("/api/v1/monitors", json={"url": "https://example.com"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] > 0
    assert body["url"] == "https://example.com"
    assert body["interval_seconds"] == 60
    assert body["enabled"] is True
    assert "next_check_at" in body
    assert _count_monitors() == before + 1


def test_create_monitor_custom_interval():
    client = TestClient(app)
    resp = client.post(
        "/api/v1/monitors",
        json={"url": "https://example.com", "interval_seconds": 120},
    )
    assert resp.status_code == 201
    assert resp.json()["interval_seconds"] == 120
    assert _count_monitors() == 1


def test_create_monitor_rejects_unsupported_scheme():
    count_before = _count_monitors()
    client = TestClient(app)
    resp = client.post("/api/v1/monitors", json={"url": "ftp://example.com"})
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"]["code"] == "unsupported_scheme"
    assert _count_monitors() == count_before


def test_create_monitor_rejects_embedded_credentials():
    count_before = _count_monitors()
    client = TestClient(app)
    resp = client.post(
        "/api/v1/monitors", json={"url": "https://user:pass@example.com"}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"]["code"] == "embedded_credentials"
    assert _count_monitors() == count_before


def test_create_monitor_rejects_loopback_ip():
    count_before = _count_monitors()
    client = TestClient(app)
    resp = client.post("/api/v1/monitors", json={"url": "http://127.0.0.1"})
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"]["code"] == "blocked_destination"
    assert _count_monitors() == count_before


def test_create_monitor_rejects_private_ip():
    count_before = _count_monitors()
    client = TestClient(app)
    resp = client.post("/api/v1/monitors", json={"url": "https://192.168.1.1"})
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"]["code"] == "blocked_destination"
    assert _count_monitors() == count_before


def test_create_monitor_rejects_prohibited_port():
    count_before = _count_monitors()
    client = TestClient(app)
    resp = client.post("/api/v1/monitors", json={"url": "https://example.com:8080"})
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"]["code"] == "prohibited_port"
    assert _count_monitors() == count_before


def test_create_monitor_rejects_interval_too_high():
    count_before = _count_monitors()
    client = TestClient(app)
    resp = client.post(
        "/api/v1/monitors",
        json={"url": "https://example.com", "interval_seconds": 90000},
    )
    assert resp.status_code == 422
    assert _count_monitors() == count_before


def test_create_monitor_rejects_interval_too_low():
    count_before = _count_monitors()
    client = TestClient(app)
    resp = client.post(
        "/api/v1/monitors",
        json={"url": "https://example.com", "interval_seconds": 30},
    )
    assert resp.status_code == 422
    assert _count_monitors() == count_before


def test_create_monitor_strips_default_port():
    """https://example.com:443 normalizes to https://example.com."""
    client = TestClient(app)
    resp = client.post("/api/v1/monitors", json={"url": "https://example.com:443"})
    assert resp.status_code == 201
    assert resp.json()["url"] == "https://example.com"
