import time

from backend.app.worker.claim import claim_due_monitors
from backend.app.worker.config import validate_worker_config


def run_worker(worker_id: str = "worker-1", poll_interval: int = 1):
    """Main worker loop — claims due monitors, defers execution to Session 6."""
    config = validate_worker_config()
    print(f"[worker] {worker_id} started. Lease={config['lease_seconds']}s, "
          f"Timeout={config['request_timeout']}s")

    while True:
        try:
            claimed = claim_due_monitors(worker_id=worker_id, limit=10)
            for m in claimed:
                print(f"[worker] {worker_id} claimed monitor {m.id} ({m.url}) "
                      f"lease_expires={m.lease_until.isoformat()}")
        except Exception as e:
            print(f"[worker] {worker_id} claim error: {e}")

        time.sleep(poll_interval)


if __name__ == "__main__":
    run_worker()
