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
