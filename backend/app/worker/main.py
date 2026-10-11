import time

from backend.app.worker.check_loop import run_check_cycle
from backend.app.worker.config import validate_worker_config


def run_worker(worker_id: str = "pulse-worker", poll_interval: int = 1):
    config = validate_worker_config()
    print(f"[worker] {worker_id} started. Lease={config['lease_seconds']}s, "
          f"Timeout={config['request_timeout']}s")

    while True:
        try:
            checked = run_check_cycle(worker_id)
            if checked:
                print(f"[worker] {worker_id} checked {checked} monitor(s)")
        except Exception as e:
            print(f"[worker] {worker_id} cycle error: {e}")

        time.sleep(poll_interval)


if __name__ == "__main__":
    run_worker()
