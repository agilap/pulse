from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.db import get_conn
from backend.app.monitoring.url_policy import UrlPolicyError, parse_and_validate_url

router = APIRouter()


class CreateMonitorRequest(BaseModel):
    url: str
    interval_seconds: int = Field(default=60, ge=60, le=86400)


class MonitorResponse(BaseModel):
    id: int
    url: str
    interval_seconds: int
    enabled: bool
    created_at: datetime
    next_check_at: datetime


@router.post("/monitors", response_model=MonitorResponse, status_code=201)
def create_monitor(req: CreateMonitorRequest):
    """Create a new monitor. First check is due immediately."""
    try:
        validated_url = parse_and_validate_url(req.url)
    except UrlPolicyError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": e.code, "message": e.message}},
        ) from None

    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO monitors (url, interval_seconds, next_check_at)
            VALUES (%s, %s, NOW())
            RETURNING id, url, interval_seconds, enabled, created_at, next_check_at
            """,
            (validated_url, req.interval_seconds),
        ).fetchone()

    return MonitorResponse(
        id=row[0],
        url=row[1],
        interval_seconds=row[2],
        enabled=row[3],
        created_at=row[4],
        next_check_at=row[5],
    )
