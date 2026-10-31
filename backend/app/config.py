from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://pulse:changeme-not-a-real-secret@localhost:5432/pulse"

    # Monitor interval bounds (seconds): 60 to 86400
    min_interval_seconds: int = 60
    max_interval_seconds: int = 86_400
    default_interval_seconds: int = 60

    # HTTP checks
    request_timeout_seconds: float = 10.0

    # Incident threshold (FR-09): consecutive failures that open an incident
    failure_threshold: int = 3

    # Worker
    lease_duration_seconds: float = 30.0
    worker_concurrency: int = 5
    webhook_concurrency: int = 10
    webhook_max_attempts: int = 8
    monitor_cap: int = 50

    # Retention (days)
    retention_days: int = 30
    notification_retention_days: int = 90

    # API server
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
