"""T10: request-changes lineage survives the repair revision loop.

Every test here is RED against the base SHA and GREEN after the
reviewer-lineage fix:
- the child attempt durably carries the parent's request_changes review
  artifact id + checksum (parent_review_* columns),
- child creation verifies the parent's PERSISTED review artifact decision is
  request_changes (fail closed with REPAIR_PARENT_LINEAGE_INVALID),
- a request_changes at the governed attempt budget raises the revision-limit
  code (REPAIR_LOOP_EXHAUSTED), not REPAIR_REVIEW_REJECTED,
- the child diagnosis is a clean revision diagnosis, never the parent's
  "route; checkpoint=..." suffix copied verbatim.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType
from app.orchestration.transformer_graph import TransformerOrchestrator
from app.repositories.models import (
    ArtifactMetadataModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageExecutionPlanModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.models.base import Base
from app.services.patch_apply_service import PatchApplyService
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformer_stage_service import TransformerStageService

NOW = datetime(2026, 8, 2, tzinfo=UTC)


def _database(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _scope(factory):
    @contextmanager
    def scope():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return scope


def _orchestrator(factory, *, repair_service=None):
    return TransformerOrchestrator(
        scope=_scope(factory),
        stage_service=TransformerStageService(scope=_scope(factory), now_provider=lambda: NOW),
        gate_service=SimpleNamespace(_validate_repair_lineage=lambda *args, **kwargs: None),
        transformation_evidence=MagicMock(),
        prompt_explainer=MagicMock(),
        validation_runner=MagicMock(),
        failure_evidence=MagicMock(),
        repair_service=repair_service or MagicMock(),
        patch_service=PatchApplyService(now_provider=lambda: NOW),
        sealing_flow=MagicMock(),
    )


class _RequestChangesReviewer:
    def review(self, attempt_id: str):
        return {
            "decision": "request_changes",
            "findings": [],
            "policy_checks": ["paths"],
            "risk_assessment": "low",
            "required_validation_targets": ["build"],
            "limitations": [],
        }


class _RejectingReviewer:
    def review(self, attempt_id: str):
        return {
            "decision": "reject",
            "findings": [],
            "policy_checks": ["paths"],
            "risk_assessment": "low",
            "required_validation_targets": ["build"],
            "limitations": [],
        }


def _review_payload(decision: str) -> dict[str, object]:
    return {
        "decision": decision,
        "findings": [],
        "policy_checks": ["paths"],
        "risk_assessment": "low",
        "required_validation_targets": ["build"],
        "limitations": [],
        "proposal_checksum": "sha256:proposal",
    }


def _seed_review_chain(
    factory,
    tmp_path: Path,
    *,
    attempt_number: int = 1,
    status: str = "request_changes",
    review_decision: str = "request_changes",
    review_artifact_id: str | None = "artifact-review-parent",
    review_checksum: str | None = None,
):
    """Seed a review_repair-ready parent attempt with a PERSISTED review artifact."""
    artifacts = tmp_path / "artifacts"
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "app.ts").write_text("old", encoding="utf-8")
    store = LocalFilesystemArtifactStore(artifacts.parent, fixed_run_root=artifacts)
    attempt_id = "repair-1"
    failure = store.write_text_artifact(
        "run-1",
        "05_repairs/attempt-repair-1/failure-evidence.json",
        json.dumps({"attempt_id": attempt_id}),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="repair-failure-evidence",
        created_at=NOW,
    )
    review = None
    if review_artifact_id is not None:
        review = store.write_text_artifact(
            "run-1",
            f"05_repairs/attempt-{attempt_id}/review.json",
            json.dumps(_review_payload(review_decision), sort_keys=True),
            ArtifactType.JSON,
            stage_id="stage-1",
            attempt_id=attempt_id,
            created_by="repair-review",
            created_at=NOW,
        )
    session = factory()
    run = MigrationRunModel(
        id="run-1",
        status="STAGE_CREATED",
        run_phase="FEASIBILITY_PLANNING",
        phase_status="completed",
        state_version=7,
        run_root=str(tmp_path),
        artifact_root=str(artifacts),
        workspace_aliases={"STAGE_SANDBOX": str(tmp_path)},
        created_at=NOW,
        updated_at=NOW,
    )
    plan = StageExecutionPlanModel(
        id="stage-plan-1",
        run_id="run-1",
        migration_plan_id="plan-1",
        stage_id="stage-1",
        idempotency_key="plan",
        request_checksum="sha256:plan",
        actor="operator",
        correlation_id="corr-1",
        status="approved",
        version=1,
        stage_plan={"repair_policy": {"max_attempts": 3}, "forbidden_change_policy": {}},
        checksum="sha256:stage-plan",
        artifact_ids=[],
        artifact_checksums={},
        state_version=1,
        event_sequence=1,
        created_at=NOW,
        updated_at=NOW,
    )
    binding = StageWorkspaceBindingModel(
        id="binding-1",
        run_id="run-1",
        stage_id="stage-1",
        alias="STAGE_WORKSPACE_1",
        workspace_path=str(workspace),
        workspace_fingerprint=StageSandboxCopier.fingerprint(workspace),
        active=True,
        created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-1",
        run_id="run-1",
        current_stage_id="stage-1",
        thread_id="thread-1",
        status="running",
        current_node="review_repair",
        worker_id="worker-1",
        lease_expires_at=NOW + timedelta(seconds=120),
        g06_approval_id="g06-1",
        plan_id="plan-1",
        plan_checksum="sha256:plan",
        stage_plan_id="stage-plan-1",
        stage_plan_checksum="sha256:stage-plan",
        idempotency_key="continuation",
        request_checksum="sha256:continuation",
        state_version=3,
        attempt=attempt_number,
        max_attempts=3,
        created_at=NOW,
        updated_at=NOW,
    )
    attempt = RepairAttemptModel(
        id=attempt_id,
        run_id="run-1",
        stage_id="stage-1",
        attempt_number=attempt_number,
        status=status,
        risk_level="low",
        diagnosis="repairable_source; checkpoint=ckpt-pre",
        checkpoint_id="ckpt-pre",
        failure_evidence_artifact_id=failure.ref.artifact_id,
        failure_evidence_checksum=failure.ref.checksum,
        failure_route_artifact_id="artifact-route",
        failure_route_checksum="sha256:route",
        context_pack_artifact_id="artifact-context",
        context_pack_checksum="sha256:context",
        proposal_artifact_id="artifact-proposal",
        proposal_checksum="sha256:proposal",
        proposer_invocation_id="repair-1:proposer",
        reviewer_invocation_id="repair-1:reviewer",
        review_artifact_id=review.ref.artifact_id if review is not None else None,
        review_checksum=review.ref.checksum if review is not None else (review_checksum or None),
        pre_fingerprint=StageSandboxCopier.fingerprint(workspace),
        failure_fingerprint="fingerprint-failure",
        created_at=NOW,
        updated_at=NOW,
    )
    session.add_all([run, plan, binding, continuation, attempt])
    session.add(
        ArtifactMetadataModel(
            id="metadata-" + failure.ref.artifact_id,
            run_id="run-1",
            stage_id="stage-1",
            artifact_type=failure.ref.artifact_type.value,
            relative_path=failure.ref.relative_path,
            checksum=failure.ref.checksum,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
        )
    )
    if review is not None:
        session.add(
            ArtifactMetadataModel(
                id="metadata-" + review.ref.artifact_id,
                run_id="run-1",
                stage_id="stage-1",
                artifact_type=review.ref.artifact_type.value,
                relative_path=review.ref.relative_path,
                checksum=review_checksum or review.ref.checksum,
                created_at=NOW,
                finalized_at=NOW,
                immutable=True,
            )
        )
    session.commit()
    session.close()
    return store


def test_child_attempt_carries_parent_request_changes_review_lineage(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_review_chain(factory, tmp_path)

    _orchestrator(factory, repair_service=_RequestChangesReviewer()).advance(
        "cont-1", "worker-1"
    )

    session = factory()
    attempts = session.query(RepairAttemptModel).order_by(
        RepairAttemptModel.attempt_number
    ).all()
    assert [attempt.attempt_number for attempt in attempts] == [1, 2]
    parent = attempts[0]
    child = attempts[1]
    assert child.parent_attempt_id == parent.id
    assert child.parent_review_artifact_id == parent.review_artifact_id
    assert child.parent_review_checksum == parent.review_checksum
    assert child.checkpoint_id == "ckpt-pre"
    assert child.status == "evidence_frozen"
    assert child.diagnosis != parent.diagnosis
    assert "checkpoint=ckpt-pre" not in (child.diagnosis or "")
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "queued"
    assert continuation.current_node == "propose_repair"
    session.close()
    engine.dispose()


def test_child_creation_rejects_parent_review_that_did_not_request_changes(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_review_chain(factory, tmp_path, review_decision="accept")

    _orchestrator(factory, repair_service=_RequestChangesReviewer()).advance(
        "cont-1", "worker-1"
    )

    session = factory()
    attempts = session.query(RepairAttemptModel).all()
    assert len(attempts) == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "REPAIR_PARENT_LINEAGE_INVALID"
    session.close()
    engine.dispose()


def test_child_creation_rejects_parent_without_persisted_review_artifact(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_review_chain(factory, tmp_path, review_artifact_id=None)

    _orchestrator(factory, repair_service=_RequestChangesReviewer()).advance(
        "cont-1", "worker-1"
    )

    session = factory()
    attempts = session.query(RepairAttemptModel).all()
    assert len(attempts) == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "REPAIR_PARENT_LINEAGE_INVALID"
    session.close()
    engine.dispose()


def test_child_creation_rejects_tampered_parent_review_artifact(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_review_chain(
        factory,
        tmp_path,
        review_checksum="sha256:" + "9" * 64,
    )

    _orchestrator(factory, repair_service=_RequestChangesReviewer()).advance(
        "cont-1", "worker-1"
    )

    session = factory()
    attempts = session.query(RepairAttemptModel).all()
    assert len(attempts) == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "REPAIR_PARENT_LINEAGE_INVALID"
    session.close()
    engine.dispose()


def test_request_changes_at_attempt_budget_raises_revision_limit(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_review_chain(factory, tmp_path, attempt_number=3)

    _orchestrator(factory, repair_service=_RequestChangesReviewer()).advance(
        "cont-1", "worker-1"
    )

    session = factory()
    attempts = session.query(RepairAttemptModel).all()
    assert len(attempts) == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "REPAIR_LOOP_EXHAUSTED"
    assert continuation.last_error_code != "REPAIR_REVIEW_REJECTED"
    session.close()
    engine.dispose()


def test_reject_decision_at_attempt_budget_still_raises_review_rejected(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_review_chain(factory, tmp_path, attempt_number=3, status="proposed")

    _orchestrator(factory, repair_service=_RejectingReviewer()).advance(
        "cont-1", "worker-1"
    )

    session = factory()
    attempts = session.query(RepairAttemptModel).all()
    assert len(attempts) == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "blocked"
    assert continuation.last_error_code == "REPAIR_REVIEW_REJECTED"
    session.close()
    engine.dispose()


def test_child_attempt_diagnosis_does_not_copy_parent_route_suffix(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_review_chain(factory, tmp_path)

    _orchestrator(factory, repair_service=_RequestChangesReviewer()).advance(
        "cont-1", "worker-1"
    )

    session = factory()
    child = session.query(RepairAttemptModel).order_by(
        RepairAttemptModel.attempt_number.desc()
    ).first()
    assert child.diagnosis == "request_changes revision; parent=repair-1"
    session.close()
    engine.dispose()


def test_child_attempt_lineage_flows_into_parent_review_binding_check(tmp_path: Path):
    """The child's review binding itself must never reference a parent artifact."""
    engine, factory = _database(tmp_path)
    _seed_review_chain(factory, tmp_path)

    _orchestrator(factory, repair_service=_RequestChangesReviewer()).advance(
        "cont-1", "worker-1"
    )

    session = factory()
    child = session.query(RepairAttemptModel).order_by(
        RepairAttemptModel.attempt_number.desc()
    ).first()
    assert child.review_artifact_id is None
    assert child.review_checksum is None
    assert child.parent_review_artifact_id is not None
    session.close()
    engine.dispose()
