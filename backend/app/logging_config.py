import json
import logging
import sys

_SECRET_KEYS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "database_url",
)


def _redact(key: str, value):
    """Redact values under secret-bearing field names."""
    lowered = key.lower()
    for secret in _SECRET_KEYS:
        if secret in lowered:
            return "***REDACTED***"
    # Also redact string values that themselves look like secrets
    if isinstance(value, str):
        value_lower = value.lower()
        if "password=" in value_lower or "secret=" in value_lower:
            return "***REDACTED***"
    return value


class SecretSafeFormatter(logging.Formatter):
    """JSON formatter that redacts secret-bearing fields.

    Logs must never contain credentials, query strings, response bodies,
    or environment secrets (FR-13).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Merge structured extras (monitor_id, outcome, latency, etc.)
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in {
                "args", "msg", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno",
                "funcName", "created", "msecs", "relativeCreated", "thread",
                "threadName", "processName", "process", "name", "message",
                "taskName",
            }:
                continue
            payload[key] = _redact(key, value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Install structured, secret-safe logging on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(SecretSafeFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z"))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
