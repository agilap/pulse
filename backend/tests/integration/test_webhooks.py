import hashlib
import hmac
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app.db.core import close_pool, get_pool
from backend.app.main import app
from backend.app.worker.check_loop import run_check_cycle
from backend.app.worker.webhook_dispatch import run_webhook_delivery_cycle

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://pulse:changeme-not-a-real-secret@localhost:5432/pulse"
)
MIGRATE_SCRIPT = str(Path(__file__).resolve().parents[3] / "scripts" / "migrate.py")


def _run_migrations():
    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL
    result = subprocess.run(
        [sys.executable, MIGRATE_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"Migration failed:\n{result.stderr}"


def _connect():
    return psycopg.connect(DATABASE_URL)


def _wipe_db():
    conn = _connect()
    conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    conn.commit()
    conn.close()


def setup_function():
    _run_migrations()
    get_pool()


def teardown_function():
    _wipe_db()
    close_pool()


def _create_monitor(url: str):
    response = TestClient(app).post(
        "/api/v1/monitors",
        json={"url": url, "interval_seconds": 60},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _make_due(monitor_id: int):
    with _connect() as conn:
        conn.execute(
            """
            UPDATE monitors
            SET next_check_at = NOW() - INTERVAL '1 second',
                lease_until = NULL,
                lease_token = NULL
            WHERE id = %s
            """,
            (monitor_id,),
        )
        conn.commit()


@pytest.fixture
def webhook_receiver():
    original = os.environ.get("PULSE_ALLOW_LOOPBACK")
    os.environ["PULSE_ALLOW_LOOPBACK"] = "1"

    class Handler(BaseHTTPRequestHandler):
        response_status = 200
        received = []

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            self.__class__.received.append((dict(self.headers), body))
            self.send_response(self.__class__.response_status)
            self.end_headers()

        def log_message(self, *args, **kwargs):
            pass

    Handler.received = []
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield {
        "url": f"http://127.0.0.1:{server.server_address[1]}/pulse-events",
        "handler": Handler,
    }

    server.shutdown()
    server.server_close()
    if original is None:
        os.environ.pop("PULSE_ALLOW_LOOPBACK", None)
    else:
        os.environ["PULSE_ALLOW_LOOPBACK"] = original


@pytest.fixture
def failure_server(webhook_receiver):
    class Handler(BaseHTTPRequestHandler):
        response_status = 503

        def do_GET(self):
            self.send_response(self.__class__.response_status)
            self.end_headers()
            self.wfile.write(b"service unavailable")

        def log_message(self, *args, **kwargs):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield {
        "url": f"http://127.0.0.1:{server.server_address[1]}",
        "handler": Handler,
    }

    server.shutdown()
    server.server_close()


def _create_webhook(url: str, event_types=None):
    payload = {"name": "Local test receiver", "url": url}
    if event_types is not None:
        payload["event_types"] = event_types
    response = TestClient(app).post("/api/v1/webhooks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _open_incident(monitor_id: int):
    for _ in range(3):
        _make_due(monitor_id)
        assert run_check_cycle("test-check-worker") == 1

    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM incidents WHERE monitor_id = %s AND resolved_at IS NULL",
            (monitor_id,),
        ).fetchone()
    assert row is not None
    return row[0]


def test_webhook_endpoint_lifecycle_and_secret_is_only_returned_once(webhook_receiver):
    client = TestClient(app)

    rejected = client.post(
        "/api/v1/webhooks",
        json={"name": "Insecure", "url": "http://example.com/hook"},
    )
    assert rejected.status_code == 422

    created = _create_webhook(webhook_receiver["url"])
    assert created["enabled"] is True
    assert created["has_secret"] is True
    assert len(created["secret"]) >= 32

    listed = client.get("/api/v1/webhooks")
    assert listed.status_code == 200
    assert "secret" not in listed.json()[0]

    updated = client.patch(
        f"/api/v1/webhooks/{created['id']}",
        json={"name": "Renamed receiver", "enabled": False},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed receiver"
    assert updated.json()["enabled"] is False

    deleted = client.delete(f"/api/v1/webhooks/{created['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/v1/webhooks").json()[0]["enabled"] is False


def test_incident_open_and_recovery_create_transactional_events(
    webhook_receiver,
    failure_server,
):
    endpoint = _create_webhook(webhook_receiver["url"])
    monitor = _create_monitor(failure_server["url"])
    incident_id = _open_incident(monitor["id"])

    with _connect() as conn:
        opened = conn.execute(
            """
            SELECT e.event_type, e.payload, d.status
            FROM notification_events e
            JOIN webhook_deliveries d ON d.event_id = e.id
            WHERE e.incident_id = %s
            ORDER BY e.created_at
            """,
            (incident_id,),
        ).fetchall()

    assert len(opened) == 1
    assert opened[0][0] == "incident.opened"
    assert opened[0][1]["incident"]["id"] == incident_id
    assert opened[0][1]["monitor"]["id"] == monitor["id"]
    assert opened[0][2] == "pending"

    failure_server["handler"].response_status = 200
    _make_due(monitor["id"])
    assert run_check_cycle("test-check-worker") == 1

    with _connect() as conn:
        events = conn.execute(
            """
            SELECT e.event_type, d.status
            FROM notification_events e
            JOIN webhook_deliveries d ON d.event_id = e.id
            WHERE e.incident_id = %s
            ORDER BY e.created_at
            """,
            (incident_id,),
        ).fetchall()

    assert [row[0] for row in events] == ["incident.opened", "incident.resolved"]
    assert all(row[1] == "pending" for row in events)

    history = TestClient(app).get(
        f"/api/v1/webhooks/{endpoint['id']}/deliveries"
    )
    assert history.status_code == 200
    assert len(history.json()) == 2


def test_dispatch_retries_and_signs_webhook_payload(webhook_receiver, failure_server):
    created = _create_webhook(webhook_receiver["url"])
    monitor = _create_monitor(failure_server["url"])
    _open_incident(monitor["id"])

    webhook_receiver["handler"].response_status = 503
    assert run_webhook_delivery_cycle("test-delivery-worker") == 1

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, status, attempt_count, last_error_code
            FROM webhook_deliveries
            WHERE endpoint_id = %s
            """,
            (created["id"],),
        ).fetchone()
        assert row[1] == "pending"
        assert row[2] == 1
        assert row[3] == "receiver_error"
        conn.execute(
            """
            UPDATE webhook_deliveries
            SET next_attempt_at = NOW() - INTERVAL '1 second'
            WHERE id = %s
            """,
            (row[0],),
        )
        conn.commit()

    webhook_receiver["handler"].response_status = 204
    assert run_webhook_delivery_cycle("test-delivery-worker") == 1

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT d.status, d.attempt_count, e.event_type, e.payload
            FROM webhook_deliveries d
            JOIN notification_events e ON e.id = d.event_id
            WHERE d.endpoint_id = %s
            """,
            (created["id"],),
        ).fetchone()
        attempts = conn.execute(
            """
            SELECT attempt_number, outcome
            FROM webhook_delivery_attempts
            WHERE delivery_id = (
                SELECT id FROM webhook_deliveries WHERE endpoint_id = %s
            )
            ORDER BY attempt_number
            """,
            (created["id"],),
        ).fetchall()

    assert row[0] == "delivered"
    assert row[1] == 2
    assert [attempt[0] for attempt in attempts] == [1, 2]
    assert [attempt[1] for attempt in attempts] == ["retrying", "delivered"]

    headers, body = webhook_receiver["handler"].received[-1]
    payload = json.loads(body)
    expected = hmac.new(
        created["secret"].encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    assert payload["type"] == "incident.opened"
    assert headers["X-Pulse-Event"] == "incident.opened"
    assert headers["X-Pulse-Event-ID"] == payload["id"]
    assert headers["X-Pulse-Signature"] == f"sha256={expected}"


def test_disabling_endpoint_cancels_pending_deliveries(webhook_receiver, failure_server):
    created = _create_webhook(webhook_receiver["url"])
    monitor = _create_monitor(failure_server["url"])
    _open_incident(monitor["id"])

    response = TestClient(app).delete(f"/api/v1/webhooks/{created['id']}")
    assert response.status_code == 204

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT status, last_error_code, lease_token
            FROM webhook_deliveries
            WHERE endpoint_id = %s
            """,
            (created["id"],),
        ).fetchone()

    assert row == ("failed", "endpoint_disabled", None)
    assert run_webhook_delivery_cycle("test-delivery-worker") == 0
