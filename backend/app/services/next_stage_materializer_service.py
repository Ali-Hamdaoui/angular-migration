"""Derive one exact later stage from a sealed output and the approved route."""

from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import select

from app.domain.planning import PlanGenerationRequest, StageExecutionPlan
from app.repositories.models import (
    CompatibilityResolutionModel,
    ExecutionProfileModel,
    MigrationPlanModel,
    StageExecutionPlanModel,
)
from app.services.planning_application_service import (
    PlanningApplicationError,
    StageExecutionPlanService,
    run_scoped_stage_id,
)
from app.services.lockfile_compatibility_service import LockfileCompatibilityService


class NextStageMaterializerError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class NextStageMaterializerService:
    semver = re.compile(r"(?P<version>\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)")

    def __init__(self, *, planner=None) -> None:
        self._planner = planner or StageExecutionPlanService()

    def context(self, session, continuation, sealed_path: str, sealed_fingerprint: str):
        migration_plan = session.get(MigrationPlanModel, continuation.plan_id)
        current_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        resolution = session.scalar(
            select(CompatibilityResolutionModel)
            .where(CompatibilityResolutionModel.run_id == continuation.run_id)
            .order_by(CompatibilityResolutionModel.created_at.desc())
        )
        profile = session.scalar(
            select(ExecutionProfileModel)
            .where(ExecutionProfileModel.run_id == continuation.run_id)
            .order_by(ExecutionProfileModel.created_at.desc())
        )
        if not migration_plan or not current_plan or not resolution or not profile:
            raise NextStageMaterializerError(
                "NEXT_STAGE_CONTEXT_MISSING", "Approved route/runtime context is missing"
            )
        if resolution.catalogue_version != (migration_plan.plan or {}).get("catalogue_version"):
            raise NextStageMaterializerError(
                "CATALOGUE_DRIFT", "Compatibility catalogue differs from the approved plan"
            )
        if profile.status not in {"selected", "resolved"} or not profile.selected_checksum:
            raise NextStageMaterializerError(
                "RUNTIME_DRIFT", "Selected execution profile is no longer active"
            )
        route = list(resolution.route or (resolution.package or {}).get("route") or [])
        current_index = next(
            (
                index
                for index, item in enumerate(route)
                if run_scoped_stage_id(continuation.run_id, item["stage_id"])
                == continuation.current_stage_id
            ),
            None,
        )
        if current_index is None:
            raise NextStageMaterializerError(
                "ROUTE_STAGE_MISSING", "Current stage is absent from the approved route"
            )
        return {
            "run_id": continuation.run_id,
            "sealed_path": sealed_path,
            "sealed_fingerprint": sealed_fingerprint,
            "current_target_exact": (current_plan.stage_plan or {}).get("target_exact"),
            "remaining_route": route[current_index + 1 :],
            "catalogue_version": resolution.catalogue_version,
            "execution_profile_id": profile.selected_profile_id,
            "execution_profile_checksum": profile.selected_checksum,
            "resolved_scripts": (current_plan.stage_plan or {}).get("resolved_scripts") or {},
            "project_targets": (current_plan.stage_plan or {}).get("project_targets") or {},
            "builder": ((current_plan.stage_plan or {}).get("build_system_decision") or {}).get(
                "builder"
            ),
            "validation_policy_id": (
                (current_plan.stage_plan or {}).get("validation_policy") or {}
            ).get("policy_id"),
            "recovery_policy_id": (
                (current_plan.stage_plan or {}).get("recovery_policy") or {}
            ).get("policy_id"),
            "repair_policy_id": (
                (current_plan.stage_plan or {}).get("repair_policy") or {}
            ).get("policy_id"),
            "plan_version": migration_plan.version,
        }

    def materialize(self, context: dict[str, object]) -> StageExecutionPlan | None:
        observed = self._sealed_source_exact(Path(str(context["sealed_path"])))
        expected = self._version(context["current_target_exact"])
        if (
            not expected
            or not observed
            or expected.split(".", 1)[0] != observed.split(".", 1)[0]
        ):
            raise NextStageMaterializerError(
                "SEALED_VERSION_MISMATCH",
                "Sealed package and lockfile do not match the completed stage target",
            )
        remaining = list(context["remaining_route"])
        if not remaining:
            return None
        route = tuple(
            (
                str(item["source_family"]),
                str(item["target_family"]),
                str(item["stage_id"]),
                str(item["target_angular_exact"]),
                str(item.get("target_cli_exact") or item["target_angular_exact"]),
            )
            for item in remaining
        )
        request = PlanGenerationRequest(
            run_id=str(context["run_id"]),
            expected_state_version=1,
            idempotency_key=f"materialize:{context['run_id']}:{route[0][2]}",
            actor="transformer",
            correlation_id=f"materialize:{route[0][2]}",
            source_exact=observed,
            source_family=route[0][0],
            target_family=route[-1][1],
            catalogue_version=str(context["catalogue_version"]),
            input_fingerprint=str(context["sealed_fingerprint"]),
            evidence_set_checksum=str(context["sealed_fingerprint"]),
            input_workspace_fingerprint=str(context["sealed_fingerprint"]),
            execution_profile_id=str(context["execution_profile_id"]),
            execution_profile_checksum=str(context["execution_profile_checksum"]),
            package_manager="npm",
            resolved_scripts=dict(context["resolved_scripts"]),
            project_targets=dict(context["project_targets"]),
            stage_route=route,
            target_cli_exact=route[0][4],
            builder=str(context["builder"]),
            validation_policy_id=str(context["validation_policy_id"]),
            recovery_policy_id=str(context["recovery_policy_id"]),
            repair_policy_id=str(context["repair_policy_id"]),
        )
        try:
            return self._planner.create(request, plan_version=int(context["plan_version"]))
        except PlanningApplicationError as error:
            raise NextStageMaterializerError(error.code, error.message) from error

    def _sealed_source_exact(self, root: Path) -> str:
        package = json.loads((root / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
        declared_value = (
            ((package.get("dependencies") or {}).get("@angular/core"))
            or ((package.get("devDependencies") or {}).get("@angular/core"))
        )
        declared = self._version(declared_value)
        locked = self._version(LockfileCompatibilityService.resolve_package_version(lock, "@angular/core"))
        if (
            not declared
            or not locked
            or (str(declared_value).startswith(("^", "~")) and declared.split(".", 1)[0] != locked.split(".", 1)[0])
            or (not str(declared_value).startswith(("^", "~")) and declared != locked)
        ):
            raise NextStageMaterializerError(
                "SEALED_VERSION_EVIDENCE_INVALID",
                "Sealed package.json and package-lock.json disagree on @angular/core",
            )
        return locked

    def _version(self, value) -> str | None:
        match = self.semver.search(str(value or ""))
        return match.group("version") if match else None
