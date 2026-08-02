import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType
from app.domain.transformation import FailureRoute, StageGateDecisionRequest
from app.orchestration.transformer_graph import TransformerOrchestrator
from app.repositories.models import (
    ArtifactMetadataModel,
    LlmInvocationModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageExecutionPlanModel,
    StageGateDecisionModel,
    StageGatePackageModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.models.base import Base
from app.services.artifact_binding import canonical_artifact_set_checksum
from app.services.failure_evidence_service import FailureEvidenceService
from app.services.stage_gate_service import StageGateError, StageGateService
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformation_continuation_service import TransformationContinuationService
from app.services.transformer_stage_service import TransformerStageError, TransformerStageService
from tests.test_transformation_continuation import NOW, _create, _session

NOW_UTC = datetime(2026, 7, 31, tzinfo=UTC)
FINGERPRINT = "sha256:" + "f" * 64


def _g10_database(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'g10.db'}")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _g10_scope(factory):
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


def _seed_g10(
    factory,
    tmp_path: Path,
    *,
    run_id: str = "run-1",
    stage_id: str = "stage-1",
    attempt_id: str = "repair-1",
):
    """Seed a production-shaped G10-ready stage.

    Failure evidence and context pack go through the REAL FailureEvidenceService
    writers, so their envelope sidecars legitimately carry attempt_id=NULL (they
    are written before the RepairAttempt row exists). Proposal and review are
    attempt-bound. Workspace, invocations, and metadata are fully valid so a
    real G10 create/decide/apply cycle can complete.
    """
    artifacts = tmp_path / "artifacts"
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    app_ts = workspace / "src" / "app.ts"
    app_ts.write_text("old", encoding="utf-8")
    (workspace / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    workspace_fingerprint = StageSandboxCopier.fingerprint(workspace)
    evidence = {
        "schema_version": "transformer-failure-evidence-v1",
        "run_id": run_id,
        "stage_id": stage_id,
        "stage_plan_checksum": "sha256:stage-plan",
        "workspace_path": str(workspace),
        "workspace_fingerprint": workspace_fingerprint,
        "artifact_root": str(artifacts),
        "execution_id": "execution-1",
        "command_log_artifact_id": None,
        "result_artifact_id": None,
        "normalized_failure": {
            "error_code": "COMPILATION_FAILED",
            "exit_code": 1,
            "failure_message": "Angular compiler reported an error",
        },
        "failure_fingerprint": FINGERPRINT,
        "prior_fingerprints": [],
        "repair_policy": {},
        "forbidden_change_policy": {},
    }
    evidence_service = FailureEvidenceService()
    failure, route_artifact = evidence_service.write(evidence, FailureRoute.REPAIRABLE_SOURCE)
    context = evidence_service.write_context_pack(evidence, failure.ref.checksum)
    store = LocalFilesystemArtifactStore(artifacts.parent, fixed_run_root=artifacts)
    proposal_payload = {
        "failure_evidence_checksum": failure.ref.checksum,
        "context_pack_checksum": context.ref.checksum,
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "replace_text",
                "path": "src/app.ts",
                "preimage_sha256": "sha256:" + hashlib.sha256(app_ts.read_bytes()).hexdigest(),
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
    proposal = store.write_text_artifact(
        run_id,
        f"05_repairs/attempt-{attempt_id}/proposal.json",
        json.dumps(proposal_payload, sort_keys=True),
        ArtifactType.JSON,
        stage_id=stage_id,
        attempt_id=attempt_id,
        created_by="repair-proposal",
        created_at=NOW_UTC,
    )
    review_payload = {
        "decision": "accept",
        "findings": [],
        "policy_checks": ["paths"],
        "risk_assessment": "low risk, minimal change",
        "required_validation_targets": ["build"],
        "limitations": [],
        "proposal_checksum": proposal.ref.checksum,
    }
    review = store.write_text_artifact(
        run_id,
        f"05_repairs/attempt-{attempt_id}/review.json",
        json.dumps(review_payload, sort_keys=True),
        ArtifactType.JSON,
        stage_id=stage_id,
        attempt_id=attempt_id,
        created_by="repair-review",
        created_at=NOW_UTC,
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
        created_at=NOW_UTC,
        updated_at=NOW_UTC,
    )
    stage_plan = StageExecutionPlanModel(
        id=f"stage-plan-{stage_id}",
        run_id=run_id,
        migration_plan_id="plan-1",
        stage_id=stage_id,
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
        created_at=NOW_UTC,
        updated_at=NOW_UTC,
    )
    binding = StageWorkspaceBindingModel(
        id="binding-1",
        run_id=run_id,
        stage_id=stage_id,
        alias="STAGE_WORKSPACE_1",
        workspace_path=str(workspace),
        workspace_fingerprint=workspace_fingerprint,
        active=True,
        created_at=NOW_UTC,
    )
    continuation = TransformationContinuationModel(
        id="cont-1",
        run_id=run_id,
        current_stage_id=stage_id,
        thread_id="thread-1",
        status="running",
        current_node="create_g10",
        g06_approval_id="g06-1",
        plan_id="plan-1",
        plan_checksum="sha256:plan",
        stage_plan_id=stage_plan.id,
        stage_plan_checksum=stage_plan.checksum,
        worker_id="worker-1",
        attempt=1,
        max_attempts=3,
        lease_expires_at=NOW_UTC + timedelta(seconds=120),
        idempotency_key="continuation",
        request_checksum="sha256:continuation",
        state_version=3,
        created_at=NOW_UTC,
        updated_at=NOW_UTC,
    )
    attempt = RepairAttemptModel(
        id=attempt_id,
        run_id=run_id,
        stage_id=stage_id,
        attempt_number=1,
        status="review_accepted",
        risk_level="low",
        diagnosis="repairable_source; checkpoint=ckpt-pre",
        failure_evidence_artifact_id=failure.ref.artifact_id,
        failure_evidence_checksum=failure.ref.checksum,
        failure_route_artifact_id=route_artifact.ref.artifact_id,
        failure_route_checksum=route_artifact.ref.checksum,
        context_pack_artifact_id=context.ref.artifact_id,
        context_pack_checksum=context.ref.checksum,
        proposal_artifact_id=proposal.ref.artifact_id,
        proposal_checksum=proposal.ref.checksum,
        proposer_invocation_id=f"{attempt_id}:proposer",
        review_artifact_id=review.ref.artifact_id,
        review_checksum=review.ref.checksum,
        reviewer_invocation_id=f"{attempt_id}:reviewer",
        failure_fingerprint=FINGERPRINT,
        created_at=NOW_UTC,
        updated_at=NOW_UTC,
    )
    session.add_all([run, stage_plan, binding, continuation, attempt])
    for stored in (failure, route_artifact, context, proposal, review):
        session.add(
            ArtifactMetadataModel(
                id="metadata-" + stored.ref.artifact_id,
                run_id=run_id,
                stage_id=stage_id,
                artifact_type=stored.ref.artifact_type.value,
                relative_path=stored.ref.relative_path,
                checksum=stored.ref.checksum,
                created_at=NOW_UTC,
                finalized_at=NOW_UTC,
                immutable=True,
            )
        )
    session.add(
        LlmInvocationModel(
            id=f"{attempt_id}:proposer",
            run_id=run_id,
            stage_id=stage_id,
            idempotency_key=f"{attempt_id}:proposer",
            request_checksum="sha256:proposer-request",
            input_hashes=[failure.ref.checksum, context.ref.checksum],
            correlation_id=f"{attempt_id}:proposer",
            actor="transformer",
            role="repair_proposer",
            task_type="repair_diagnosis",
            provider="azure_openai",
            deployment_alias="azure-openai",
            prompt_version="prompt-repair-proposer-v2",
            schema_version="schema-registry-v2",
            pricing_version="mvp-pricing-2026-01",
            stage="repair",
            redacted_summary=json.dumps({"risk_level": "low"}, sort_keys=True),
            status="completed",
            artifact_ids=[proposal.ref.artifact_id],
            artifact_checksums={proposal.ref.artifact_id: proposal.ref.checksum},
            state_version=1,
            event_sequence=0,
            retries=0,
            transport_started=True,
            started_at=NOW_UTC,
            completed_at=NOW_UTC,
            created_at=NOW_UTC,
        )
    )
    session.add(
        LlmInvocationModel(
            id=f"{attempt_id}:reviewer",
            run_id=run_id,
            stage_id=stage_id,
            idempotency_key=f"{attempt_id}:reviewer",
            request_checksum="sha256:reviewer-request",
            input_hashes=[proposal.ref.checksum],
            correlation_id=f"{attempt_id}:reviewer",
            actor="transformer",
            role="repair_reviewer",
            task_type="repair_review",
            provider="azure_openai",
            deployment_alias="azure-openai",
            prompt_version="prompt-repair-reviewer-v2",
            schema_version="schema-registry-v2",
            pricing_version="mvp-pricing-2026-01",
            stage="repair",
            redacted_summary=json.dumps({"decision": "accept"}, sort_keys=True),
            status="completed",
            artifact_ids=[review.ref.artifact_id],
            artifact_checksums={review.ref.artifact_id: review.ref.checksum},
            state_version=1,
            event_sequence=0,
            retries=0,
            transport_started=True,
            started_at=NOW_UTC,
            completed_at=NOW_UTC,
            created_at=NOW_UTC,
        )
    )
    session.commit()
    session.close()
    return (
        store,
        workspace,
        artifacts,
        attempt_id,
        failure,
        context,
        proposal,
        review,
        workspace_fingerprint,
    )


def _g10_orchestrator(factory):
    scope = _g10_scope(factory)
    return TransformerOrchestrator(
        scope=scope,
        stage_service=TransformerStageService(scope=scope),
        gate_service=StageGateService(),
        transformation_evidence=MagicMock(),
        prompt_explainer=MagicMock(),
        validation_runner=MagicMock(),
        failure_evidence=MagicMock(),
        repair_service=MagicMock(),
        patch_service=None,
        sealing_flow=MagicMock(),
    )


def _requeue_cont(factory, *, worker: str = "worker-2") -> None:
    session = factory()
    continuations = TransformationContinuationService()
    continuations.wake(session, "cont-1", now=NOW_UTC)
    session.commit()
    session.close()
    session = factory()
    claimed = continuations.claim_next(session, worker, now=NOW_UTC + timedelta(seconds=300))
    assert claimed is not None
    session.commit()
    session.close()


def _g10_package(session, *, status: str | None = None):
    query = select(StageGatePackageModel).where(StageGatePackageModel.gate_id == "G10")
    if status is not None:
        query = query.where(StageGatePackageModel.status == status)
    return session.scalar(query)


def _g10_decision_request(continuation, package) -> StageGateDecisionRequest:
    return StageGateDecisionRequest(
        expected_state_version=continuation.state_version,
        idempotency_key="g10-approve",
        package_checksum=package.package_checksum,
        workspace_fingerprint=package.workspace_fingerprint,
        decision="approve",
        correlation_id="corr-1",
    )


def _read_envelope(artifacts: Path, relative_path: str) -> dict[str, object]:
    return json.loads((artifacts / f"{relative_path}.meta.json").read_text(encoding="utf-8"))


def _rewrite_sidecar(artifacts: Path, relative_path: str, **updates) -> None:
    sidecar = artifacts / f"{relative_path}.meta.json"
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload.update(updates)
    sidecar.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_g10_create_decide_apply_accepts_production_shaped_pre_attempt_evidence(tmp_path: Path):
    """A production-shaped evidence envelope (attempt_id=NULL) passes G10 end to end.

    Failure evidence and context pack are written by FailureEvidenceService
    BEFORE the attempt exists, so their envelopes carry attempt_id=NULL exactly
    like production. RED until the fix: ``_validate_repair_lineage`` rejects
    them with G10_LINEAGE_STALE because it demands the exact attempt id on all
    four inner artifacts.
    """
    engine, factory = _g10_database(tmp_path)
    _store, _workspace, artifacts, attempt_id, failure, _context, _proposal, _review, _fp = (
        _seed_g10(factory, tmp_path)
    )
    for stored in (failure,):
        envelope = _read_envelope(artifacts, stored.ref.relative_path)
        assert envelope["attempt_id"] is None

    orchestrator = _g10_orchestrator(factory)
    orchestrator.advance("cont-1", "worker-1")

    session = factory()
    package = _g10_package(session)
    assert package is not None and package.status == "pending"
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "waiting_gate"
    assert continuation.current_node == "wait_g10"
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "waiting_g10"
    assert attempt.g10_gate_package_id == package.id
    session.close()

    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    package = _g10_package(session)
    decision = StageGateService().decide(
        session,
        continuation,
        "G10",
        _g10_decision_request(continuation, package),
        actor="operator",
        now=NOW_UTC,
    )
    assert decision.accepted is True
    assert package.status == "approved"
    assert continuation.status == "queued"
    assert continuation.current_node == "apply_repair"
    session.commit()
    session.close()

    _requeue_cont(factory, worker="worker-2")
    orchestrator.advance("cont-1", "worker-2")

    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "applied"
    assert attempt.apply_ledger_artifact_id is not None
    assert attempt.apply_ledger_checksum is not None
    assert attempt.post_fingerprint is not None
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "queued"
    assert continuation.current_node == "repair_revalidate"
    session.close()
    engine.dispose()


def test_g10_rejects_wrong_run_stage_checksum_evidence_envelope(tmp_path: Path):
    """Pre-attempt evidence tampering stays fail-closed under the role contract.

    attempt_id=NULL is accepted for pre-attempt roles ONLY; a wrong run_id,
    stage_id, or checksum on the same envelope still blocks G10 create with
    G10_LINEAGE_STALE, exactly like production.
    """
    engine, factory = _g10_database(tmp_path)
    _store, _workspace, artifacts, _attempt_id, failure, _context, _proposal, _review, _fp = (
        _seed_g10(factory, tmp_path)
    )
    original_bytes = (artifacts / failure.ref.relative_path).read_bytes()
    orchestrator = _g10_orchestrator(factory)

    cases = [
        ("run_id", {"run_id": "run-other"}),
        ("stage_id", {"stage_id": "stage-other"}),
    ]
    for label, update in cases:
        _rewrite_sidecar(artifacts, failure.ref.relative_path, **update)
        envelope = _read_envelope(artifacts, failure.ref.relative_path)
        assert envelope[label] == update[label]
        with pytest.raises(StageGateError) as raised:
            orchestrator.advance("cont-1", "worker-1")
        assert raised.value.code == "G10_LINEAGE_STALE"
        _rewrite_sidecar(
            artifacts,
            failure.ref.relative_path,
            run_id="run-1",
            stage_id="stage-1",
        )

    (artifacts / failure.ref.relative_path).write_bytes(original_bytes + b"\n")
    with pytest.raises(StageGateError) as raised:
        orchestrator.advance("cont-1", "worker-1")
    assert raised.value.code == "G10_LINEAGE_STALE"
    (artifacts / failure.ref.relative_path).write_bytes(original_bytes)
    engine.dispose()


def test_g10_rejects_shared_role_artifact_id(tmp_path: Path):
    """One artifact id cannot satisfy two roles.

    When the same id is referenced by the proposal and review columns, G10
    create must reject the envelope instead of letting the review role ride on
    the proposal content checks. RED until the fix: the ordered elif chain lets
    the shared id satisfy both roles and create succeeds.
    """
    engine, factory = _g10_database(tmp_path)
    _store, _workspace, _artifacts, attempt_id, _failure, _context, proposal, _review, _fp = (
        _seed_g10(factory, tmp_path)
    )
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    attempt.review_artifact_id = attempt.proposal_artifact_id
    attempt.review_checksum = attempt.proposal_checksum
    reviewer = session.get(LlmInvocationModel, f"{attempt_id}:reviewer")
    reviewer.artifact_ids = [proposal.ref.artifact_id]
    reviewer.artifact_checksums = {proposal.ref.artifact_id: proposal.ref.checksum}
    session.commit()
    session.close()

    with pytest.raises(StageGateError) as raised:
        _g10_orchestrator(factory).advance("cont-1", "worker-1")
    assert raised.value.code == "G10_LINEAGE_STALE"
    engine.dispose()


def test_g10_create_artifact_set_checksum_covers_inner_artifacts(tmp_path: Path):
    """G10 artifact_set_checksum covers evidence, context, proposal, review, envelope."""
    engine, factory = _g10_database(tmp_path)
    _store, _workspace, _artifacts, attempt_id, _failure, _context, _proposal, _review, _fp = (
        _seed_g10(factory, tmp_path)
    )
    _g10_orchestrator(factory).advance("cont-1", "worker-1")

    session = factory()
    package = _g10_package(session)
    attempt = session.get(RepairAttemptModel, attempt_id)
    expected = canonical_artifact_set_checksum(
        [
            {"artifact_id": attempt.failure_evidence_artifact_id, "checksum": attempt.failure_evidence_checksum},
            {"artifact_id": attempt.context_pack_artifact_id, "checksum": attempt.context_pack_checksum},
            {"artifact_id": attempt.proposal_artifact_id, "checksum": attempt.proposal_checksum},
            {"artifact_id": attempt.review_artifact_id, "checksum": attempt.review_checksum},
            {"artifact_id": package.package_artifact_id, "checksum": package.package_checksum},
        ]
    )
    assert package.artifact_set_checksum == expected
    session.close()
    engine.dispose()


def test_g10_decide_rejects_tampered_artifact_set_checksum(tmp_path: Path):
    """G10 decide validates the artifact_set_checksum recorded on the package."""
    engine, factory = _g10_database(tmp_path)
    _store, _workspace, _artifacts, _attempt_id, _failure, _context, _proposal, _review, _fp = (
        _seed_g10(factory, tmp_path)
    )
    _g10_orchestrator(factory).advance("cont-1", "worker-1")

    session = factory()
    package = _g10_package(session)
    package.artifact_set_checksum = "sha256:" + "0" * 64
    session.commit()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    with pytest.raises(StageGateError) as raised:
        StageGateService().decide(
            session,
            continuation,
            "G10",
            _g10_decision_request(continuation, package),
            actor="operator",
            now=NOW_UTC,
        )
    assert raised.value.code == "G10_LINEAGE_STALE"
    session.close()
    engine.dispose()


def test_g10_apply_binds_to_recorded_approved_package(tmp_path: Path):
    """Apply uses the attempt-recorded G10 package, not the newest approved one.

    Two approved G10 packages exist; the newer one carries a tampered payload
    that fails lineage. Only the recorded package may be applied. RED until the
    fix: ``_apply_repair_locked`` selects the newest approved package, lineage
    fails, and apply never runs.
    """
    engine, factory = _g10_database(tmp_path)
    store, workspace, artifacts, attempt_id, _failure, _context, _proposal, _review, _fp = (
        _seed_g10(factory, tmp_path)
    )
    orchestrator = _g10_orchestrator(factory)
    orchestrator.advance("cont-1", "worker-1")

    session = factory()
    recorded = _g10_package(session)
    continuation = session.get(TransformationContinuationModel, "cont-1")
    StageGateService().decide(
        session,
        continuation,
        "G10",
        _g10_decision_request(continuation, recorded),
        actor="operator",
        now=NOW_UTC,
    )
    session.commit()
    session.close()

    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    run = session.get(MigrationRunModel, "run-1")
    tampered = json.loads(
        store.read_artifact("run-1", _package_relative_path(session, recorded)).content
    )
    tampered["validation_targets"] = ["other"]
    p2 = store.write_text_artifact(
        "run-1",
        "04_workflow_state/stages/stage-1/gates/g10-package.json",
        json.dumps(tampered, sort_keys=True),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="transformer",
        created_at=NOW_UTC,
    )
    session.add(
        ArtifactMetadataModel(
            id="metadata-" + p2.ref.artifact_id,
            run_id="run-1",
            stage_id="stage-1",
            artifact_type=p2.ref.artifact_type.value,
            relative_path=p2.ref.relative_path,
            checksum=p2.ref.checksum,
            created_at=NOW_UTC,
            finalized_at=NOW_UTC,
            immutable=True,
        )
    )
    session.add(
        StageGatePackageModel(
            id="gate-package-p2",
            run_id="run-1",
            stage_id="stage-1",
            gate_id="G10",
            gate_version=2,
            status="approved",
            package_artifact_id=p2.ref.artifact_id,
            package_checksum=p2.ref.checksum,
            artifact_set_checksum="sha256:" + "1" * 64,
            plan_id="plan-1",
            plan_version=1,
            stage_plan_id="stage-plan-1",
            stage_plan_checksum="sha256:stage-plan",
            workspace_fingerprint=binding.workspace_fingerprint,
            expected_state_version=continuation.state_version + 1,
            created_at=NOW_UTC,
        )
    )
    session.add(
        StageGateDecisionModel(
            id="gate-decision-p2",
            gate_package_id="gate-package-p2",
            run_id="run-1",
            stage_id="stage-1",
            gate_id="G10",
            decision="approve",
            actor="operator",
            comment=None,
            idempotency_key="g10-approve-p2",
            request_checksum="sha256:request-p2",
            expected_state_version=continuation.state_version + 1,
            package_checksum=p2.ref.checksum,
            workspace_fingerprint=binding.workspace_fingerprint,
            accepted=True,
            reason_code=None,
            created_at=NOW_UTC,
        )
    )
    session.commit()
    session.close()

    _requeue_cont(factory, worker="worker-2")
    orchestrator.advance("cont-1", "worker-2")

    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.status == "applied"
    assert attempt.g10_gate_package_id == recorded.id
    assert attempt.apply_ledger_artifact_id is not None
    session.close()
    engine.dispose()


def _package_relative_path(session, package) -> str:
    metadata = session.get(ArtifactMetadataModel, "metadata-" + package.package_artifact_id)
    return metadata.relative_path


@pytest.mark.parametrize("recorded_id", [None, "gate-package-other"])
def test_g10_apply_rejects_unrecorded_approved_package(tmp_path: Path, recorded_id):
    """Apply fails closed when the approved package is not the recorded one."""
    engine, factory = _g10_database(tmp_path)
    _store, _workspace, _artifacts, attempt_id, _failure, _context, _proposal, _review, _fp = (
        _seed_g10(factory, tmp_path)
    )
    orchestrator = _g10_orchestrator(factory)
    orchestrator.advance("cont-1", "worker-1")

    session = factory()
    package = _g10_package(session)
    continuation = session.get(TransformationContinuationModel, "cont-1")
    StageGateService().decide(
        session,
        continuation,
        "G10",
        _g10_decision_request(continuation, package),
        actor="operator",
        now=NOW_UTC,
    )
    attempt = session.get(RepairAttemptModel, attempt_id)
    attempt.g10_gate_package_id = recorded_id
    session.commit()
    session.close()

    _requeue_cont(factory, worker="worker-2")
    with pytest.raises(TransformerStageError) as raised:
        orchestrator.advance("cont-1", "worker-2")
    assert raised.value.code == "G10_APPROVAL_REQUIRED"
    session = factory()
    assert session.get(RepairAttemptModel, attempt_id).status != "applied"
    session.close()
    engine.dispose()


def test_g10_create_replay_leaves_one_package_and_no_orphan_artifacts(tmp_path: Path):
    """Idempotent G10 create replay writes no second gate artifact pair.

    RED until the fix: replay calls write_gate_package + register_artifact
    before create() returns the existing pending package, orphaning a fresh
    artifact/metadata pair on every replay.
    """
    engine, factory = _g10_database(tmp_path)
    _store, _workspace, artifacts, attempt_id, _failure, _context, _proposal, _review, _fp = (
        _seed_g10(factory, tmp_path)
    )
    orchestrator = _g10_orchestrator(factory)
    orchestrator.advance("cont-1", "worker-1")

    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "waiting_gate"
    continuation.current_node = "create_g10"
    continuation.status = "running"
    continuation.worker_id = "worker-2"
    continuation.lease_expires_at = NOW_UTC + timedelta(seconds=120)
    continuation.state_version += 1
    session.commit()
    session.close()

    orchestrator.advance("cont-1", "worker-2")

    session = factory()
    packages = session.query(StageGatePackageModel).filter_by(gate_id="G10").all()
    assert len(packages) == 1
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "waiting_gate"
    assert continuation.current_node == "wait_g10"
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.g10_gate_package_id == packages[0].id
    gate_pairs = sorted(
        str(path.relative_to(artifacts)).replace("\\", "/")
        for path in artifacts.rglob("04_workflow_state/stages/stage-1/gates/g10-package*")
        if path.is_file()
    )
    assert len(gate_pairs) == 2
    assert sum(not name.endswith(".meta.json") for name in gate_pairs) == 1
    assert sum(name.endswith(".meta.json") for name in gate_pairs) == 1
    registered = (
        session.query(ArtifactMetadataModel)
        .filter(ArtifactMetadataModel.relative_path.like("%/gates/g10-package%"))
        .all()
    )
    assert len(registered) == 1
    session.close()
    engine.dispose()


def _decision(version: int, *, key: str = "g07-approve", fingerprint: str = "sha256:workspace"):
    return StageGateDecisionRequest(
        expected_state_version=version,
        idempotency_key=key,
        package_checksum="sha256:g07-package",
        workspace_fingerprint=fingerprint,
        decision="approve",
        correlation_id="correlation-1",
    )


def test_g07_is_bound_to_state_package_and_workspace_and_wakes_once(tmp_path: Path):
    engine, session = _session(tmp_path)
    continuation = _create(TransformationContinuationService(), session)
    continuation.status = "running"
    continuation.worker_id = "worker-1"
    gate = StageGateService().create(
        session,
        continuation,
        gate_id="G07",
        package_artifact_id="artifact-g07",
        package_checksum="sha256:g07-package",
        artifact_set_checksum="sha256:g07-set",
        workspace_fingerprint="sha256:workspace",
        now=NOW,
    )

    assert continuation.status == "waiting_gate"
    assert gate.expected_state_version == continuation.state_version
    result = StageGateService().decide(
        session, continuation, "G07", _decision(continuation.state_version), actor="operator", now=NOW
    )
    replay = StageGateService().decide(
        session, continuation, "G07", _decision(gate.expected_state_version), actor="operator", now=NOW
    )

    assert result.id == replay.id
    assert continuation.status == "queued"
    assert continuation.current_node == "bootstrap_install"
    assert continuation.wake_sequence == 1
    session.close()
    engine.dispose()


def test_g07_rejects_stale_workspace_fingerprint(tmp_path: Path):
    engine, session = _session(tmp_path)
    continuation = _create(TransformationContinuationService(), session)
    continuation.status = "running"
    continuation.worker_id = "worker-1"
    StageGateService().create(
        session,
        continuation,
        gate_id="G07",
        package_artifact_id="artifact-g07",
        package_checksum="sha256:g07-package",
        artifact_set_checksum="sha256:g07-set",
        workspace_fingerprint="sha256:workspace",
        now=NOW,
    )

    with pytest.raises(StageGateError, match="fingerprint"):
        StageGateService().decide(
            session,
            continuation,
            "G07",
            _decision(continuation.state_version, fingerprint="sha256:stale"),
            actor="operator",
            now=NOW,
        )
    session.close()
    engine.dispose()
