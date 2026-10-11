"""Session 1 smoke test — verifies toolchain and config load."""
from backend.app.config import settings


def test_settings_load():
    """Settings object loads with valid defaults."""
    assert settings.min_interval_seconds >= 60
    assert settings.max_interval_seconds <= 86_400
    assert settings.request_timeout_seconds < settings.lease_duration_seconds
