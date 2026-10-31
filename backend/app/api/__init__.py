from fastapi import APIRouter

from .health import router as health_router
from .monitors import router as monitors_router
from .webhooks import router as webhooks_router

api_router = APIRouter()
api_router.include_router(monitors_router, prefix="/api/v1")
api_router.include_router(webhooks_router, prefix="/api/v1")
api_router.include_router(health_router)
