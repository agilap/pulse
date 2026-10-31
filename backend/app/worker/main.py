import time

from backend.app.logging_config import configure_logging
from backend.app.worker.check_loop import run_check_cycle
from backend.app.worker.config import validate_worker_config
from backend.app.worker.retention import (
    cleanup_expired_check_results,
    cleanup_expired_notification_events,
)
from backend.app.worker.webhook_dispatch import run_webhook_delivery_cycle

configure_logging()

RETENTION_INTERVAL_SECONDS = 3600


def run_worker(worker_id: str = "pulse-worker", poll_interval: int = 1):
    config = validate_worker_config()
    print(
        f"[worker] {worker_id} started. Lease={config['lease_seconds']}s, "
        f"Timeout={config['request_timeout']}s"
    )

    last_retention = time.monotonic()

    while True:
        try:
            checked = run_check_cycle(worker_id)
            if checked:
                print(f"[worker] {worker_id} checked {checked} monitor(s)")
        except Exception as e:
            print(f"[worker] {worker_id} check cycle error: {e}")

        try:
            delivered = run_webhook_delivery_cycle(worker_id)
            if delivered:
                print(f"[worker] {worker_id} attempted {delivered} webhook delivery(s)")
        except Exception as e:
            print(f"[worker] {worker_id} webhook cycle error: {e}")

        if time.monotonic() - last_retention >= RETENTION_INTERVAL_SECONDS:
            try:
                deleted_checks = cleanup_expired_check_results()
                deleted_events = cleanup_expired_notification_events()
                if deleted_checks or deleted_events:
                    print(
                        f"[worker] {worker_id} retention deleted "
                        f"{deleted_checks} check(s) and {deleted_events} notification event(s)"
                    )
                last_retention = time.monotonic()
            except Exception as e:
                print(f"[worker] {worker_id} retention error: {e}")

        time.sleep(poll_interval)


if __name__ == "__main__":
    run_worker()
