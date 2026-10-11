from datetime import datetime, timedelta, timezone

from backend.app.monitoring.status import (
    MonitorStatus,
    StatusInput,
    derive_status,
    freshness_window,
)

NOW = datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)


def _input(interval=60, last_checked=None, outcome="success", failures=0, open_incident=False):
    return StatusInput(
        interval_seconds=interval,
        last_checked_at=last_checked,
        last_outcome=outcome,
        consecutive_failures=failures,
        has_open_incident=open_incident,
    )


def test_pending_when_never_checked():
    assert derive_status(_input(last_checked=None), now=NOW) == MonitorStatus.pending


def test_up_when_success_and_no_incident():
    s = _input(last_checked=NOW - timedelta(seconds=10), outcome="success")
    assert derive_status(s, now=NOW) == MonitorStatus.up


def test_degraded_when_failing_below_threshold():
    s = _input(
        last_checked=NOW - timedelta(seconds=10),
        outcome="http_error",
        failures=1,
        open_incident=False,
    )
    assert derive_status(s, now=NOW) == MonitorStatus.degraded


def test_down_when_incident_open_and_fresh():
    s = _input(
        last_checked=NOW - timedelta(seconds=10),
        outcome="http_error",
        failures=3,
        open_incident=True,
    )
    assert derive_status(s, now=NOW) == MonitorStatus.down


def test_stale_takes_precedence_over_down():
    """Stale data must never be presented as proof of being down."""
    s = _input(
        interval=60,
        last_checked=NOW - timedelta(seconds=100_000),  # very old
        outcome="http_error",
        failures=3,
        open_incident=True,
    )
    assert derive_status(s, now=NOW) == MonitorStatus.stale


def test_stale_takes_precedence_over_up():
    s = _input(
        interval=60,
        last_checked=NOW - timedelta(seconds=100_000),
        outcome="success",
    )
    assert derive_status(s, now=NOW) == MonitorStatus.stale


def test_freshness_window_short_interval_uses_three_intervals():
    """For a 60s interval, 3x180s exceeds the 120s floor, so 3x wins."""
    window = freshness_window(60)
    assert window == timedelta(seconds=180 + 10)


def test_freshness_window_tiny_interval_uses_floor():
    """For a 10s interval, 3x30s < 120s floor, so floor + timeout wins."""
    window = freshness_window(10)
    assert window == timedelta(seconds=120 + 10)


def test_freshness_window_long_interval_uses_three_intervals():
    """For a 3600s interval, 3x10800s > 120s floor."""
    window = freshness_window(3600)
    assert window == timedelta(seconds=3600 * 3 + 10)


def test_freshness_window_boundary():
    """Interval where 3x equals the floor exactly (40s interval -> 120s)."""
    window = freshness_window(40)
    assert window == timedelta(seconds=120 + 10)


def test_fresh_data_at_window_edge_is_not_stale():
    """Exactly at the window boundary is still fresh (strict > comparison)."""
    window = freshness_window(60)
    s = _input(last_checked=NOW - window)
    assert derive_status(s, now=NOW) == MonitorStatus.up


def test_data_just_past_window_is_stale():
    window = freshness_window(60)
    s = _input(last_checked=NOW - window - timedelta(seconds=1))
    assert derive_status(s, now=NOW) == MonitorStatus.stale


def test_success_after_failures_but_incident_still_open_is_down():
    """A success that hasn't resolved the incident yet -> down while open."""
    s = _input(
        last_checked=NOW - timedelta(seconds=5),
        outcome="success",
        failures=0,
        open_incident=True,
    )
    assert derive_status(s, now=NOW) == MonitorStatus.down
