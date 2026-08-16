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
from app.api.routes.commands import router as commands_router
from app.api.routes.run_commands import router as run_commands_router
from app.api.routes.runs import router as runs_router
from app.api.routes.llm import router as llm_router
from app.api.routes.parity_baseline import router as parity_baseline_router
from app.api.routes.analysis import router as analysis_router
from app.api.routes.compatibility import router as compatibility_router
from app.api.routes.plans import router as plans_router
from app.api.routes.planning_review import router as planning_review_router
from app.api.routes.stage_execution import router as stage_execution_router
from app.api.routes.assistant import router as run_assistant_router
from app.api.routes.transformation import router as transformation_router
from app.api.routes.runtime_execution import router as runtime_execution_router
from app.api.routes.diagnostics import router as diagnostics_router
from app.api.routes.stage_runtime import router as stage_runtime_router
from app.api.routes.workspace_authority import router as workspace_authority_router
from app.api.routes.lockfile_compatibility import router as lockfile_compatibility_router
from app.api.routes.catalogue import router as catalogue_router
from app.api.routes.migration_route import router as migration_route_router
from app.api.routes.runtime_certification import router as runtime_certification_router
from app.api.routes.project_capability import router as project_capability_router
from app.api.routes.ng_update_governance import router as ng_update_governance_router
from app.api.routes.third_party_compatibility import router as third_party_compatibility_router
from app.api.routes.preflight_checks import router as preflight_checks_router

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
api_router.include_router(plans_router)
api_router.include_router(planning_review_router)
api_router.include_router(stage_execution_router)
api_router.include_router(transformation_router)
api_router.include_router(runtime_execution_router)
api_router.include_router(diagnostics_router)
api_router.include_router(stage_runtime_router)
api_router.include_router(workspace_authority_router)
api_router.include_router(lockfile_compatibility_router)
api_router.include_router(catalogue_router)
api_router.include_router(migration_route_router)
api_router.include_router(runtime_certification_router)
api_router.include_router(project_capability_router)
api_router.include_router(ng_update_governance_router)
api_router.include_router(third_party_compatibility_router)
api_router.include_router(preflight_checks_router)
# Keep the fixed G03 route ahead of G02's parameterized approval route.
# Otherwise /approvals/G03/decisions is captured by G02 and rejected with a
# misleading gate_id mismatch (400).
api_router.include_router(baseline_g03_router)
api_router.include_router(g02_router)
api_router.include_router(migrations_router)
api_router.include_router(assistant_router)
api_router.include_router(run_assistant_router)
api_router.include_router(artifacts_router)
api_router.include_router(environment_router)
api_router.include_router(execution_profiles_router)
api_router.include_router(preflights_router)
api_router.include_router(baseline_router)
api_router.include_router(baseline_parity_router)
api_router.include_router(baseline_matrix_router)
api_router.include_router(discovery_router)
api_router.include_router(parity_baseline_router)
api_router.include_router(commands_router)
api_router.include_router(run_commands_router)
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
api_v1_router.include_router(plans_router)
api_v1_router.include_router(planning_review_router)
api_v1_router.include_router(stage_execution_router)
api_v1_router.include_router(transformation_router)
api_v1_router.include_router(runtime_execution_router)
api_v1_router.include_router(diagnostics_router)
api_v1_router.include_router(stage_runtime_router)
api_v1_router.include_router(workspace_authority_router)
api_v1_router.include_router(lockfile_compatibility_router)
api_v1_router.include_router(catalogue_router)
api_v1_router.include_router(migration_route_router)
api_v1_router.include_router(runtime_certification_router)
api_v1_router.include_router(project_capability_router)
api_v1_router.include_router(ng_update_governance_router)
api_v1_router.include_router(third_party_compatibility_router)
api_v1_router.include_router(preflight_checks_router)
# Keep the fixed G03 route ahead of G02's parameterized approval route in the
# versioned surface as well.
api_v1_router.include_router(baseline_g03_router)
api_v1_router.include_router(g02_router)
api_v1_router.include_router(migrations_router)
api_v1_router.include_router(assistant_router)
api_v1_router.include_router(run_assistant_router)
api_v1_router.include_router(artifacts_router)
api_v1_router.include_router(environment_router)
api_v1_router.include_router(execution_profiles_router)
api_v1_router.include_router(preflights_router)
api_v1_router.include_router(draft_approval_router)
api_v1_router.include_router(baseline_router)
api_v1_router.include_router(baseline_parity_router)
api_v1_router.include_router(baseline_matrix_router)
api_v1_router.include_router(discovery_router)
api_v1_router.include_router(parity_baseline_router)
api_v1_router.include_router(commands_router)
api_v1_router.include_router(run_commands_router)
api_v1_router.include_router(analysis_router)
api_router.include_router(api_v1_router)
