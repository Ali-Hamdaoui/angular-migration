"""Composition root for thin API routers."""

from fastapi import APIRouter

from app.api.routes.artifacts import router as artifacts_router
from app.api.routes.health import router as health_router
from app.api.routes.migrations import router as migrations_router
from app.api.routes.version import router as version_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(version_router)
api_router.include_router(migrations_router)
api_router.include_router(artifacts_router)