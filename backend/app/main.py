from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api import api_router
from backend.app.db import close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_pool()


app = FastAPI(
    title="Pulse",
    description="Self-hosted uptime monitoring",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(api_router)


@app.get("/health/live")
async def liveness() -> dict[str, str]:
    """Process liveness check."""
    return {"status": "alive"}
