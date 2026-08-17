"""V2 analyzer and planner service (F18)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.domain.v2_planning import V2AnalysisFinding, V2MigrationPlan, V2PlannedStage
from app.repositories.models import MigrationRunModel, V2PlanningModel
from app.repositories.session import session_scope
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
from app.services.migration_route_service import MigrationRouteService
from app.services.project_capability_service import ProjectCapabilityService
from app.services.stage_knowledge_service import StageKnowledgeRegistry


class V2PlanningError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class V2PlannerService:
    """Derive deterministic analysis findings and migration plans (F18-01/02)."""

    def __init__(
        self,
        *,
        route_service: MigrationRouteService | None = None,
        catalogue_provider: CompatibilityCatalogueProvider | None = None,
        capability_service: ProjectCapabilityService | None = None,
        knowledge_registry: StageKnowledgeRegistry | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._route = route_service or MigrationRouteService()
        self._catalogue = catalogue_provider or CompatibilityCatalogueProvider()
        self._capabilities = capability_service or ProjectCapabilityService()
        self._knowledge = knowledge_registry or StageKnowledgeRegistry()
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def _run_context(self, run_id: str) -> tuple[str, str]:
        with self._session_scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise V2PlanningError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
            if not run.source_version_family or not run.target_version_family:
                raise V2PlanningError("RUN_FAMILIES_MISSING", "run source/target version families are not set")
            return (run.source_version_family, run.target_version_family)

    def analyze(self, run_id: str, source_root: Path | None = None) -> list[V2AnalysisFinding]:
        """Derive deterministic findings for a run (F18-01)."""
        source_family, target_family = self._run_context(run_id)
        findings: list[V2AnalysisFinding] = []
        try:
            route = self._route.compute(_major(source_family), _major(target_family))
            findings.append(V2AnalysisFinding(finding_id="route_derived", severity="info", message=f"route {source_family} -> {target_family} derived ({len(route.stages)} stages)"))
        except Exception as exc:
            findings.append(V2AnalysisFinding(finding_id="route_failed", severity="blocker", message=f"route derivation failed: {exc}"))
            return findings
        if source_root is not None:
            capabilities = self._capabilities.derive(source_root)
            _status, blockers = self._capabilities.readiness(capabilities)
            if blockers:
                findings.append(V2AnalysisFinding(finding_id="capability_blockers", severity="blocker", message="; ".join(blockers)))
            else:
                findings.append(V2AnalysisFinding(finding_id="capability_ready", severity="info", message="project capability ready"))
        return findings

    def derive_plan(
        self,
        run_id: str,
        source_root: Path | None = None,
        *,
        capability_snapshot_id: str | None = None,
    ) -> V2MigrationPlan:
        """Derive the deterministic migration plan (F18-02).

        Source capabilities are bound to an immutable persisted snapshot. A
        later validation therefore reloads the same facts instead of inspecting
        a mutable workspace or silently using an empty capability set.
        """
        try:
            source_family, target_family = self._run_context(run_id)
            source_major = _major(source_family)
            target_major = _major(target_family)
            route = self._route.compute(source_major, target_major)
            catalogue = self._catalogue.load()
            findings = self.analyze(run_id, None)
            snapshot = None
            if source_root is not None:
                snapshot = self._capabilities.snapshot(run_id, source_root)
            elif capability_snapshot_id is not None:
                snapshot = self._capabilities.get_snapshot(run_id, capability_snapshot_id)
            capabilities = list(snapshot.capabilities) if snapshot is not None else []
            stages: list[V2PlannedStage] = []
            for stage in route.stages:
                entry = catalogue.entry_for(stage.source_family, stage.target_family)
                knowledge = self._knowledge.entry(stage.source_major, stage.target_major)
                stages.append(
                    V2PlannedStage(
                        stage_order=stage.stage_order,
                        source_major=stage.source_major,
                        target_major=stage.target_major,
                        source_family=stage.source_family,
                        target_family=stage.target_family,
                        target_exact=entry.target_angular_exact if entry else f"{stage.target_major}.0.0",
                        node_minimum=entry.node_minimum if entry else None,
                        expected_transforms=knowledge.expected_transforms,
                        validation_expectations=knowledge.validation_expectations,
                        expected_dependency_changes=self._knowledge.dependency_dispositions(knowledge, capabilities),
                    )
                )
        except V2PlanningError:
            raise
        except Exception as exc:
            raise V2PlanningError("PLAN_DERIVATION_FAILED", f"plan derivation failed: {exc}") from exc
        plan = V2MigrationPlan(
            run_id=run_id,
            source_major=source_major,
            target_major=target_major,
            catalogue_version=catalogue.version,
            capability_snapshot_id=(self._capabilities.snapshot_id(run_id, snapshot.checksum) if snapshot else None),
            capability_snapshot_checksum=snapshot.checksum if snapshot else None,
            findings=tuple(findings),
            stages=tuple(stages),
        )
        return plan.bind_checksum()

    def persist(self, run_id: str, plan: V2MigrationPlan) -> V2PlanningModel:
        """Persist the deterministic plan (F18-04)."""
        with self._session_scope() as session:
            if session.get(MigrationRunModel, run_id) is None:
                raise V2PlanningError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
            existing = session.scalar(
                select(V2PlanningModel).where(
                    V2PlanningModel.run_id == run_id,
                    V2PlanningModel.checksum == plan.checksum,
                )
            )
            if existing is not None:
                return existing
            row = V2PlanningModel(
                id="v2p-" + hashlib.sha256(f"{run_id}:{plan.checksum}".encode()).hexdigest()[:24],
                run_id=run_id,
                source_major=plan.source_major,
                target_major=plan.target_major,
                catalogue_version=plan.catalogue_version,
                capability_snapshot_id=plan.capability_snapshot_id,
                capability_snapshot_checksum=plan.capability_snapshot_checksum,
                findings=[finding.model_dump(mode="json") for finding in plan.findings],
                stages=[stage.model_dump(mode="json") for stage in plan.stages],
                checksum=plan.checksum,
                created_at=self._now_provider(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def get_run_plan(self, run_id: str) -> V2PlanningModel | None:
        with self._session_scope() as session:
            return session.scalar(
                select(V2PlanningModel)
                .where(V2PlanningModel.run_id == run_id)
                .order_by(V2PlanningModel.created_at.desc())
                .limit(1)
            )

    def validate_plan(self, run_id: str) -> V2MigrationPlan:
        """Recompute the plan deterministically and compare with the persisted one.

        Raises PLAN_DRIFT when the persisted plan no longer matches the
        catalogue/knowledge-derived plan (immutability enforcement, F18-03).
        """
        persisted = self.get_run_plan(run_id)
        if persisted is None:
            raise V2PlanningError("PLAN_NOT_PERSISTED", f"run {run_id} has no persisted V2 plan")
        derived = self.derive_plan(run_id, capability_snapshot_id=persisted.capability_snapshot_id)
        if persisted.checksum != derived.checksum or persisted.source_major != derived.source_major or persisted.target_major != derived.target_major:
            raise V2PlanningError(
                "PLAN_DRIFT",
                "The persisted V2 plan drifted from the catalogue/knowledge-derived plan",
            )
        return derived


def _major(family: str | None) -> int:
    if not family:
        return 0
    try:
        return int(family.removeprefix("angular-").removesuffix(".x"))
    except ValueError:
        return 0
