from datetime import datetime, timedelta

from backend.app.config import settings
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


def persist_check_result(
    monitor_id: int,
    claim_token: str,
    checked_at: datetime,
    result: CheckResult,
    interval_seconds: int,
) -> bool:
    """Persist a check result atomically with monitor updates and incident transitions.

    FR-09: result insert, counter/summary update, and incident open/resolve
    happen in ONE transaction so displayed state can never contradict the
    stored result. If the DB write fails, everything rolls back together.

    Optimistic locking (WHERE lease_token = %s) means a stale worker whose
    lease was superseded cannot commit — returns False in that case.

    Returns True if committed, False if the claim was no longer current.
    """
    is_success = result.outcome.value == "success"
    threshold = settings.failure_threshold
    next_check = checked_at + timedelta(seconds=interval_seconds)

    with get_conn() as conn:
        # Read current state inside the transaction we will write in.
        row = conn.execute(
            "SELECT consecutive_failures FROM monitors WHERE id = %s FOR UPDATE",
            (monitor_id,),
        ).fetchone()
        if row is None:
            conn.rollback()
            return False

        current_failures = row[0]
        new_failures = 0 if is_success else current_failures + 1

        # 1. Insert the check result
        conn.execute(
            """
            INSERT INTO check_results
                (monitor_id, checked_at, outcome, status_code, latency_ms,
                 error_code, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
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
        )

        # 2. Update monitor summary + schedule next check, clearing the lease.
        #    Optimistic lock: only if our claim token is still current.
        cur = conn.execute(
            """
            UPDATE monitors
            SET last_checked_at = %s,
                last_outcome = %s,
                last_status_code = %s,
                next_check_at = %s,
                lease_until = NULL,
                lease_token = NULL,
                consecutive_failures = %s,
                updated_at = NOW()
            WHERE id = %s
              AND (lease_token = %s OR lease_token IS NULL)
            RETURNING id
            """,
            (
                checked_at,
                result.outcome.value,
                result.status_code,
                next_check,
                new_failures,
                monitor_id,
                claim_token,
            ),
        )

        if cur.rowcount == 0:
            # Claim was superseded by another worker — discard everything.
            conn.rollback()
            return False

        # 3. Incident state transition
        if is_success:
            # Resolve any open incident
            conn.execute(
                """
                UPDATE incidents
                SET resolved_at = %s
                WHERE monitor_id = %s AND resolved_at IS NULL
                """,
                (checked_at, monitor_id),
            )
        elif new_failures >= threshold:
            # Open an incident only if none is open; otherwise extend it.
            open_incident = conn.execute(
                "SELECT id FROM incidents WHERE monitor_id = %s AND resolved_at IS NULL",
                (monitor_id,),
            ).fetchone()

            if open_incident is None:
                conn.execute(
                    """
                    INSERT INTO incidents
                        (monitor_id, started_at, last_failure_at,
                         failure_count_at_open)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (monitor_id, checked_at, checked_at, new_failures),
                )
            else:
                conn.execute(
                    """
                    UPDATE incidents
                    SET last_failure_at = %s
                    WHERE id = %s
                    """,
                    (checked_at, open_incident[0]),
                )

        conn.commit()
    return True
