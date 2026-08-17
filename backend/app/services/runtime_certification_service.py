"""Bridge runtime certification service (V2 F11)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.runtime_certification import RuntimeCertificationDecision, evaluate_certification
from app.repositories.models import MigrationStageModel, RuntimeCertificationModel
from app.repositories.session import session_scope
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
from app.services.stage_runtime_service import StageRuntimeApplicationService, StageRuntimeError


class RuntimeCertificationError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class RuntimeCertificationService:
    """Certify stage runtime bindings against the catalogue and enforce the gate."""

    def __init__(
        self,
        *,
        catalogue_provider: CompatibilityCatalogueProvider | None = None,
        stage_runtime_service: StageRuntimeApplicationService | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalogue_provider = catalogue_provider or CompatibilityCatalogueProvider()
        self._stage_runtime = stage_runtime_service or StageRuntimeApplicationService()
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def certify_stage(self, stage_id: str) -> RuntimeCertificationDecision:
        """Resolve the stage runtime and certify it against the catalogue."""
        families = self._stage_runtime.stage_version_families(stage_id)
        catalogue = self._catalogue_provider.load()
        entry = catalogue.entry_for(families[0], families[1])
        if entry is None:
            raise RuntimeCertificationError("CATALOGUE_ENTRY_MISSING", f"No catalogue entry for {families[0]} -> {families[1]}")
        if not entry.validated_runtime_profiles and not entry.source_node_ranges and not entry.target_node_ranges:
            decision = RuntimeCertificationDecision(
                run_id=self._stage_run_id(stage_id), stage_id=stage_id,
                source_family=families[0], target_family=families[1],
                certified=False, allowed=False, classification="UNSUPPORTED",
                reason="transition has no certified runtime profiles yet",
                certified_against=catalogue.version, resolved_at=self._now_provider(),
            )
            return self._persist_decision(decision, None, None)
        binding = self._stage_runtime.resolve_stage(stage_id, families[0], families[1])
        node = binding.descriptor_for(_kind("node"))
        npm = binding.descriptor_for(_kind("npm"))
        npx = binding.descriptor_for(_kind("npx"))
        decision = evaluate_certification(
            run_id=self._stage_run_id(stage_id),
            stage_id=stage_id,
            source_family=families[0],
            target_family=families[1],
            node_descriptor=node,
            npm_descriptor=npm,
            npx_descriptor=npx,
            catalogue_validated_profiles=entry.validated_runtime_profiles,
            source_node_ranges=entry.source_node_ranges,
            target_node_ranges=entry.target_node_ranges,
            catalogue_version=catalogue.version,
            resolved_at=self._now_provider(),
        )
        return self._persist_decision(decision, node, npm)

    def _stage_run_id(self, stage_id: str) -> str:
        with self._session_scope() as session:
            stage = session.get(MigrationStageModel, stage_id)
            return stage.run_id if stage else ""

    def _persist_decision(self, decision: RuntimeCertificationDecision, node, npm) -> RuntimeCertificationDecision:
        with self._session_scope() as session:
            record_id = _certification_id(decision.stage_id, node.sha256 if node else "none")
            existing = session.get(RuntimeCertificationModel, record_id)
            if existing is not None:
                return decision
            session.add(
                RuntimeCertificationModel(
                    id=record_id,
                    run_id=decision.run_id,
                    stage_id=decision.stage_id,
                    source_family=decision.source_family,
                    target_family=decision.target_family,
                    runtime_id=decision.runtime_id,
                    node_version=decision.node_exact,
                    npm_version=decision.npm_exact,
                    node_sha256=node.sha256 if node else None,
                    npm_sha256=npm.sha256 if npm else None,
                    certified=decision.certified,
                    allowed=decision.allowed,
                    classification=decision.classification,
                    reason=decision.reason,
                    certified_against=decision.certified_against,
                    created_at=decision.resolved_at,
                )
            )
            session.commit()
        return decision

    def is_stage_certified(self, stage_id: str) -> RuntimeCertificationDecision | None:
        """Return the latest certification decision for a stage, if any."""
        with self._session_scope() as session:
            record = session.scalar(
                select(RuntimeCertificationModel)
                .where(RuntimeCertificationModel.stage_id == stage_id, RuntimeCertificationModel.certified.is_(True))
                .order_by(RuntimeCertificationModel.created_at.desc())
                .limit(1)
            )
            if record is None:
                return None
            return RuntimeCertificationDecision(
                run_id=record.run_id, stage_id=record.stage_id,
                source_family=record.source_family, target_family=record.target_family,
                runtime_id=record.runtime_id, node_exact=record.node_version, npm_exact=record.npm_version,
                certified=record.certified, allowed=record.allowed, classification=record.classification,
                reason=record.reason, certified_against=record.certified_against,
                resolved_at=record.created_at,
            )

    def enforce_stage_certification(self, stage_id: str) -> RuntimeCertificationDecision:
        """Pre-execution gate: a stage must have a certified runtime to proceed (F11-03).

        The runtime is certified on demand when the machine provides a profile the
        catalogue validates; otherwise the gate fails closed with
        RUNTIME_NOT_CERTIFIED.
        """
        families = self._stage_runtime.stage_version_families(stage_id)
        entry = self._catalogue_provider.load().entry_for(families[0], families[1])
        if entry is None:
            raise RuntimeCertificationError(
                "RUNTIME_NOT_CERTIFIED",
                f"stage {stage_id} ({families[0]} -> {families[1]}) has no certified runtime profile",
            )
        decision = self.certify_stage(stage_id)
        if not decision.allowed:
            raise RuntimeCertificationError(
                "RUNTIME_NOT_CERTIFIED",
                decision.reason or "stage runtime is not certified for the transition",
                {"stage_id": stage_id, "runtime_id": decision.runtime_id},
            )
        return decision

    def list_stage_certifications(self, stage_id: str) -> list[RuntimeCertificationModel]:
        with self._session_scope() as session:
            return list(
                session.scalars(
                    select(RuntimeCertificationModel)
                    .where(RuntimeCertificationModel.stage_id == stage_id)
                    .order_by(RuntimeCertificationModel.created_at.desc())
                ).all()
            )


def _kind(name: str):
    from app.domain.runtime_execution import RuntimeExecutableKind

    return RuntimeExecutableKind(name)


def _certification_id(stage_id: str, sha256: str) -> str:
    return "cert-" + hashlib.sha256(f"{stage_id}:{sha256}".encode()).hexdigest()[:24]
