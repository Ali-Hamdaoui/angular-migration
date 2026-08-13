"""Derive one exact later stage from a sealed output and the approved route."""

from __future__ import annotations

import json
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.domain.planning import PlanGenerationRequest, StageExecutionPlan
from app.repositories.models import (
    CompatibilityResolutionModel,
    EnvironmentCapabilityModel,
    ExecutionProfileModel,
    MigrationRunModel,
    MigrationPlanModel,
    StageExecutionPlanModel,
)
from app.services.planning_application_service import (
    PlanningApplicationError,
    StageExecutionPlanService,
    run_scoped_stage_id,
)


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
        remaining_route = route[current_index + 1 :]
        if remaining_route and resolution.catalogue_version == "catalog-v3":
            profile = self._select_successor_profile(
                session,
                continuation.run_id,
                str((current_plan.stage_plan or {}).get("target_exact") or ""),
                remaining_route[0],
            )
        return {
            "run_id": continuation.run_id,
            "sealed_path": sealed_path,
            "sealed_fingerprint": sealed_fingerprint,
            "current_target_exact": (current_plan.stage_plan or {}).get("target_exact"),
            "remaining_route": remaining_route,
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

    @staticmethod
    def _select_successor_profile(session, run_id: str, source_exact: str, route_entry: dict) -> ExecutionProfileModel:
        """Persist the exact catalogue/runtime binding for the successor stage."""
        environment = session.scalar(
            select(EnvironmentCapabilityModel).order_by(EnvironmentCapabilityModel.created_at.desc())
        )
        profiles = (environment.snapshot or {}).get("runtime_profiles", []) if environment else []
        node_exact = str(route_entry.get("node_exact") or "")
        npm_exact = str(route_entry.get("npm_exact") or "")
        candidate = next(
            (
                item for item in profiles
                if str(item.get("node_exact")) == node_exact
                and str(item.get("npm_exact")) == npm_exact
                and str(item.get("npx_exact")) == npm_exact
            ),
            None,
        )
        if candidate is None:
            raise NextStageMaterializerError(
                "NEXT_STAGE_RUNTIME_UNAVAILABLE",
                f"No configured runtime matches Node {node_exact} / npm {npm_exact}",
            )
        now = datetime.now(UTC)
        key = f"stage-runtime:{route_entry['stage_id']}"
        existing = session.scalar(select(ExecutionProfileModel).where(
            ExecutionProfileModel.run_id == run_id,
            ExecutionProfileModel.idempotency_key == key,
        ))
        existing_payload = (
            (existing.profiles or [None])[0]
            if existing is not None
            else None
        )
        validated_at = (
            existing_payload.get("validated_at")
            if isinstance(existing_payload, dict)
            else candidate.get("validated_at")
        ) or environment.created_at.isoformat()
        payload = {
            "profile_id": str(candidate["profile_id"]),
            "operating_system": "windows", "architecture": "amd64",
            "node_executable": str(candidate["node_executable"]), "node_exact": node_exact,
            "package_manager": "npm",
            "package_manager_executable": str(candidate["npm_executable"]),
            "package_manager_exact": npm_exact,
            "npx_executable": str(candidate["npx_executable"]), "npx_exact": npm_exact,
            "angular_cli_execution": "npx",
            "angular_cli_exact": str(route_entry.get("target_cli_exact") or route_entry.get("target_angular_exact")),
            "proxy_profile": "configured", "certificate_profile": "validated",
            "network_policy": "approved-registries-only",
            "environment_allowlist": ["PATH", "HTTP_PROXY", "HTTPS_PROXY"],
            "cache_policy": "approved",
            "compatibility_catalog_version": "catalog-v3-stage-runtime-v1",
            "source_angular_exact": source_exact,
            "validated_at": str(validated_at),
        }
        checksum = "sha256:" + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        payload["checksum"] = checksum
        if existing:
            if existing.selected_checksum != checksum:
                raise NextStageMaterializerError(
                    "NEXT_STAGE_RUNTIME_DRIFT", "Persisted successor runtime no longer matches inventory"
                )
            return existing
        run = session.get(MigrationRunModel, run_id)
        record = ExecutionProfileModel(
            id=f"profile-{hashlib.sha256((run_id + key).encode()).hexdigest()[:24]}",
            run_id=run_id, idempotency_key=key, request_checksum=checksum,
            policy_version="catalog-v3-stage-runtime-v1", status="resolved",
            source_angular_exact=source_exact,
            selected_profile_id=payload["profile_id"], selected_checksum=checksum,
            profiles=[payload], blockers=[], guidance=[], artifact_ids=[],
            state_version=run.state_version, event_sequence=0,
            created_at=now, updated_at=now,
        )
        session.add(record)
        session.flush()
        return record

    def materialize(self, context: dict[str, object]) -> StageExecutionPlan | None:
        observed = self._sealed_source_exact(Path(str(context["sealed_path"])))
        expected = self._version(context["current_target_exact"])
        if (
            not expected
            or not observed
            or expected != observed
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
        declared = self._version(
            ((package.get("dependencies") or {}).get("@angular/core"))
            or ((package.get("devDependencies") or {}).get("@angular/core"))
        )
        packages = lock.get("packages") or {}
        modern = (
            packages.get("node_modules/@angular/core") or {}
            if isinstance(packages, dict)
            else {}
        )
        dependencies = lock.get("dependencies") or {}
        legacy = (
            dependencies.get("@angular/core") or {}
            if isinstance(dependencies, dict)
            else {}
        )
        locked = self._version(modern.get("version")) or self._version(
            legacy.get("version")
        )
        if (
            not declared
            or not locked
            or declared != locked
        ):
            raise NextStageMaterializerError(
                "SEALED_VERSION_EVIDENCE_INVALID",
                "Sealed package.json and package-lock.json disagree on @angular/core",
            )
        return locked

    def _version(self, value) -> str | None:
        match = self.semver.search(str(value or ""))
        return match.group("version") if match else None
