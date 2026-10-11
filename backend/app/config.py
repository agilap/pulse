"""Environment-validated configuration for Pulse.

All settings come from environment variables (loaded from a local .env file
in development). Configuration bounds are validated here so unsafe values
are caught at startup, not at runtime.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Pulse configuration."""

    # Database
    database_url: str = "postgresql://pulse:changeme-not-a-real-secret@localhost:5432/pulse"

    # Monitor interval bounds (seconds): 60 to 86400
    min_interval_seconds: int = 60
    max_interval_seconds: int = 86_400
    default_interval_seconds: int = 60

    # HTTP checks
    request_timeout_seconds: float = 10.0

    # Worker
    lease_duration_seconds: float = 30.0
    worker_concurrency: int = 5
    monitor_cap: int = 50

    # Retention (days)
    retention_days: int = 30

    # API server
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
