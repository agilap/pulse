"""Pulse API entry point — Session 1 scaffold."""
from fastapi import FastAPI

app = FastAPI(
    title="Pulse",
    description="Self-hosted uptime monitoring",
    version="0.1.0",
)


@app.get("/health/live")
async def liveness() -> dict[str, str]:
    """Process liveness check."""
    return {"status": "alive"}
