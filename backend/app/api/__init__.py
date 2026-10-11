from fastapi import APIRouter

from .monitors import router as monitors_router

api_router = APIRouter()
api_router.include_router(monitors_router, prefix="/api/v1")
