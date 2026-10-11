from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from backend.app.db.core import get_conn
from backend.app.db.queries import (
    has_open_incident,
    monitor_exists,
    select_all_incidents,
    select_check_history,
    select_incidents,
    select_monitor,
    select_monitors,
)
from backend.app.monitoring.status import StatusInput, derive_status
from backend.app.monitoring.url_policy import UrlPolicyError, parse_and_validate_url

router = APIRouter()


class CreateMonitorRequest(BaseModel):
    url: str
    interval_seconds: int = Field(default=60, ge=60, le=86400)


class UpdateMonitorRequest(BaseModel):
    interval_seconds: int | None = Field(default=None, ge=60, le=86400)
    enabled: bool | None = None


class MonitorResponse(BaseModel):
    id: int
    url: str
    interval_seconds: int
    enabled: bool
    status: str
    created_at: datetime
    updated_at: datetime
    next_check_at: datetime
    last_checked_at: datetime | None = None
    last_outcome: str | None = None
    last_status_code: int | None = None
    consecutive_failures: int | None = None


class CheckResultResponse(BaseModel):
    id: int
    checked_at: datetime
    outcome: str
    status_code: int | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None


class IncidentResponse(BaseModel):
    id: int
    monitor_id: int | None = None
    url: str | None = None
    started_at: datetime
    last_failure_at: datetime
    resolved_at: datetime | None = None
    failure_count_at_open: int


def _row_to_response(row) -> MonitorResponse:
    """Map a monitors row to MonitorResponse with derived status."""
    derived = derive_status(
        StatusInput(
            interval_seconds=row[2],
            last_checked_at=row[7],
            last_outcome=row[8],
            consecutive_failures=row[10] or 0,
            has_open_incident=has_open_incident(row[0]),
        )
    )
    return MonitorResponse(
        id=row[0], url=row[1], interval_seconds=row[2], enabled=row[3],
        status=derived.value,
        created_at=row[4], updated_at=row[5], next_check_at=row[6],
        last_checked_at=row[7], last_outcome=row[8], last_status_code=row[9],
        consecutive_failures=row[10],
    )


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
                      created_at, updated_at, next_check_at,
                      last_checked_at, last_outcome, last_status_code,
                      consecutive_failures
            """,
            (validated_url, req.interval_seconds),
        ).fetchone()
        conn.commit()
    return _row_to_response(row)


@router.get("/monitors", response_model=list[MonitorResponse])
def list_monitors():
    rows = select_monitors(limit=100)
    return [_row_to_response(r) for r in rows]


@router.get("/monitors/{monitor_id}", response_model=MonitorResponse)
def get_monitor(monitor_id: int):
    row = select_monitor(monitor_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Monitor not found."}},
        )
    return _row_to_response(row)


@router.patch("/monitors/{monitor_id}", response_model=MonitorResponse)
def update_monitor(monitor_id: int, req: UpdateMonitorRequest):
    """Update interval and/or enabled state. Re-enabling makes it due promptly."""
    if not monitor_exists(monitor_id):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Monitor not found."}},
        )

    sets = []
    params: list = []

    if req.interval_seconds is not None:
        sets.append("interval_seconds = %s")
        params.append(req.interval_seconds)

    if req.enabled is not None:
        sets.append("enabled = %s")
        params.append(req.enabled)
        # Re-enabling makes the next check due promptly
        if req.enabled:
            sets.append("next_check_at = NOW()")

    if not sets:
        row = select_monitor(monitor_id)
        return _row_to_response(row)

    sets.append("updated_at = NOW()")
    params.append(monitor_id)

    with get_conn() as conn:
        row = conn.execute(
            f"UPDATE monitors SET {', '.join(sets)} WHERE id = %s "
            f"RETURNING id, url, interval_seconds, enabled, "
            f"created_at, updated_at, next_check_at, "
            f"last_checked_at, last_outcome, last_status_code, "
            f"consecutive_failures",
            tuple(params),
        ).fetchone()
        conn.commit()
    return _row_to_response(row)


@router.delete("/monitors/{monitor_id}", status_code=204)
def delete_monitor(monitor_id: int):
    """Delete a monitor. Cascades to check results and incidents."""
    if not monitor_exists(monitor_id):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Monitor not found."}},
        )
    with get_conn() as conn:
        conn.execute("DELETE FROM monitors WHERE id = %s", (monitor_id,))
        conn.commit()
    return Response(status_code=204)


@router.get("/monitors/{monitor_id}/checks", response_model=list[CheckResultResponse])
def get_check_history(monitor_id: int, limit: int = 100):
    """Paginated recent check history, newest first."""
    if not monitor_exists(monitor_id):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Monitor not found."}},
        )
    rows = select_check_history(monitor_id, limit=min(limit, 100))
    return [
        CheckResultResponse(
            id=r[0], checked_at=r[1], outcome=r[2], status_code=r[3],
            latency_ms=r[4], error_code=r[5], error_message=r[6],
        )
        for r in rows
    ]


@router.get("/monitors/{monitor_id}/incidents", response_model=list[IncidentResponse])
def get_incident_history(monitor_id: int, limit: int = 100):
    """Incident history for a monitor, newest first."""
    if not monitor_exists(monitor_id):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Monitor not found."}},
        )
    rows = select_incidents(monitor_id, limit=min(limit, 100))
    return [
        IncidentResponse(
            id=r[0], started_at=r[1], last_failure_at=r[2],
            resolved_at=r[3], failure_count_at_open=r[4],
        )
        for r in rows
    ]


@router.get("/incidents", response_model=list[IncidentResponse])
def list_incidents(state: str = "all", limit: int = 100):
    """Filterable incident list. state = 'open' | 'resolved' | 'all'."""
    if state not in ("open", "resolved", "all"):
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "invalid_state",
                              "message": "state must be open, resolved, or all."}},
        )
    rows = select_all_incidents(state=state, limit=min(limit, 100))
    return [
        IncidentResponse(
            id=r[0], monitor_id=r[1], started_at=r[2], last_failure_at=r[3],
            resolved_at=r[4], failure_count_at_open=r[5], url=r[6],
        )
        for r in rows
    ]
