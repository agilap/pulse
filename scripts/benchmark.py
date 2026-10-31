import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient

from backend.app.db.core import close_pool, get_pool
from backend.app.main import app

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://pulse:changeme-not-a-real-secret@localhost:5432/pulse"
)
MIGRATE_SCRIPT = str(Path(__file__).resolve().parents[1] / "scripts" / "migrate.py")
MONITOR_COUNT = 50
REQUESTS_PER_ENDPOINT = 100


def _migrate():
    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL
    subprocess.run(
        [sys.executable, MIGRATE_SCRIPT], capture_output=True, text=True, env=env, check=True
    )


def _wipe():
    conn = psycopg.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    conn.commit()
    cur.close()
    conn.close()


def _seed(client):
    for i in range(MONITOR_COUNT):
        client.post(
            "/api/v1/monitors",
            json={"url": f"https://bench-{i}.example.com", "interval_seconds": 60},
        )


def _measure(client, method, path):
    samples = []
    for _ in range(REQUESTS_PER_ENDPOINT):
        start = time.perf_counter()
        resp = client.request(method, path)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"
        samples.append(elapsed_ms)
    return samples


def _report(name, samples):
    samples_sorted = sorted(samples)
    p50 = samples_sorted[len(samples) // 2]
    p95 = samples_sorted[int(len(samples) * 0.95)]
    mean = statistics.mean(samples)
    print(f"  {name}: p50={p50:.1f}ms p95={p95:.1f}ms mean={mean:.1f}ms "
          f"min={min(samples):.1f}ms max={max(samples):.1f}ms")
    return p50, p95


def run_benchmark():
    print("=" * 60)
    print("Pulse benchmark")
    print("=" * 60)
    print(f"Machine: {platform.machine()}")
    print(f"Platform: {platform.platform()}")
    print(f"Python: {platform.python_version()}")
    print(f"Dataset: {MONITOR_COUNT} monitors")
    print(f"Requests per endpoint: {REQUESTS_PER_ENDPOINT}")
    print("-" * 60)

    _wipe()
    _migrate()
    get_pool()

    client = TestClient(app)
    _seed(client)

    list_samples = _measure(client, "GET", "/api/v1/monitors")
    detail_samples = _measure(client, "GET", "/api/v1/monitors/1")
    checks_samples = _measure(client, "GET", "/api/v1/monitors/1/checks")

    print("Results:")
    _report("GET /api/v1/monitors", list_samples)
    _report("GET /api/v1/monitors/{id}", detail_samples)
    _report("GET /api/v1/monitors/{id}/checks", checks_samples)

    print("-" * 60)
    print("Target: p95 < 300ms for CRUD/list operations.")

    close_pool()


if __name__ == "__main__":
    run_benchmark()
