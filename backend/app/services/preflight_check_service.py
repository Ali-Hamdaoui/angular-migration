"""Preflight check orchestration service (V2 F16)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.domain.preflight_checks import PreflightCheckResult, PreflightVerdict, aggregate_verdict
from app.repositories.models import MigrationRunModel, PreflightCheckResultModel
from app.repositories.session import session_scope
from app.services.lockfile_compatibility_service import LockfileCompatibilityService
from app.services.project_capability_service import ProjectCapabilityService
from app.services.third_party_compatibility_service import ThirdPartyCompatibilityScanner


class PreflightCheckError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PreflightCheckService:
    """Compose deterministic preflight checks and produce a verdict (F16-01/03)."""

    def __init__(
        self,
        *,
        capability_service: ProjectCapabilityService | None = None,
        lockfile_service: LockfileCompatibilityService | None = None,
        dependency_scanner: ThirdPartyCompatibilityScanner | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._capabilities = capability_service or ProjectCapabilityService()
        self._lockfile = lockfile_service or LockfileCompatibilityService()
        self._dependencies = dependency_scanner or ThirdPartyCompatibilityScanner()
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def run_checks(self, run_id: str, source_root: Path) -> PreflightVerdict:
        """Run the composed check set against a source project (F16-01/02)."""
        checks: list[PreflightCheckResult] = []

        # 1. Capability readiness
        capabilities = self._capabilities.derive(source_root)
        capability_status, capability_blockers = self._capabilities.readiness(capabilities)
        checks.append(
            PreflightCheckResult(
                check_id="capability_readiness", name="project capability readiness",
                passed=capability_status == "ready",
                blockers=tuple(capability_blockers),
                detail=f"capability status {capability_status}",
            )
        )

        # 2. Lockfile source consistency (presence + parseability). Target-major
        # compatibility is validated per stage by the lockfile runner (F08).
        lockfile_checks = []
        try:
            dependency_set = self._lockfile.inspect_lockfile(source_root)
            if dependency_set.checksum == "missing":
                lockfile_checks.append("LOCKFILE_MISSING")
            elif dependency_set.lockfile_version is None and not dependency_set.resolved_packages:
                lockfile_checks.append("LOCKFILE_INVALID")
        except Exception as exc:
            lockfile_checks = [f"LOCKFILE_VALIDATION_ERROR:{type(exc).__name__}"]
        checks.append(
            PreflightCheckResult(
                check_id="lockfile_compatibility", name="lockfile presence and parseability",
                passed=not lockfile_checks,
                blockers=tuple(lockfile_checks),
                detail="lockfile present and parseable" if not lockfile_checks else "lockfile missing or invalid",
            )
        )

        # 3. Third-party dependency compatibility
        dependency_blockers = []
        try:
            stage = self._stage(run_id)
            if stage:
                report = self._dependencies.scan_stage(source_root, run_id=run_id, stage_id=stage.id)
                dependency_blockers = list(report.blockers)
        except Exception as exc:
            dependency_blockers = [f"DEPENDENCY_SCAN_ERROR:{type(exc).__name__}"]
        checks.append(
            PreflightCheckResult(
                check_id="dependency_compatibility", name="third-party dependency compatibility",
                passed=not dependency_blockers,
                blockers=tuple(dependency_blockers),
                detail="no dependency blockers" if not dependency_blockers else "dependency compatibility blocked",
            )
        )

        return aggregate_verdict(run_id, checks)

    def persist(self, run_id: str, verdict: PreflightVerdict) -> PreflightCheckResultModel:
        """Persist the preflight verdict (per-check evidence)."""
        with self._session_scope() as session:
            if session.get(MigrationRunModel, run_id) is None:
                raise PreflightCheckError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
            existing = session.scalar(
                select(PreflightCheckResultModel).where(
                    PreflightCheckResultModel.run_id == run_id,
                    PreflightCheckResultModel.checksum == verdict.checksum,
                )
            )
            if existing is not None:
                return existing
            row = PreflightCheckResultModel(
                id="pfc-" + hashlib.sha256(f"{run_id}:{verdict.checksum}".encode()).hexdigest()[:24],
                run_id=run_id,
                status=verdict.status,
                blockers=list(verdict.blockers),
                checks=[check.model_dump(mode="json") for check in verdict.checks],
                checksum=verdict.checksum,
                created_at=self._now_provider(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def get_run_verdict(self, run_id: str) -> PreflightCheckResultModel | None:
        with self._session_scope() as session:
            return session.scalar(
                select(PreflightCheckResultModel)
                .where(PreflightCheckResultModel.run_id == run_id)
                .order_by(PreflightCheckResultModel.created_at.desc())
                .limit(1)
            )

    def gate_run_start(self, run_id: str) -> PreflightCheckResultModel:
        """F16-04: run start is gated on the preflight verdict (fail-closed)."""
        verdict = self.get_run_verdict(run_id)
        if verdict is None:
            raise PreflightCheckError("PREFLIGHT_REQUIRED", f"run {run_id} has no preflight verdict")
        if verdict.status == "blocked":
            raise PreflightCheckError("PREFLIGHT_BLOCKED", f"run {run_id} preflight is blocked; blockers: {', '.join(verdict.blockers)}")
        return verdict

    def _stage(self, run_id: str):
        from app.repositories.models import MigrationStageModel

        with self._session_scope() as session:
            return session.scalar(
                select(MigrationStageModel)
                .where(MigrationStageModel.run_id == run_id)
                .order_by(MigrationStageModel.stage_order.asc())
                .limit(1)
            )
