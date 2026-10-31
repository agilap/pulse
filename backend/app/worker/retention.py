import logging

from backend.app.config import settings
from backend.app.db.core import get_conn

logger = logging.getLogger("pulse.retention")

BATCH_SIZE = 1000


def cleanup_expired_check_results() -> int:
    """Delete check results older than the retention window, in bounded batches.

    FR-12: never one long-running transaction over the whole dataset.
    Each batch is its own short transaction; incidents are never touched
    (they live until the monitor is deleted).
    """
    total_deleted = 0

    while True:
        with get_conn() as conn:
            cur = conn.execute(
                """
                DELETE FROM check_results
                WHERE id IN (
                    SELECT id FROM check_results
                    WHERE checked_at < NOW() - make_interval(days => %s)
                    LIMIT %s
                )
                """,
                (settings.retention_days, BATCH_SIZE),
            )
            deleted = cur.rowcount
            conn.commit()

        total_deleted += deleted
        logger.info("retention_batch_deleted", extra={"deleted": deleted})

        if deleted < BATCH_SIZE:
            break

    return total_deleted


def cleanup_expired_notification_events() -> int:
    """Remove old terminal notification history without deleting pending work."""
    total_deleted = 0

    while True:
        with get_conn() as conn:
            cur = conn.execute(
                """
                DELETE FROM notification_events
                WHERE id IN (
                    SELECT e.id
                    FROM notification_events e
                    WHERE e.created_at < NOW() - make_interval(days => %s)
                      AND NOT EXISTS (
                          SELECT 1
                          FROM webhook_deliveries d
                          WHERE d.event_id = e.id
                            AND d.status IN ('pending', 'delivering')
                      )
                    ORDER BY e.created_at ASC
                    LIMIT %s
                )
                """,
                (settings.notification_retention_days, BATCH_SIZE),
            )
            deleted = cur.rowcount
            conn.commit()

        total_deleted += deleted
        logger.info("notification_retention_batch_deleted", extra={"deleted": deleted})

        if deleted < BATCH_SIZE:
            break

    return total_deleted
