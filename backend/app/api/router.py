"""Composition root for thin API routers."""

from fastapi import APIRouter

from app.api.routes.artifacts import router as artifacts_router
from app.api.routes.preflights import draft_approval_router, router as preflights_router
from app.api.routes.environment import router as environment_router
from app.api.routes.execution_profiles import router as execution_profiles_router
from app.api.routes.health import router as health_router
from app.api.routes.g02 import router as g02_router
from app.api.routes.sources import router as sources_router
from app.api.routes.source_analysis import router as source_analysis_router
from app.api.routes.snapshots import router as snapshots_router
from app.api.routes.migrations import assistant_router, router as migrations_router
from app.api.routes.version import router as version_router
from app.api.routes.baseline import router as baseline_router
from app.api.routes.baseline_g03 import router as baseline_g03_router
from app.api.routes.baseline_matrix import router as baseline_matrix_router
from app.api.routes.discovery import router as discovery_router
from app.api.routes.baseline_parity import router as baseline_parity_router
from app.api.routes.runs import router as runs_router
from app.api.routes.llm import router as llm_router
from app.api.routes.parity_baseline import router as parity_baseline_router
from app.api.routes.analysis import router as analysis_router
from app.api.routes.compatibility import router as compatibility_router

api_router = APIRouter()
api_v1_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(sources_router)
api_router.include_router(source_analysis_router)
api_router.include_router(version_router)
api_router.include_router(runs_router)
api_router.include_router(llm_router)
api_router.include_router(snapshots_router)
api_router.include_router(compatibility_router)
api_router.include_router(g02_router)
api_router.include_router(migrations_router)
api_router.include_router(assistant_router)
api_router.include_router(artifacts_router)
api_router.include_router(environment_router)
api_router.include_router(execution_profiles_router)
api_router.include_router(preflights_router)
api_router.include_router(baseline_router)
api_router.include_router(baseline_g03_router)
api_router.include_router(baseline_parity_router)
api_router.include_router(baseline_matrix_router)
api_router.include_router(discovery_router)
api_router.include_router(parity_baseline_router)
api_router.include_router(analysis_router)
api_router.include_router(draft_approval_router)

# Versioned production surface; legacy unversioned paths remain compatibility aliases.
api_v1_router.include_router(health_router)
api_v1_router.include_router(sources_router)
api_v1_router.include_router(source_analysis_router)
api_v1_router.include_router(version_router)
api_v1_router.include_router(runs_router)
api_v1_router.include_router(llm_router)
api_v1_router.include_router(snapshots_router)
api_v1_router.include_router(compatibility_router)
api_v1_router.include_router(g02_router)
api_v1_router.include_router(migrations_router)
api_v1_router.include_router(assistant_router)
api_v1_router.include_router(artifacts_router)
api_v1_router.include_router(environment_router)
api_v1_router.include_router(execution_profiles_router)
api_v1_router.include_router(preflights_router)
api_v1_router.include_router(draft_approval_router)
api_v1_router.include_router(baseline_router)
api_v1_router.include_router(baseline_g03_router)
api_v1_router.include_router(baseline_parity_router)
api_v1_router.include_router(baseline_matrix_router)
api_v1_router.include_router(discovery_router)
api_v1_router.include_router(parity_baseline_router)
api_v1_router.include_router(analysis_router)
api_router.include_router(api_v1_router)
