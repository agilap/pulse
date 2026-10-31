import logging
import random
import secrets
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from backend.app.config import settings
from backend.app.db.core import get_conn
from backend.app.monitoring.webhook import WebhookSendResult, send_webhook

logger = logging.getLogger("pulse.webhooks")


class ClaimedWebhookDelivery(NamedTuple):
    id: int
    event_id: str
    endpoint_id: int
    url: str
    secret: str
    event_type: str
    payload: dict
    attempt_count: int
    lease_token: str


def claim_due_webhook_deliveries(
    worker_id: str,
    limit: int | None = None,
) -> list[ClaimedWebhookDelivery]:
    """Claim due webhook deliveries using SKIP LOCKED and expiring leases."""
    batch_limit = limit or settings.webhook_concurrency
    lease_until = datetime.now(timezone.utc) + timedelta(seconds=settings.lease_duration_seconds)
    claim_token = f"{worker_id}:{int(time.time() * 1_000_000)}:{secrets.token_hex(8)}"

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.event_id, d.endpoint_id, e.url, e.secret,
                   n.event_type, n.payload, d.attempt_count
            FROM webhook_deliveries d
            JOIN webhook_endpoints e ON e.id = d.endpoint_id
            JOIN notification_events n ON n.id = d.event_id
            WHERE e.enabled = TRUE
              AND (
                    (d.status = 'pending' AND d.next_attempt_at <= NOW())
                    OR (d.status = 'delivering' AND d.lease_until < NOW())
              )
            ORDER BY d.next_attempt_at ASC, d.id ASC
            LIMIT %s
            FOR UPDATE OF d SKIP LOCKED
            """,
            (batch_limit,),
        ).fetchall()

        if not rows:
            return []

        delivery_ids = [row[0] for row in rows]
        conn.execute(
            """
            UPDATE webhook_deliveries
            SET status = 'delivering',
                lease_until = %s,
                lease_token = %s,
                updated_at = NOW()
            WHERE id = ANY(%s)
            """,
            (lease_until, claim_token, delivery_ids),
        )
        conn.commit()

    return [
        ClaimedWebhookDelivery(
            id=row[0],
            event_id=str(row[1]),
            endpoint_id=row[2],
            url=row[3],
            secret=row[4],
            event_type=row[5],
            payload=row[6],
            attempt_count=row[7],
            lease_token=claim_token,
        )
        for row in rows
    ]


def _retry_delay_seconds(attempt_number: int) -> float:
    base = min(5.0 * (2 ** max(0, attempt_number - 1)), 3600.0)
    return base * random.uniform(0.8, 1.2)


def persist_webhook_delivery_result(
    delivery_id: int,
    claim_token: str,
    result: WebhookSendResult,
) -> bool:
    """Persist one attempt and transition the delivery only for the current lease."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT attempt_count
            FROM webhook_deliveries
            WHERE id = %s
              AND status = 'delivering'
              AND lease_token = %s
            FOR UPDATE
            """,
            (delivery_id, claim_token),
        ).fetchone()

        if row is None:
            conn.rollback()
            return False

        attempt_number = row[0] + 1
        if result.delivered:
            status = "delivered"
            outcome = "delivered"
            next_attempt_at = None
            delivered_at = datetime.now(timezone.utc)
        elif result.retryable and attempt_number < settings.webhook_max_attempts:
            status = "pending"
            outcome = "retrying"
            next_attempt_at = datetime.now(timezone.utc) + timedelta(
                seconds=_retry_delay_seconds(attempt_number)
            )
            delivered_at = None
        else:
            status = "failed"
            outcome = "failed"
            next_attempt_at = None
            delivered_at = None

        conn.execute(
            """
            INSERT INTO webhook_delivery_attempts
                (delivery_id, attempt_number, outcome, response_status,
                 duration_ms, error_code, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                delivery_id,
                attempt_number,
                outcome,
                result.status_code,
                result.duration_ms,
                result.error_code,
                result.error_message,
            ),
        )
        conn.execute(
            """
            UPDATE webhook_deliveries
            SET status = %s,
                attempt_count = %s,
                next_attempt_at = COALESCE(%s, next_attempt_at),
                delivered_at = %s,
                last_status_code = %s,
                last_error_code = %s,
                last_error_message = %s,
                lease_until = NULL,
                lease_token = NULL,
                updated_at = NOW()
            WHERE id = %s AND lease_token = %s
            """,
            (
                status,
                attempt_number,
                next_attempt_at,
                delivered_at,
                result.status_code,
                result.error_code,
                result.error_message,
                delivery_id,
                claim_token,
            ),
        )
        conn.commit()
    return True


def _process_delivery(delivery: ClaimedWebhookDelivery) -> int:
    try:
        result = send_webhook(
            url=delivery.url,
            secret=delivery.secret,
            event_id=delivery.event_id,
            delivery_id=delivery.id,
            event_type=delivery.event_type,
            payload=delivery.payload,
            timeout=settings.request_timeout_seconds,
        )
    except Exception:
        logger.exception(
            "webhook_delivery_unhandled_error",
            extra={"delivery_id": delivery.id, "endpoint_id": delivery.endpoint_id},
        )
        result = WebhookSendResult(
            delivered=False,
            retryable=True,
            error_code="internal_error",
            error_message="Unexpected error while delivering webhook.",
        )

    committed = persist_webhook_delivery_result(
        delivery_id=delivery.id,
        claim_token=delivery.lease_token,
        result=result,
    )
    if committed:
        logger.info(
            "webhook_delivery_attempted",
            extra={
                "delivery_id": delivery.id,
                "endpoint_id": delivery.endpoint_id,
                "event_type": delivery.event_type,
                "delivered": result.delivered,
                "status_code": result.status_code,
                "error_code": result.error_code,
            },
        )
        return 1

    logger.warning(
        "webhook_delivery_discarded_stale_claim",
        extra={"delivery_id": delivery.id},
    )
    return 0


def run_webhook_delivery_cycle(worker_id: str) -> int:
    """Claim and concurrently attempt a bounded batch of due webhook deliveries."""
    claimed = claim_due_webhook_deliveries(worker_id)
    if not claimed:
        return 0

    attempted = 0
    with ThreadPoolExecutor(max_workers=settings.webhook_concurrency) as executor:
        futures = [executor.submit(_process_delivery, delivery) for delivery in claimed]
        for future in as_completed(futures):
            attempted += future.result()

    return attempted
