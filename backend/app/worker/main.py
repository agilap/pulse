import time

from backend.app.logging_config import configure_logging
from backend.app.worker.check_loop import run_check_cycle
from backend.app.worker.config import validate_worker_config
from backend.app.worker.retention import cleanup_expired_check_results

configure_logging()

RETENTION_INTERVAL_SECONDS = 3600


def run_worker(worker_id: str = "pulse-worker", poll_interval: int = 1):
    config = validate_worker_config()
    print(f"[worker] {worker_id} started. Lease={config['lease_seconds']}s, "
          f"Timeout={config['request_timeout']}s")

    last_retention = time.monotonic()

    while True:
        try:
            checked = run_check_cycle(worker_id)
            if checked:
                print(f"[worker] {worker_id} checked {checked} monitor(s)")
        except Exception as e:
            print(f"[worker] {worker_id} cycle error: {e}")

        # Periodic retention cleanup (FR-12)
        if time.monotonic() - last_retention >= RETENTION_INTERVAL_SECONDS:
            try:
                deleted = cleanup_expired_check_results()
                if deleted:
                    print(f"[worker] {worker_id} retention deleted {deleted} row(s)")
                last_retention = time.monotonic()
            except Exception as e:
                print(f"[worker] {worker_id} retention error: {e}")

        time.sleep(poll_interval)


if __name__ == "__main__":
    run_worker()
