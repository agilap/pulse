from backend.app.db.core import get_conn


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
