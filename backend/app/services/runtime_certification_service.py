"""Bridge runtime certification service (V2 F11 / V2.2 P0-0).

PRODUCTION requires an exact Factory-certified profile backed by promoted
immutable evidence. QUALIFICATION may exercise an officially allowed profile
only under explicit immutable authorization and can never certify itself:
certification appears only through deterministic evidence promotion that
validates the complete reviewed bundle before writing certified truth.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.artifact_store.local_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType
from app.domain.runtime_certification import (
    RuntimeCertificationDecision,
    RuntimeCertificationPromotionDecision,
    RuntimeQualificationAuthorization,
    RuntimeQualificationEvidence,
    evaluate_certification,
    qualification_authorization_path,
    qualification_evidence_path,
    qualification_promotion_path,
    runtime_certification_artifact_path,
)
from app.repositories.models import MigrationRunModel, MigrationStageModel, RuntimeCertificationModel
from app.repositories.session import session_scope
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
from app.services.stage_runtime_service import StageRuntimeApplicationService


class RuntimeCertificationError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class _DescriptorIdentity:
    kind: str
    path: str
    version: str
    sha256: str


class RuntimeCertificationService:
    """Certify stage runtime bindings against the catalogue and enforce the gate."""

    def __init__(
        self,
        *,
        catalogue_provider: CompatibilityCatalogueProvider | None = None,
        stage_runtime_service: StageRuntimeApplicationService | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
        artifact_store: LocalFilesystemArtifactStore | None = None,
    ) -> None:
        self._catalogue_provider = catalogue_provider or CompatibilityCatalogueProvider()
        self._stage_runtime = stage_runtime_service or StageRuntimeApplicationService()
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._artifact_store = artifact_store

    def certify_stage(self, stage_id: str) -> RuntimeCertificationDecision:
        """Resolve the stage runtime and evaluate it against the catalogue.

        This is evaluation only: it never writes a certified decision. Exact
        certification is owned exclusively by ``promote_qualification_evidence``.
        """
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
        # Evaluation-only persistence: certified truth is written exclusively by
        # promote_qualification_evidence, so this projection never stores
        # certified=True even if a legacy catalogue version classifies exactly.
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
                    certified=False,
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
        record = self._latest_certified_record(stage_id)
        if record is None:
            return None
        return self._decision_from_record(record)

    def enforce_stage_certification(self, stage_id: str) -> RuntimeCertificationDecision:
        """Pre-execution PRODUCTION gate: require an exact certified profile.

        ``allowed`` is insufficient; an officially compatible but uncertified
        runtime blocks with STAGE_RUNTIME_CERTIFICATION_REQUIRED. A certified
        row is accepted only after its immutable certification artifact at the
        deterministic path revalidates; the row remains an indexed projection.
        """
        families = self._stage_runtime.stage_version_families(stage_id)
        entry = self._catalogue_provider.load().entry_for(families[0], families[1])
        if entry is None:
            raise RuntimeCertificationError(
                "STAGE_RUNTIME_CERTIFICATION_REQUIRED",
                f"stage {stage_id} ({families[0]} -> {families[1]}) has no certified runtime profile",
            )
        record = self._latest_certified_record(stage_id)
        if record is None:
            raise RuntimeCertificationError(
                "STAGE_RUNTIME_CERTIFICATION_REQUIRED",
                f"stage {stage_id} has no promoted runtime certification evidence",
            )
        self._revalidate_certification_artifact(record)
        return RuntimeCertificationDecision(
            run_id=record.run_id, stage_id=record.stage_id,
            source_family=record.source_family, target_family=record.target_family,
            runtime_id=record.runtime_id, node_exact=record.node_version, npm_exact=record.npm_version,
            certified=True, allowed=True, classification="EXACT_CERTIFIED",
            reason=record.reason, certified_against=record.certified_against,
            resolved_at=record.created_at,
        )

    def authorize_qualification(self, authorization: RuntimeQualificationAuthorization) -> str:
        """Persist the immutable qualification authorization at its deterministic path."""
        store = self._store_for_run(authorization.run_id, "QUALIFICATION_AUTHORIZATION_UNAVAILABLE")
        catalogue = self._catalogue_provider.load()
        if authorization.catalogue_checksum != catalogue.checksum:
            raise RuntimeCertificationError(
                "QUALIFICATION_AUTHORIZATION_CATALOGUE_MISMATCH",
                "authorization binds a different compatibility catalogue checksum",
            )
        if authorization.expires_at <= self._now_provider():
            raise RuntimeCertificationError(
                "QUALIFICATION_AUTHORIZATION_EXPIRED",
                "qualification authorization has expired",
            )
        if not authorization.runtime_descriptor_checksums:
            raise RuntimeCertificationError(
                "QUALIFICATION_AUTHORIZATION_INCOMPLETE",
                "qualification authorization must bind exact runtime descriptor checksums",
            )
        scope = _scope_from_stage_id(authorization.stage_id)
        relative_path = qualification_authorization_path(scope, authorization.digest)
        return self._write_json(store, authorization.run_id, relative_path, authorization)

    def record_qualification_evidence(self, evidence: RuntimeQualificationEvidence) -> str:
        """Persist immutable qualification evidence under its authorization digest."""
        store = self._store_for_run(evidence.run_id, "QUALIFICATION_EVIDENCE_UNAVAILABLE")
        authorization = self._load_qualification_authorization(
            evidence.run_id, evidence.stage_id, evidence.authorization_checksum
        )
        if evidence.authorization_checksum != authorization.authorization_checksum:
            raise RuntimeCertificationError(
                "QUALIFICATION_EVIDENCE_AUTHORIZATION_MISMATCH",
                "evidence does not bind the persisted qualification authorization",
            )
        self._require_live_authorization(authorization)
        unbound = set(evidence.descriptor_checksums) - set(authorization.runtime_descriptor_checksums)
        if unbound:
            raise RuntimeCertificationError(
                "QUALIFICATION_EVIDENCE_DESCRIPTOR_MISMATCH",
                "evidence descriptors are not covered by the authorization",
            )
        if evidence.catalogue_checksum != self._catalogue_provider.load().checksum:
            raise RuntimeCertificationError(
                "QUALIFICATION_EVIDENCE_CATALOGUE_MISMATCH",
                "evidence binds a different compatibility catalogue checksum",
            )
        digest = authorization.digest
        scope = _scope_from_stage_id(evidence.stage_id)
        return self._write_json(
            store, evidence.run_id, qualification_evidence_path(scope, digest), evidence
        )

    def promote_qualification_evidence(
        self, run_id: str, stage_id: str, promotion: RuntimeCertificationPromotionDecision
    ) -> RuntimeCertificationDecision:
        """Deterministic certification promotion from reviewed complete evidence.

        Validates the persisted immutable bundle (authorization + evidence +
        explicit accepted reviewer decision), official-envelope membership of
        the exact descriptors, and checksum integrity. Command success alone
        never promotes. Idempotent per derived record identity.
        """
        store = self._store_for_run(run_id, "CERTIFICATION_PROMOTION_UNAVAILABLE")
        scope = _scope_from_stage_id(stage_id)
        review_path = qualification_promotion_path(scope, promotion.authorization_checksum.removeprefix("sha256:"))
        review = self._load_json(store, run_id, review_path, RuntimeCertificationPromotionDecision)
        if review.model_dump(mode="json") != promotion.model_dump(mode="json"):
            raise RuntimeCertificationError(
                "CERTIFICATION_PROMOTION_REVIEW_MISMATCH",
                "promotion decision does not match the persisted reviewed decision",
            )
        if promotion.decision != "accepted":
            raise RuntimeCertificationError(
                "CERTIFICATION_PROMOTION_NOT_ACCEPTED",
                "certification requires an explicitly accepted reviewer decision",
            )
        digest = promotion.authorization_checksum.removeprefix("sha256:")
        authorization = self._load_qualification_authorization(run_id, stage_id, promotion.authorization_checksum)
        self._require_live_authorization(authorization)
        evidence_path = qualification_evidence_path(scope, digest)
        evidence_ref = self._find_artifact(store, run_id, evidence_path)
        if evidence_ref is None:
            raise RuntimeCertificationError(
                "CERTIFICATION_PROMOTION_EVIDENCE_MISSING",
                "qualification evidence artifact is missing",
            )
        if promotion.evidence_checksum != evidence_ref.checksum:
            raise RuntimeCertificationError(
                "CERTIFICATION_PROMOTION_EVIDENCE_CHECKSUM_MISMATCH",
                "promotion binds a different evidence checksum",
            )
        evidence = self._load_json(store, run_id, evidence_path, RuntimeQualificationEvidence)
        families = (authorization.source_family, authorization.target_family)
        entry = self._catalogue_provider.load().entry_for(families[0], families[1])
        if (
            entry is None
            or not CompatibilityCatalogueProvider.node_in_official_intersection(
                evidence.node_exact, entry.source_node_ranges, entry.target_node_ranges
            )
            or evidence.catalogue_checksum != self._catalogue_provider.load().checksum
        ):
            raise RuntimeCertificationError(
                "CERTIFICATION_PROMOTION_OUTSIDE_OFFICIAL_ENVELOPE",
                "exact runtime is outside the official compatibility envelope",
            )
        record_id = _promoted_certification_id(stage_id, evidence, promotion)
        existing = self._get_record(record_id)
        if existing is not None:
            return self._decision_from_record(existing)
        node = _DescriptorIdentity("node", evidence.node_path, evidence.node_exact, evidence.node_sha256)
        npm = _DescriptorIdentity("npm", evidence.npm_path, evidence.npm_exact, evidence.npm_sha256)
        decision = RuntimeCertificationDecision(
            run_id=run_id, stage_id=stage_id, source_family=families[0], target_family=families[1],
            runtime_id=evidence.node_path, node_exact=evidence.node_exact, npm_exact=evidence.npm_exact,
            certified=True, allowed=True, classification="EXACT_CERTIFIED",
            reason="promoted from reviewed complete qualification evidence",
            certified_against=self._catalogue_provider.load().version,
            resolved_at=promotion.decided_at, run_mode="PRODUCTION",
        )
        self._write_json(
            store,
            run_id,
            runtime_certification_artifact_path(scope, record_id),
            decision,
            stage_id=stage_id,
        )
        try:
            with self._session_scope() as session:
                session.add(
                    RuntimeCertificationModel(
                        id=record_id,
                        run_id=run_id,
                        stage_id=stage_id,
                        source_family=decision.source_family,
                        target_family=decision.target_family,
                        runtime_id=decision.runtime_id,
                        node_version=decision.node_exact,
                        npm_version=decision.npm_exact,
                        node_sha256=node.sha256,
                        npm_sha256=npm.sha256,
                        certified=True,
                        allowed=True,
                        classification="EXACT_CERTIFIED",
                        reason=decision.reason,
                        certified_against=decision.certified_against,
                        created_at=decision.resolved_at,
                    )
                )
                session.commit()
        except IntegrityError:
            return self._decision_from_record(self._get_record(record_id))
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

    # ------------------------------------------------------------------
    # internal helpers

    def _store_for_run(self, run_id: str, code: str) -> LocalFilesystemArtifactStore:
        """Resolve the immutable store from the run artifact root (code truth)."""
        if self._artifact_store is not None:
            return self._artifact_store
        with self._session_scope() as session:
            run = session.get(MigrationRunModel, run_id)
        if run is None or not run.artifact_root:
            raise RuntimeCertificationError(code, "run artifact root unavailable for immutable runtime evidence")
        root = Path(run.artifact_root).resolve()
        return LocalFilesystemArtifactStore(root, fixed_run_root=root)

    def _write_json(
        self,
        store: LocalFilesystemArtifactStore,
        run_id: str,
        relative_path: str,
        contract,
        *,
        stage_id: str | None = None,
    ) -> str:
        stored = store.write_text_artifact(
            run_id,
            relative_path,
            contract.model_dump_json(),
            ArtifactType.JSON,
            stage_id=stage_id,
            created_by="runtime-certification",
            policy_version="runtime-certification-v1",
        )
        return stored.ref.artifact_id

    def _load_json(self, store: LocalFilesystemArtifactStore, run_id: str, relative_path: str, contract):
        try:
            stored = store.read_artifact(run_id, relative_path)
        except Exception as error:
            raise RuntimeCertificationError(
                "RUNTIME_QUALIFICATION_ARTIFACT_MISSING",
                f"required qualification artifact is unavailable: {relative_path}",
            ) from error
        try:
            return contract.model_validate(json.loads(stored.content))
        except Exception as error:
            raise RuntimeCertificationError(
                "RUNTIME_QUALIFICATION_ARTIFACT_INVALID",
                f"qualification artifact failed contract validation: {relative_path}",
            ) from error

    def _find_artifact(self, store: LocalFilesystemArtifactStore, run_id: str, relative_path: str):
        for ref in store.list_artifacts(run_id):
            if ref.relative_path == relative_path:
                return ref
        return None

    def _load_qualification_authorization(
        self, run_id: str, stage_id: str, authorization_checksum: str
    ) -> RuntimeQualificationAuthorization:
        """Load the authorization deterministically by its own checksum digest."""
        store = self._store_for_run(run_id, "RUNTIME_QUALIFICATION_ARTIFACT_MISSING")
        scope = _scope_from_stage_id(stage_id)
        digest = authorization_checksum.removeprefix("sha256:")
        relative_path = qualification_authorization_path(scope, digest)
        try:
            stored = store.read_artifact(run_id, relative_path)
            return RuntimeQualificationAuthorization.model_validate(json.loads(stored.content))
        except RuntimeCertificationError:
            raise
        except Exception as error:
            raise RuntimeCertificationError(
                "RUNTIME_QUALIFICATION_ARTIFACT_INVALID",
                f"qualification authorization failed contract validation: {relative_path}",
            ) from error

    def _require_live_authorization(self, authorization: RuntimeQualificationAuthorization) -> None:
        """Stale or expired authorizations never authorize evidence or promotion."""
        if authorization.expires_at <= self._now_provider():
            raise RuntimeCertificationError(
                "QUALIFICATION_AUTHORIZATION_EXPIRED",
                "qualification authorization has expired",
            )

    def _latest_certified_record(self, stage_id: str) -> RuntimeCertificationModel | None:
        with self._session_scope() as session:
            return session.scalar(
                select(RuntimeCertificationModel)
                .where(RuntimeCertificationModel.stage_id == stage_id, RuntimeCertificationModel.certified.is_(True))
                .order_by(RuntimeCertificationModel.created_at.desc())
                .limit(1)
            )

    def _revalidate_certification_artifact(self, record: RuntimeCertificationModel) -> None:
        store = self._store_for_run(record.run_id, "STAGE_RUNTIME_CERTIFICATION_REQUIRED")
        scope = _scope_from_stage_id(record.stage_id)
        relative_path = runtime_certification_artifact_path(scope, record.id)
        try:
            stored = store.read_artifact(record.run_id, relative_path)
            decision = RuntimeCertificationDecision.model_validate(json.loads(stored.content))
        except Exception as error:
            raise RuntimeCertificationError(
                "STAGE_RUNTIME_CERTIFICATION_REQUIRED",
                f"immutable certification artifact failed revalidation for stage {record.stage_id}",
            ) from error
        if (
            not decision.certified
            or decision.stage_id != record.stage_id
            or decision.run_id != record.run_id
        ):
            raise RuntimeCertificationError(
                "STAGE_RUNTIME_CERTIFICATION_REQUIRED",
                f"certification artifact contradicts the projection row for stage {record.stage_id}",
            )

    def _get_record(self, record_id: str) -> RuntimeCertificationModel | None:
        with self._session_scope() as session:
            return session.get(RuntimeCertificationModel, record_id)

    def _decision_from_record(self, record: RuntimeCertificationModel) -> RuntimeCertificationDecision:
        return RuntimeCertificationDecision(
            run_id=record.run_id, stage_id=record.stage_id,
            source_family=record.source_family, target_family=record.target_family,
            runtime_id=record.runtime_id, node_exact=record.node_version, npm_exact=record.npm_version,
            certified=record.certified, allowed=record.allowed, classification=record.classification,
            reason=record.reason, certified_against=record.certified_against,
            resolved_at=record.created_at,
        )


def certified_profiles_for_families(
    source_family: str, target_family: str
) -> tuple[tuple[str, str], ...]:
    """Promoted certified exact (node, npm) profiles for a stage transition.

    Planning feasibility consults this so a reviewed and promoted profile
    becomes production-eligible; execution still revalidates the immutable
    certification artifact through ``enforce_stage_certification``.
    """
    with session_scope() as session:
        rows = session.scalars(
            select(RuntimeCertificationModel)
            .where(
                RuntimeCertificationModel.certified.is_(True),
                RuntimeCertificationModel.source_family == source_family,
                RuntimeCertificationModel.target_family == target_family,
            )
        ).all()
    return tuple(sorted({(row.node_version, row.npm_version) for row in rows if row.node_version and row.npm_version}))


def _kind(name: str):
    from app.domain.runtime_execution import RuntimeExecutableKind

    return RuntimeExecutableKind(name)


def _certification_id(stage_id: str, sha256: str) -> str:
    return "cert-" + hashlib.sha256(f"{stage_id}:{sha256}".encode()).hexdigest()[:24]


def _promoted_certification_id(
    stage_id: str,
    evidence: RuntimeQualificationEvidence,
    promotion: RuntimeCertificationPromotionDecision,
) -> str:
    payload = ":".join(
        (
            stage_id,
            evidence.node_sha256,
            evidence.npm_sha256,
            evidence.npx_sha256,
            evidence.catalogue_checksum,
            promotion.evidence_checksum,
            promotion.promotion_checksum,
        )
    )
    return "cert-" + hashlib.sha256(payload.encode()).hexdigest()[:24]


def _scope_from_stage_id(stage_id: str) -> str:
    _validate_stage_path_segment(stage_id)
    return stage_id


def _validate_stage_path_segment(value: str) -> None:
    if not value or "/" in value or "\\" in value or value in {".", ".."}:
        raise RuntimeCertificationError(
            "RUNTIME_QUALIFICATION_PATH_INVALID",
            "stage identifier is not a safe deterministic path segment",
        )
