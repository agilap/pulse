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


def _create(client, url="https://example.com", interval=60):
    resp = client.post(
        "/api/v1/monitors", json={"url": url, "interval_seconds": interval}
    )
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


def setup_function():
    _setup_db()


def teardown_function():
    _wipe_db()
    close_pool()


class _NotFoundHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"not found")

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


def test_create_returns_status_field():
    client = TestClient(app)
    m = _create(client)
    assert m["status"] == "pending"  # never checked


def test_status_pending_then_down_after_failures(error_http_server):
    client = TestClient(app)
    m = _create(client, error_http_server, 60)
    assert m["status"] == "pending"

    for _ in range(3):
        _make_due(m["id"])
        run_check_cycle(worker_id="test-worker")
        time.sleep(0.1)

    resp = client.get(f"/api/v1/monitors/{m['id']}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "down"


def test_patch_updates_interval():
    client = TestClient(app)
    m = _create(client)
    resp = client.patch(
        f"/api/v1/monitors/{m['id']}", json={"interval_seconds": 300}
    )
    assert resp.status_code == 200
    assert resp.json()["interval_seconds"] == 300


def test_patch_disable_and_enable():
    client = TestClient(app)
    m = _create(client)

    resp = client.patch(f"/api/v1/monitors/{m['id']}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    resp = client.patch(f"/api/v1/monitors/{m['id']}", json={"enabled": True})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True
    # next_check_at should be recent (due promptly)
    from datetime import datetime, timezone
    next_check = datetime.fromisoformat(resp.json()["next_check_at"].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - next_check).total_seconds()
    assert age < 10


def test_patch_rejects_invalid_interval():
    client = TestClient(app)
    m = _create(client)
    resp = client.patch(
        f"/api/v1/monitors/{m['id']}", json={"interval_seconds": 10}
    )
    assert resp.status_code == 422


def test_patch_unknown_returns_404():
    client = TestClient(app)
    resp = client.patch("/api/v1/monitors/999999", json={"enabled": False})
    assert resp.status_code == 404


def test_delete_removes_monitor_and_history(error_http_server):
    client = TestClient(app)
    m = _create(client, error_http_server, 60)

    _make_due(m["id"])
    run_check_cycle(worker_id="test-worker")

    # Confirm a check result exists
    resp = client.get(f"/api/v1/monitors/{m['id']}/checks")
    assert len(resp.json()) == 1

    resp = client.delete(f"/api/v1/monitors/{m['id']}")
    assert resp.status_code == 204

    # Gone
    resp = client.get(f"/api/v1/monitors/{m['id']}")
    assert resp.status_code == 404

    # History cascaded away
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM check_results WHERE monitor_id = %s", (m["id"],)
    )
    assert cur.fetchone()[0] == 0
    cur.close()
    conn.close()


def test_delete_unknown_returns_404():
    client = TestClient(app)
    resp = client.delete("/api/v1/monitors/999999")
    assert resp.status_code == 404


def test_check_history_returns_records(error_http_server):
    client = TestClient(app)
    m = _create(client, error_http_server, 60)

    for _ in range(2):
        _make_due(m["id"])
        run_check_cycle(worker_id="test-worker")
        time.sleep(0.1)

    resp = client.get(f"/api/v1/monitors/{m['id']}/checks")
    assert resp.status_code == 200
    checks = resp.json()
    assert len(checks) == 2
    assert checks[0]["outcome"] == "http_error"
    assert checks[0]["status_code"] == 404


def test_check_history_404_for_unknown_monitor():
    client = TestClient(app)
    resp = client.get("/api/v1/monitors/999999/checks")
    assert resp.status_code == 404


def test_check_history_bounded():
    """Limit is capped at 100."""
    client = TestClient(app)
    m = _create(client)
    resp = client.get(f"/api/v1/monitors/{m['id']}/checks?limit=500")
    assert resp.status_code == 200


def test_incident_history_returns_incident(error_http_server):
    client = TestClient(app)
    m = _create(client, error_http_server, 60)

    for _ in range(3):
        _make_due(m["id"])
        run_check_cycle(worker_id="test-worker")
        time.sleep(0.1)

    resp = client.get(f"/api/v1/monitors/{m['id']}/incidents")
    assert resp.status_code == 200
    incidents = resp.json()
    assert len(incidents) == 1
    assert incidents[0]["resolved_at"] is None
    assert incidents[0]["failure_count_at_open"] == 3


def test_list_incidents_open_filter(error_http_server):
    client = TestClient(app)
    m = _create(client, error_http_server, 60)

    for _ in range(3):
        _make_due(m["id"])
        run_check_cycle(worker_id="test-worker")
        time.sleep(0.1)

    resp = client.get("/api/v1/incidents?state=open")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["url"] is not None

    resp = client.get("/api/v1/incidents?state=resolved")
    assert resp.status_code == 200
    assert len(resp.json()) == 0


def test_list_incidents_rejects_bad_state():
    client = TestClient(app)
    resp = client.get("/api/v1/incidents?state=bogus")
    assert resp.status_code == 422


def test_health_ready_ok():
    client = TestClient(app)
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_health_live_ok():
    client = TestClient(app)
    resp = client.get("/health/live")
    assert resp.status_code == 200


def test_summary_counts_by_status():
    """The list endpoint exposes per-monitor status for dashboard summary."""
    client = TestClient(app)
    _create(client, "https://a.example.com")
    _create(client, "https://b.example.com")

    resp = client.get("/api/v1/monitors")
    statuses = [m["status"] for m in resp.json()]
    assert statuses == ["pending", "pending"]
