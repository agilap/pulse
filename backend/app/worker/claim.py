import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from backend.app.config import settings
from backend.app.db.core import get_conn


class ClaimedMonitor(NamedTuple):
    id: int
    url: str
    interval_seconds: int
    lease_token: str
    lease_until: datetime


def claim_due_monitors(worker_id: str, limit: int = 10) -> list[ClaimedMonitor]:
    """Claim eligible monitors atomically with FOR UPDATE SKIP LOCKED + lease."""
    lease_until = datetime.now(timezone.utc) + timedelta(seconds=settings.lease_duration_seconds)
    claim_token = f"{worker_id}:{int(time.time() * 1_000_000)}:{secrets.token_hex(8)}"

    claimed: list[ClaimedMonitor] = []

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, url, interval_seconds
            FROM monitors
            WHERE enabled = TRUE
              AND next_check_at <= NOW()
              AND (lease_until IS NULL OR lease_until < NOW())
            ORDER BY next_check_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

        if rows:
            ids = [r[0] for r in rows]
            conn.execute(
                """
                UPDATE monitors
                SET lease_until = %s,
                    lease_token = %s
                WHERE id = ANY(%s)
                  AND (lease_until IS NULL OR lease_until < NOW())
                """,
                (lease_until, claim_token, ids),
            )
            conn.commit()

            for r in rows:
                claimed.append(ClaimedMonitor(
                    id=r[0], url=r[1], interval_seconds=r[2],
                    lease_token=claim_token, lease_until=lease_until,
                ))

    return claimed
