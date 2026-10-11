import logging

from backend.app.config import settings
from backend.app.db.queries import insert_check_result, update_monitor_after_check
from backend.app.monitoring.checker import execute_check
from backend.app.worker.claim import claim_due_monitors

logger = logging.getLogger("pulse.worker")


def run_check_cycle(worker_id: str) -> int:
    """One worker cycle: claim due monitors, check them, persist results.

    Returns the number of monitors checked. Each monitor is processed
    independently — a single check failure never blocks others.
    """
    claimed = claim_due_monitors(worker_id=worker_id, limit=settings.worker_concurrency)
    checked = 0

    for monitor in claimed:
        try:
            result = execute_check(monitor.url, timeout=settings.request_timeout_seconds)
            checked_at = _utcnow()

            # Persist result
            insert_check_result(monitor.id, checked_at, result)

            # Update monitor summary + lease + next check
            update_monitor_after_check(
                monitor_id=monitor.id,
                claim_token=monitor.lease_token,
                checked_at=checked_at,
                result=result,
                interval_seconds=monitor.interval_seconds,
            )

            logger.info(
                "check_complete",
                extra={
                    "monitor_id": monitor.id,
                    "url": monitor.url,
                    "outcome": result.outcome.value,
                    "status_code": result.status_code,
                    "latency_ms": result.latency_ms,
                },
            )
            checked += 1

        except Exception:
            # FR-14: a single check failure must not crash the worker loop
            logger.exception(
                "check_failed",
                extra={"monitor_id": monitor.id, "url": monitor.url},
            )
            # The lease will expire naturally — another worker will reclaim
            # The monitor stays due since we didn't update next_check_at

    return checked


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
