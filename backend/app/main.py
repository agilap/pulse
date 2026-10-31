from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api import api_router
from backend.app.db.core import close_pool
from backend.app.logging_config import configure_logging

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_pool()


app = FastAPI(
    title="Pulse",
    description="Self-hosted uptime monitoring",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(api_router)
