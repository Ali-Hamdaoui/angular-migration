"""Composition root for thin API routers."""

from fastapi import APIRouter

from app.api.routes.artifacts import router as artifacts_router
from app.api.routes.preflights import draft_approval_router, router as preflights_router
from app.api.routes.environment import router as environment_router
from app.api.routes.health import router as health_router
from app.api.routes.sources import router as sources_router
from app.api.routes.migrations import assistant_router, router as migrations_router
from app.api.routes.version import router as version_router
from app.api.routes.runs import router as runs_router

api_router = APIRouter()
api_v1_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(sources_router)
api_router.include_router(version_router)
api_router.include_router(runs_router)
api_router.include_router(migrations_router)
api_router.include_router(assistant_router)
api_router.include_router(artifacts_router)
api_router.include_router(environment_router)
api_router.include_router(preflights_router)
api_router.include_router(draft_approval_router)

# Versioned production surface; legacy unversioned paths remain compatibility aliases.
api_v1_router.include_router(health_router)
api_v1_router.include_router(sources_router)
api_v1_router.include_router(version_router)
api_v1_router.include_router(runs_router)
api_v1_router.include_router(migrations_router)
api_v1_router.include_router(assistant_router)
api_v1_router.include_router(artifacts_router)
api_v1_router.include_router(environment_router)
api_v1_router.include_router(preflights_router)
api_v1_router.include_router(draft_approval_router)
api_router.include_router(api_v1_router)
