"""Integration test: migrations apply cleanly on a fresh database."""
import os
import subprocess
import sys

import psycopg
import pytest

MIGRATE_SCRIPT = "/home/alex/pulse/scripts/migrate.py"
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://pulse:changeme-not-a-real-secret@localhost:5432/pulse"
)


def _run_migrations():
    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL
    result = subprocess.run(
        [sys.executable, MIGRATE_SCRIPT], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, f"Migration failed:\n{result.stderr}"


def _connect():
    return psycopg.connect(DATABASE_URL)


@pytest.fixture()
def fresh_db():
    # Wipe + re-migrate for a clean baseline
    _run_migrations()
    yield
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    conn.commit()
    cur.close()
    conn.close()


def test_tables_exist(fresh_db):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT tablename FROM pg_tables WHERE schemaname = 'public'
        ORDER BY tablename
    """)
    tables = [row[0] for row in cur.fetchall()]
    assert "monitors" in tables
    assert "check_results" in tables
    assert "schema_migrations" in tables
    cur.close()
    conn.close()


def test_monitors_columns(fresh_db):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'monitors'
        ORDER BY ordinal_position
    """)
    cols = {row[0]: row[1] for row in cur.fetchall()}
    assert cols["url"] == "text"
    assert cols["interval_seconds"] == "integer"
    assert cols["next_check_at"].replace("with time zone", "tz") == "timestamp tz"
    assert cols["lease_until"].replace("with time zone", "tz") == "timestamp tz"
    assert cols["lease_token"] == "text"
    assert cols["consecutive_failures"] == "integer"
    cur.close()
    conn.close()


def test_monitors_indexes(fresh_db):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT indexname FROM pg_indexes WHERE tablename = 'monitors'
    """)
    indexes = [row[0] for row in cur.fetchall()]
    assert "idx_monitors_due" in indexes
    assert "idx_monitors_lease" in indexes
    cur.close()
    conn.close()


def test_check_results_fk(fresh_db):
    conn = _connect()
    cur = conn.cursor()
    # Insert a monitor
    cur.execute(
        "INSERT INTO monitors (url, interval_seconds) VALUES (%s, %s) RETURNING id",
        ("https://example.com", 60),
    )
    monitor_id = cur.fetchone()[0]
    # Insert a check result referencing it — should succeed
    cur.execute(
        "INSERT INTO check_results (monitor_id, outcome, latency_ms) VALUES (%s, %s, %s)",
        (monitor_id, "success", 42),
    )
    conn.commit()

    # Insert referencing a non-existent monitor — should fail (FK constraint)
    cur.execute("BEGIN")
    try:
        cur.execute(
            "INSERT INTO check_results (monitor_id, outcome) VALUES (%s, %s)",
            (999999, "success"),
        )
        pytest.fail("FK constraint not enforced")
    except psycopg.errors.ForeignKeyViolation:
        conn.rollback()

    # Cascade delete: deleting monitor should remove its check_results
    cur.execute("DELETE FROM monitors WHERE id = %s", (monitor_id,))
    cur.execute("SELECT COUNT(*) FROM check_results WHERE monitor_id = %s", (monitor_id,))
    assert cur.fetchone()[0] == 0
    conn.commit()
    cur.close()
    conn.close()


def test_interval_constraint(fresh_db):
    conn = _connect()
    cur = conn.cursor()
    # Below minimum interval
    cur.execute("BEGIN")
    try:
        cur.execute(
            "INSERT INTO monitors (url, interval_seconds) VALUES (%s, %s)",
            ("https://example.com", 30),
        )
        pytest.fail("CHECK constraint not enforced for interval < min")
    except psycopg.errors.CheckViolation:
        conn.rollback()

    # Above maximum interval
    cur.execute("BEGIN")
    try:
        cur.execute(
            "INSERT INTO monitors (url, interval_seconds) VALUES (%s, %s)",
            ("https://example.com", 90000),
        )
        pytest.fail("CHECK constraint not enforced for interval > max")
    except psycopg.errors.CheckViolation:
        conn.rollback()
    cur.close()
    conn.close()
