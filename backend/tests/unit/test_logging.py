import logging

from backend.app.logging_config import SecretSafeFormatter


def _emit(record_kwargs):
    logger = logging.getLogger("pulse.test")
    handler = logging.Handler()
    handler.setFormatter(SecretSafeFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z"))
    record = logger.makeRecord(
        name="pulse.test",
        level=logging.INFO,
        fn="test.py",
        lno=1,
        msg=record_kwargs.get("msg", "hello"),
        args=(),
        exc_info=None,
    )
    for key, value in record_kwargs.get("extra", {}).items():
        setattr(record, key, value)
    return handler.format(record)


def test_redacts_password_fields():
    line = _emit({
        "msg": "connecting",
        "extra": {"password": "hunter2", "monitor_id": 5},
    })
    assert "hunter2" not in line
    assert "REDACTED" in line
    assert "monitor_id" in line


def test_redacts_token_fields():
    line = _emit({
        "msg": "auth",
        "extra": {"lease_token": "worker-1:123:abcdef"},
    })
    assert "abcdef" not in line
    assert "REDACTED" in line


def test_redacts_database_url():
    line = _emit({
        "msg": "connect",
        "extra": {"database_url": "postgresql://u:pw@host/db"},
    })
    assert "pw" not in line
    assert "REDACTED" in line


def test_keeps_safe_fields():
    line = _emit({
        "msg": "check complete",
        "extra": {
            "monitor_id": 7,
            "outcome": "success",
            "status_code": 200,
            "latency_ms": 42,
        },
    })
    assert "success" in line
    assert "200" in line
    assert "42" in line


def test_output_is_valid_json():
    import json

    line = _emit({"msg": "test", "extra": {"monitor_id": 1}})
    parsed = json.loads(line)
    assert parsed["message"] == "test"
    assert parsed["level"] == "INFO"
    assert parsed["monitor_id"] == 1
