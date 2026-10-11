from datetime import datetime, timedelta

from backend.app.db.core import get_conn
from backend.app.monitoring.checker import CheckResult


def select_monitors(limit: int = 100):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, url, interval_seconds, enabled,
                   created_at, updated_at, next_check_at,
                   last_checked_at, last_outcome, last_status_code,
                   consecutive_failures
            FROM monitors
            ORDER BY id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return rows


def select_monitor(monitor_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, url, interval_seconds, enabled,
                   created_at, updated_at, next_check_at,
                   last_checked_at, last_outcome, last_status_code,
                   consecutive_failures
            FROM monitors
            WHERE id = %s
            """,
            (monitor_id,),
        ).fetchone()
    return row


def insert_check_result(
    monitor_id: int,
    checked_at: datetime,
    result: CheckResult,
) -> int:
    """Insert a check result row. Returns the new check_results.id.

    All sensitive data is excluded — only outcome, status_code, latency,
    and sanitized error fields are persisted. No URL query strings,
    no response bodies, no request headers.
    """
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO check_results
                (monitor_id, checked_at, outcome, status_code, latency_ms,
                 error_code, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                monitor_id,
                checked_at,
                result.outcome.value,
                result.status_code,
                result.latency_ms,
                result.error_code,
                result.error_message,
            ),
        ).fetchone()
        conn.commit()
    return row[0]


def update_monitor_after_check(
    monitor_id: int,
    claim_token: str,
    checked_at: datetime,
    result: CheckResult,
    interval_seconds: int,
) -> None:
    """Atomically update monitor summary fields, clear lease, schedule next check.

    Uses optimistic locking: only updates WHERE lease_token = %s,
    so a stale worker with an old token cannot overwrite a newer claim.
    """
    is_success = result.outcome.value == "success"
    next_check = checked_at + timedelta(seconds=interval_seconds)

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE monitors
            SET last_checked_at = %s,
                last_outcome = %s,
                last_status_code = %s,
                next_check_at = %s,
                lease_until = NULL,
                lease_token = NULL,
                consecutive_failures = CASE
                    WHEN %s THEN 0
                    ELSE consecutive_failures + 1
                END,
                updated_at = NOW()
            WHERE id = %s
              AND (lease_token = %s OR lease_token IS NULL)
            """,
            (
                checked_at,
                result.outcome.value,
                result.status_code,
                next_check,
                is_success,
                monitor_id,
                claim_token,
            ),
        )
        conn.commit()
