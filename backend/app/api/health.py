from fastapi import APIRouter, HTTPException, status

from backend.app.db.core import get_conn

router = APIRouter()


@router.get("/health/live")
def liveness():
    """Process liveness — no dependency checks."""
    return {"status": "alive"}


@router.get("/health/ready")
def readiness():
    """Readiness: reports not-ready if the database is unavailable."""
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "db_unavailable",
                              "message": "Database not reachable."}},
        ) from None
    return {"status": "ready"}
