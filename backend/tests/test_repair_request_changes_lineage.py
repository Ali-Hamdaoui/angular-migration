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
    MigrationPlanModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageExecutionPlanModel,
    StageGatePackageModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.models.base import Base
from app.services.patch_apply_service import PatchApplyService
from app.services.causal_review import repair_budget
from app.services.failure_evidence_service import FailureEvidenceService
from app.services.repair_application_service import RepairApplicationError, RepairApplicationService
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


def _seed_budget_request_case(
    factory,
    tmp_path: Path,
    *,
    target_attempt_number: int,
    completed_attempt_numbers: tuple[int, ...] = (),
    completed_status: str = "applied",
    recovery_attempt_number: int | None = None,
):
    artifacts = tmp_path / "budget-artifacts"
    workspace = tmp_path / "budget-workspace"
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "app.ts").write_text("old", encoding="utf-8")
    store = LocalFilesystemArtifactStore(artifacts.parent, fixed_run_root=artifacts)
    stage_id = "stage-1"
    run_id = "run-1"
    target_id = f"repair-{stage_id}-{target_attempt_number}"
    live_fingerprint = StageSandboxCopier.fingerprint(workspace)

    def _metadata(stored):
        return ArtifactMetadataModel(
            id="metadata-" + stored.ref.artifact_id,
            run_id=run_id,
            stage_id=stage_id,
            artifact_type=stored.ref.artifact_type.value,
            relative_path=stored.ref.relative_path,
            checksum=stored.ref.checksum,
            schema_version=stored.envelope.schema_version if stored.envelope else 1,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
            size_bytes=len(stored.content.encode("utf-8")),
        )

    def _proposal_payload(failure_checksum: str, context_checksum: str):
        return {
            "failure_evidence_checksum": failure_checksum,
            "context_pack_checksum": context_checksum,
            "proposal_format": "operations",
            "operations": [
                {
                    "operation": "replace_text",
                    "path": "src/app.ts",
                    "preimage_sha256": "sha256:" + "0" * 64,
                    "old_text": "old",
                    "new_text": "new",
                }
            ],
            "unified_diff": None,
            "touched_files": ["src/app.ts"],
            "rationale": ["Fix the compiler error."],
            "risk_level": "low",
            "validation_targets": ["build"],
            "limitations": [],
        }

    def _review_payload_for(proposal_checksum: str):
        return {
            "decision": "request_changes",
            "findings": [],
            "policy_checks": ["paths"],
            "risk_assessment": "low",
            "required_validation_targets": ["build"],
            "limitations": [],
            "proposal_checksum": proposal_checksum,
        }

    failure = store.write_text_artifact(
        run_id,
        f"05_repairs/attempt-{target_id}/failure-evidence.json",
        json.dumps({"attempt_id": target_id}),
        ArtifactType.JSON,
        stage_id=stage_id,
        attempt_id=target_id,
        created_by="repair-failure-evidence",
        created_at=NOW,
    )
    evidence = {
        "schema_version": "transformer-failure-evidence-v1",
        "run_id": run_id,
        "stage_id": stage_id,
        "stage_plan_checksum": "sha256:stage-plan",
        "workspace_path": str(workspace),
        "workspace_fingerprint": live_fingerprint,
        "artifact_root": str(artifacts),
        "execution_id": "execution-1",
        "command_log_artifact_id": None,
        "result_artifact_id": None,
        "normalized_failure": {
            "error_code": "COMPILATION_FAILED",
            "exit_code": 1,
            "failure_message": "Angular compiler reported an error",
        },
        "failure_fingerprint": "fingerprint-failure",
        "prior_fingerprints": [],
        "repair_policy": {"max_attempts": 3, "max_applied": 2},
        "forbidden_change_policy": {},
    }
    context = FailureEvidenceService(now_provider=lambda: NOW).write_context_pack(
        evidence, failure.ref.checksum
    )
    target_proposal = store.write_text_artifact(
        run_id,
        f"05_repairs/attempt-{target_id}/proposal.json",
        json.dumps(_proposal_payload(failure.ref.checksum, context.ref.checksum), sort_keys=True),
        ArtifactType.JSON,
        stage_id=stage_id,
        attempt_id=target_id,
        created_by="repair-proposal",
        created_at=NOW,
    )
    target_review = store.write_text_artifact(
        run_id,
        f"05_repairs/attempt-{target_id}/review.json",
        json.dumps(_review_payload_for(target_proposal.ref.checksum), sort_keys=True),
        ArtifactType.JSON,
        stage_id=stage_id,
        attempt_id=target_id,
        created_by="repair-review",
        created_at=NOW,
    )

    completed_rows = []
    completed_packages = []
    for number in completed_attempt_numbers:
        attempt_id = f"repair-{stage_id}-{number}"
        proposal = store.write_text_artifact(
            run_id,
            f"05_repairs/attempt-{attempt_id}/proposal.json",
            json.dumps(_proposal_payload("sha256:failure", "sha256:context"), sort_keys=True),
            ArtifactType.JSON,
            stage_id=stage_id,
            attempt_id=attempt_id,
            created_by="repair-proposal",
            created_at=NOW,
        )
        review = store.write_text_artifact(
            run_id,
            f"05_repairs/attempt-{attempt_id}/review.json",
            json.dumps(_review_payload_for(proposal.ref.checksum), sort_keys=True),
            ArtifactType.JSON,
            stage_id=stage_id,
            attempt_id=attempt_id,
            created_by="repair-review",
            created_at=NOW,
        )
        package_id = f"gate-package-{number}"
        package = StageGatePackageModel(
            id=package_id,
            run_id=run_id,
            stage_id=stage_id,
            gate_id="G10",
            gate_version=number,
            status="approved",
            package_artifact_id=f"artifact-package-{number}",
            package_checksum="sha256:" + str(number) * 64,
            artifact_set_checksum="sha256:" + str(number) * 64,
            plan_id="plan-1",
            plan_version=1,
            stage_plan_id="stage-plan-1",
            stage_plan_checksum="sha256:stage-plan",
            workspace_fingerprint=live_fingerprint,
            expected_state_version=number,
            created_at=NOW,
        )
        completed_packages.append(package)
        completed_rows.append(
            RepairAttemptModel(
                id=attempt_id,
                run_id=run_id,
                stage_id=stage_id,
                attempt_number=number,
                status=completed_status,
                risk_level="low",
                diagnosis="completed repair",
                proposal_artifact_id=proposal.ref.artifact_id,
                proposal_checksum=proposal.ref.checksum,
                review_artifact_id=review.ref.artifact_id,
                review_checksum=review.ref.checksum,
                g10_gate_package_id=package_id,
                apply_ledger_artifact_id=f"artifact-apply-{number}",
                apply_ledger_checksum="sha256:" + str(number) * 64,
                pre_fingerprint=live_fingerprint,
                post_fingerprint=live_fingerprint,
                created_at=NOW,
                updated_at=NOW,
            )
        )

    target_package_id = f"gate-package-{target_attempt_number}"
    target_package = StageGatePackageModel(
        id=target_package_id,
        run_id=run_id,
        stage_id=stage_id,
        gate_id="G10",
        gate_version=target_attempt_number,
        status="pending",
        package_artifact_id=f"artifact-package-{target_attempt_number}",
        package_checksum="sha256:" + str(target_attempt_number) * 64,
        artifact_set_checksum="sha256:" + str(target_attempt_number) * 64,
        plan_id="plan-1",
        plan_version=1,
        stage_plan_id="stage-plan-1",
        stage_plan_checksum="sha256:stage-plan",
        workspace_fingerprint=live_fingerprint,
        expected_state_version=target_attempt_number,
        created_at=NOW,
    )
    target_attempt = RepairAttemptModel(
        id=target_id,
        run_id=run_id,
        stage_id=stage_id,
        attempt_number=target_attempt_number,
        status="waiting_g10",
        risk_level="low",
        diagnosis="current repair",
        failure_evidence_artifact_id=failure.ref.artifact_id,
        failure_evidence_checksum=failure.ref.checksum,
        context_pack_artifact_id=context.ref.artifact_id,
        context_pack_checksum=context.ref.checksum,
        proposal_artifact_id=target_proposal.ref.artifact_id,
        proposal_checksum=target_proposal.ref.checksum,
        review_artifact_id=target_review.ref.artifact_id,
        review_checksum=target_review.ref.checksum,
        g10_gate_package_id=target_package_id,
        pre_fingerprint=live_fingerprint,
        failure_fingerprint="fingerprint-failure",
        created_at=NOW,
        updated_at=NOW,
    )

    recovery = None
    if recovery_attempt_number is not None:
        recovery = RepairAttemptModel(
            id=f"repair-{stage_id}-{recovery_attempt_number}",
            run_id=run_id,
            stage_id=stage_id,
            attempt_number=recovery_attempt_number,
            status="superseded",
            risk_level="unknown",
            diagnosis="recovery evidence only",
            created_at=NOW,
            updated_at=NOW,
        )

    session = factory()
    run = MigrationRunModel(
        id=run_id,
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
    plan = MigrationPlanModel(
        id="plan-1",
        run_id=run_id,
        idempotency_key="plan",
        request_checksum="sha256:plan",
        actor="operator",
        status="approved",
        version=1,
        plan={},
        checksum="sha256:plan",
        artifact_ids=[],
        artifact_checksums={},
        state_version=1,
        event_sequence=1,
        created_at=NOW,
        updated_at=NOW,
    )
    stage_plan = StageExecutionPlanModel(
        id="stage-plan-1",
        run_id=run_id,
        migration_plan_id="plan-1",
        stage_id=stage_id,
        idempotency_key="stage-plan",
        request_checksum="sha256:stage-plan-request",
        actor="operator",
        correlation_id="correlation-1",
        status="approved",
        version=1,
        stage_plan={"repair_policy": {"max_attempts": 3, "max_applied": 2}},
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
        run_id=run_id,
        stage_id=stage_id,
        alias="STAGE_WORKSPACE_1",
        workspace_path=str(workspace),
        workspace_fingerprint=live_fingerprint,
        active=True,
        created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-1",
        run_id=run_id,
        current_stage_id=stage_id,
        thread_id="thread-1",
        status="waiting_gate",
        current_node="wait_g10",
        g06_approval_id="g06-1",
        plan_id="plan-1",
        plan_checksum="sha256:plan",
        stage_plan_id="stage-plan-1",
        stage_plan_checksum="sha256:stage-plan",
        max_attempts=3,
        idempotency_key="continuation",
        request_checksum="sha256:continuation",
        state_version=3,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add_all(
        [
            run,
            plan,
            stage_plan,
            binding,
            continuation,
            *completed_packages,
            target_package,
            *completed_rows,
            target_attempt,
            *([recovery] if recovery is not None else []),
        ]
    )
    for stored in [failure, context, target_proposal, target_review]:
        session.add(_metadata(stored))
    for number in completed_attempt_numbers:
        for relative in (
            f"05_repairs/attempt-repair-{stage_id}-{number}/proposal.json",
            f"05_repairs/attempt-repair-{stage_id}-{number}/review.json",
        ):
            stored = store.read_artifact(run_id, relative)
            session.add(_metadata(stored))
    session.commit()
    session.close()
    return store, target_id, target_proposal.ref.artifact_id, target_proposal.ref.checksum


def _request_revision(service, target_id, proposal_id, proposal_checksum, *, key):
    return service.request_revision(
        attempt_id=target_id,
        proposal_id=proposal_id,
        base_checksum=proposal_checksum,
        instruction="Please revise the candidate.",
        idempotency_key=key,
        actor="operator",
    )


def test_request_changes_ignores_superseded_unapplied_recovery_attempts(tmp_path: Path):
    engine, factory = _database(tmp_path)
    store, target_id, proposal_id, proposal_checksum = _seed_budget_request_case(
        factory,
        tmp_path,
        target_attempt_number=5,
        recovery_attempt_number=4,
    )
    proposal_path = f"05_repairs/attempt-{target_id}/proposal.json"
    original_proposal = store.read_artifact("run-1", proposal_path).content
    service = RepairApplicationService(scope=_scope(factory), now_provider=lambda: NOW)

    result = _request_revision(
        service, target_id, proposal_id, proposal_checksum, key="revision-recovery"
    )

    assert result == {
        "attempt_id": "repair-stage-1-6",
        "status": "evidence_frozen",
        "idempotent_replay": False,
    }
    session = factory()
    attempts = session.query(RepairAttemptModel).order_by(RepairAttemptModel.attempt_number).all()
    assert [attempt.attempt_number for attempt in attempts] == [4, 5, 6]
    recovery = session.get(RepairAttemptModel, "repair-stage-1-4")
    parent = session.get(RepairAttemptModel, target_id)
    child = session.get(RepairAttemptModel, "repair-stage-1-6")
    assert recovery is not None
    assert recovery.status == "superseded"
    assert recovery.proposal_artifact_id is None
    assert recovery.review_artifact_id is None
    assert recovery.apply_ledger_artifact_id is None
    assert parent is not None and parent.status == "superseded"
    assert parent.proposal_artifact_id == proposal_id
    assert parent.proposal_checksum == proposal_checksum
    assert store.read_artifact("run-1", proposal_path).content == original_proposal
    assert child is not None and child.parent_attempt_id == target_id
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "queued"
    assert continuation.current_node == "propose_repair"
    session.close()
    engine.dispose()


def test_request_changes_still_exhausts_at_causal_repair_budget(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _, target_id, proposal_id, proposal_checksum = _seed_budget_request_case(
        factory,
        tmp_path,
        target_attempt_number=4,
        completed_attempt_numbers=(1, 2, 3),
    )
    session = factory()
    budget = repair_budget(session, "run-1", "stage-1", {"max_attempts": 3, "max_applied": 2})
    assert budget["consumed_attempts"] == 3
    assert budget["consumed_applied"] == 3
    session.close()
    service = RepairApplicationService(scope=_scope(factory), now_provider=lambda: NOW)

    with pytest.raises(RepairApplicationError) as error:
        _request_revision(
            service, target_id, proposal_id, proposal_checksum, key="revision-exhausted"
        )

    assert error.value.code == "REPAIR_LOOP_EXHAUSTED"
    session = factory()
    assert session.query(RepairAttemptModel).count() == 4
    session.close()
    engine.dispose()


def test_repair_budget_counts_causally_completed_migration_retried_attempt(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_budget_request_case(
        factory,
        tmp_path,
        target_attempt_number=2,
        completed_attempt_numbers=(1,),
        completed_status="migration_retried",
    )
    session = factory()

    budget = repair_budget(
        session,
        "run-1",
        "stage-1",
        {"max_attempts": 3, "max_applied": 2},
    )

    assert budget["consumed_attempts"] == 1
    assert budget["consumed_applied"] == 1
    session.close()
    engine.dispose()


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
    _, target_id, proposal_id, proposal_checksum = _seed_budget_request_case(
        factory,
        tmp_path,
        target_attempt_number=4,
        completed_attempt_numbers=(1, 2, 3),
    )

    with pytest.raises(RepairApplicationError) as error:
        _request_revision(
            RepairApplicationService(scope=_scope(factory), now_provider=lambda: NOW),
            target_id,
            proposal_id,
            proposal_checksum,
            key="revision-at-budget",
        )

    assert error.value.code == "REPAIR_LOOP_EXHAUSTED"
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
