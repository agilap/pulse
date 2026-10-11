from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.db.core import get_conn
from backend.app.db.queries import select_monitor, select_monitors
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
    updated_at: datetime
    next_check_at: datetime
    last_checked_at: datetime | None = None
    last_outcome: str | None = None
    last_status_code: int | None = None
    consecutive_failures: int | None = None


@router.post("/monitors", response_model=MonitorResponse, status_code=201)
def create_monitor(req: CreateMonitorRequest):
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
            RETURNING id, url, interval_seconds, enabled,
                      created_at, updated_at, next_check_at
            """,
            (validated_url, req.interval_seconds),
        ).fetchone()
    return MonitorResponse(
        id=row[0], url=row[1], interval_seconds=row[2], enabled=row[3],
        created_at=row[4], updated_at=row[5], next_check_at=row[6],
    )


@router.get("/monitors", response_model=list[MonitorResponse])
def list_monitors():
    rows = select_monitors(limit=100)
    return [
        MonitorResponse(
            id=r[0], url=r[1], interval_seconds=r[2], enabled=r[3],
            created_at=r[4], updated_at=r[5], next_check_at=r[6],
            last_checked_at=r[7], last_outcome=r[8], last_status_code=r[9],
            consecutive_failures=r[10],
        )
        for r in rows
    ]


@router.get("/monitors/{monitor_id}", response_model=MonitorResponse)
def get_monitor(monitor_id: int):
    row = select_monitor(monitor_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Monitor not found."}},
        )
    return MonitorResponse(
        id=row[0], url=row[1], interval_seconds=row[2], enabled=row[3],
        created_at=row[4], updated_at=row[5], next_check_at=row[6],
        last_checked_at=row[7], last_outcome=row[8], last_status_code=row[9],
        consecutive_failures=row[10],
    )
