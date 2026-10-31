from datetime import datetime, timedelta
from uuid import uuid4

from psycopg.types.json import Jsonb

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


def select_check_history(monitor_id: int, limit: int = 100):
    """Recent check history, newest first. Bounded by LIMIT (FR-10)."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, checked_at, outcome, status_code, latency_ms,
                   error_code, error_message
            FROM check_results
            WHERE monitor_id = %s
            ORDER BY checked_at DESC
            LIMIT %s
            """,
            (monitor_id, limit),
        ).fetchall()
    return rows


def select_incidents(monitor_id: int, limit: int = 100):
    """Incident history for a monitor, newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, started_at, last_failure_at, resolved_at,
                   failure_count_at_open
            FROM incidents
            WHERE monitor_id = %s
            ORDER BY started_at DESC
            LIMIT %s
            """,
            (monitor_id, limit),
        ).fetchall()
    return rows


def select_all_incidents(state: str = "all", limit: int = 100):
    """Incidents across all monitors. state = 'open' | 'resolved' | 'all'."""
    with get_conn() as conn:
        if state == "open":
            rows = conn.execute(
                """
                SELECT i.id, i.monitor_id, i.started_at, i.last_failure_at,
                       i.resolved_at, i.failure_count_at_open, m.url
                FROM incidents i
                JOIN monitors m ON m.id = i.monitor_id
                WHERE i.resolved_at IS NULL
                ORDER BY i.started_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        elif state == "resolved":
            rows = conn.execute(
                """
                SELECT i.id, i.monitor_id, i.started_at, i.last_failure_at,
                       i.resolved_at, i.failure_count_at_open, m.url
                FROM incidents i
                JOIN monitors m ON m.id = i.monitor_id
                WHERE i.resolved_at IS NOT NULL
                ORDER BY i.started_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT i.id, i.monitor_id, i.started_at, i.last_failure_at,
                       i.resolved_at, i.failure_count_at_open, m.url
                FROM incidents i
                JOIN monitors m ON m.id = i.monitor_id
                ORDER BY i.started_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
    return rows


def has_open_incident(monitor_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM incidents WHERE monitor_id = %s AND resolved_at IS NULL",
            (monitor_id,),
        ).fetchone()
    return row is not None


def monitor_exists(monitor_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM monitors WHERE id = %s", (monitor_id,)).fetchone()
    return row is not None


def _enqueue_notification_event(
    conn,
    *,
    event_type: str,
    incident_id: int,
    monitor_id: int,
    monitor_url: str,
    interval_seconds: int,
    started_at: datetime,
    last_failure_at: datetime,
    failure_count_at_open: int,
    occurred_at: datetime,
    resolved_at: datetime | None = None,
):
    """Persist an event and fan it out to subscribed endpoints in this transaction."""
    event_id = uuid4()
    incident_payload = {
        "id": incident_id,
        "started_at": started_at.isoformat(),
        "last_failure_at": last_failure_at.isoformat(),
        "failure_count_at_open": failure_count_at_open,
    }
    if resolved_at is not None:
        incident_payload["resolved_at"] = resolved_at.isoformat()

    payload = {
        "id": str(event_id),
        "type": event_type,
        "occurred_at": occurred_at.isoformat(),
        "monitor": {
            "id": monitor_id,
            "url": monitor_url,
            "interval_seconds": interval_seconds,
        },
        "incident": incident_payload,
    }

    conn.execute(
        """
        INSERT INTO notification_events (id, event_type, incident_id, monitor_id, payload)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (incident_id, event_type) DO NOTHING
        """,
        (event_id, event_type, incident_id, monitor_id, Jsonb(payload)),
    )

    persisted_event = conn.execute(
        """
        SELECT id FROM notification_events
        WHERE incident_id = %s AND event_type = %s
        """,
        (incident_id, event_type),
    ).fetchone()
    persisted_event_id = persisted_event[0]

    conn.execute(
        """
        INSERT INTO webhook_deliveries (event_id, endpoint_id)
        SELECT %s, id
        FROM webhook_endpoints
        WHERE enabled = TRUE
          AND event_types @> ARRAY[%s]::TEXT[]
        ON CONFLICT (event_id, endpoint_id) DO NOTHING
        """,
        (persisted_event_id, event_type),
    )


def persist_check_result(
    monitor_id: int,
    claim_token: str,
    checked_at: datetime,
    result: CheckResult,
    interval_seconds: int,
) -> bool:
    """Persist a check result atomically with monitor updates and incident transitions.

    Result persistence, monitor summary updates, incident transitions, and
    notification event fan-out share one transaction. A failed transaction
    cannot leave an incident transition without its corresponding outbox event.

    Optimistic locking (WHERE lease_token = %s) means a stale worker whose
    lease was superseded cannot commit — returns False in that case.

    Returns True if committed, False if the claim was no longer current.
    """
    is_success = result.outcome.value == "success"
    threshold = settings.failure_threshold
    next_check = checked_at + timedelta(seconds=interval_seconds)

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT consecutive_failures, url
            FROM monitors
            WHERE id = %s
            FOR UPDATE
            """,
            (monitor_id,),
        ).fetchone()
        if row is None:
            conn.rollback()
            return False

        current_failures, monitor_url = row
        new_failures = 0 if is_success else current_failures + 1

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
              AND lease_token = %s
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
            conn.rollback()
            return False

        if is_success:
            resolved_incidents = conn.execute(
                """
                UPDATE incidents
                SET resolved_at = %s
                WHERE monitor_id = %s AND resolved_at IS NULL
                RETURNING id, started_at, last_failure_at, resolved_at,
                          failure_count_at_open
                """,
                (checked_at, monitor_id),
            ).fetchall()

            for incident in resolved_incidents:
                _enqueue_notification_event(
                    conn,
                    event_type="incident.resolved",
                    incident_id=incident[0],
                    monitor_id=monitor_id,
                    monitor_url=monitor_url,
                    interval_seconds=interval_seconds,
                    started_at=incident[1],
                    last_failure_at=incident[2],
                    failure_count_at_open=incident[4],
                    occurred_at=checked_at,
                    resolved_at=incident[3],
                )

        elif new_failures >= threshold:
            open_incident = conn.execute(
                "SELECT id FROM incidents WHERE monitor_id = %s AND resolved_at IS NULL",
                (monitor_id,),
            ).fetchone()

            if open_incident is None:
                incident = conn.execute(
                    """
                    INSERT INTO incidents
                        (monitor_id, started_at, last_failure_at,
                         failure_count_at_open)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, started_at, last_failure_at, failure_count_at_open
                    """,
                    (monitor_id, checked_at, checked_at, new_failures),
                ).fetchone()

                _enqueue_notification_event(
                    conn,
                    event_type="incident.opened",
                    incident_id=incident[0],
                    monitor_id=monitor_id,
                    monitor_url=monitor_url,
                    interval_seconds=interval_seconds,
                    started_at=incident[1],
                    last_failure_at=incident[2],
                    failure_count_at_open=incident[3],
                    occurred_at=checked_at,
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
