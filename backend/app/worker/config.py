import os

from backend.app.config import settings

DEFAULT_REQUEST_TIMEOUT = 10.0
DEFAULT_LEASE_SECONDS = 30.0
MIN_LEASE_MARGIN = 5.0


def validate_worker_config():
    """Validate worker-critical settings — raises on unsafe config."""
    default_timeout = settings.request_timeout_seconds
    default_lease = settings.lease_duration_seconds
    request_timeout = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", default_timeout))
    lease_seconds = float(os.environ.get("LEASE_DURATION_SECONDS", default_lease))

    if lease_seconds <= request_timeout + MIN_LEASE_MARGIN:
        raise ValueError(
            f"LEASE_DURATION_SECONDS ({lease_seconds}s) must exceed "
            f"REQUEST_TIMEOUT_SECONDS ({request_timeout}s) + {MIN_LEASE_MARGIN}s "
            f"margin. Got {lease_seconds}s lease, need > "
            f"{request_timeout + MIN_LEASE_MARGIN}s."
        )

    if request_timeout <= 0:
        raise ValueError(
            f"REQUEST_TIMEOUT_SECONDS must be positive, got {request_timeout}"
        )

    if lease_seconds <= 0:
        raise ValueError(
            f"LEASE_DURATION_SECONDS must be positive, got {lease_seconds}"
        )

    return {"request_timeout": request_timeout, "lease_seconds": lease_seconds}
