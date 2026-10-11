from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from backend.app.config import settings

# FR-08: greater of three configured intervals or 120 seconds
MIN_FRESHNESS_SECONDS = 120


class MonitorStatus(str, Enum):
    pending = "pending"
    up = "up"
    degraded = "degraded"
    down = "down"
    stale = "stale"


@dataclass
class StatusInput:
    interval_seconds: int
    last_checked_at: datetime | None
    last_outcome: str | None
    consecutive_failures: int
    has_open_incident: bool


def freshness_window(interval_seconds: int) -> timedelta:
    """Data older than this means Pulse cannot confidently state status."""
    three_intervals = timedelta(seconds=interval_seconds * 3)
    floor = timedelta(seconds=MIN_FRESHNESS_SECONDS)
    timeout_allowance = timedelta(seconds=settings.request_timeout_seconds)
    return max(three_intervals, floor) + timeout_allowance


def derive_status(data: StatusInput, now: datetime | None = None) -> MonitorStatus:
    """Derive monitor status per FR-08.

    Stale takes precedence: never present stale data as proof of being down.
    """
    now = now or datetime.now(timezone.utc)

    # No check has ever completed
    if data.last_checked_at is None:
        return MonitorStatus.pending

    window = freshness_window(data.interval_seconds)
    if now - data.last_checked_at > window:
        return MonitorStatus.stale

    if data.last_outcome == "success" and not data.has_open_incident:
        return MonitorStatus.up

    if data.has_open_incident:
        return MonitorStatus.down

    # Failures below the incident threshold
    return MonitorStatus.degraded
