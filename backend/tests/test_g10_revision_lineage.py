"""Focused regression tests for the G10 human-revision lineage fixes.

FIX A: the revision-context embedded parent proposal/review are compared
semantically after canonicalization through the authoritative schemas, so
representation-only nested None keys cannot invalidate legitimate lineage while
real semantic drift still fails closed with REPAIR_PARENT_LINEAGE_INVALID.

FIX B: StageGateError raised at the workflow boundary is routed into the
existing durable fail/block path instead of escaping to the worker loop.
"""

from __future__ import annotations

import copy
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.domain.contracts import ArtifactType, WorkflowEventType
from app.orchestration.transformer_graph import TransformerOrchestrator, TransformerWorkflow
from app.repositories.models import (
    ArtifactMetadataModel,
    LlmInvocationModel,
    MigrationPlanModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageExecutionPlanModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    WorkflowEventModel,
)
from app.services.artifact_binding import canonical_artifact_set_checksum
from app.services.repair_application_service import RepairProposal, RepairReview
from app.services.stage_gate_service import (
    _SEMANTIC_RECOVERY_REASON,
    StageGateError,
    StageGateService,
    _canonical_revision_payload,
)
from app.services.transformer_stage_service import TransformerStageService
from tests.test_stage_gate_service import (
    NOW_UTC,
    _g10_database,
    _g10_orchestrator,
    _g10_scope,
    _seed_g10,
)


@pytest.fixture
def factory(tmp_path):
    _engine, factory = _g10_database(tmp_path)
    return factory


def _dependency_add_proposal(*, version: str) -> dict:
    """A raw proposal artifact payload as the production writer stores it
    (optional operation fields omitted, never written as nulls)."""
    return {
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "dependency_add",
                "path": "package.json",
                "section": "devDependencies",
                "package": "example-package",
                "new_version": version,
                "old_text": '{"name":"fixture"}',
                "new_text": '{"name":"fixture","devDependencies":{"example-package":"' + version + '"}}',
                "preimage_sha256": "sha256:preimage",
                "provenance": [],
            }
        ],
        "unified_diff": None,
        "touched_files": ["package.json"],
        "rationale": ["Add the missing test environment package."],
        "risk_level": "low",
        "validation_targets": ["test"],
        "limitations": [],
    }


def _old_writer_round_trip(payload: dict) -> dict:
    """Simulate the pre-fix request_revision representation: a pydantic
    validate/model_dump round-trip that adds null-valued optional fields."""
    return RepairProposal.model_validate(payload).model_dump(mode="json")


def _padded_with_nulls(payload: dict) -> dict:
    padded = copy.deepcopy(payload)
    for key in (
        "blocking_dependency",
        "checkpoint_id",
        "content",
        "failure_type",
        "repair_kind",
        "schema_version",
        "strategy",
        "target_state",
    ):
        padded["operations"][0][key] = None
    return padded


def test_revision_proposal_canonicalization_accepts_nested_none_representation():
    raw = _dependency_add_proposal(version="^1.0.0")
    padded = _padded_with_nulls(raw)
    assert padded != raw, "fixture must differ representation-only"
    assert _canonical_revision_payload(padded, review=False) == _canonical_revision_payload(
        raw, review=False
    )


def test_revision_proposal_canonicalization_rejects_semantic_version_drift():
    raw = _dependency_add_proposal(version="^1.0.0")
    drifted = _padded_with_nulls(_dependency_add_proposal(version="^2.0.0"))
    assert _canonical_revision_payload(drifted, review=False) != _canonical_revision_payload(
        raw, review=False
    )


def test_g10_accepts_recovered_proposer_semantic_retry_lineage():
    parent_id = "repair-parent"
    child_id = "repair-child"
    recovered_id = f"{parent_id}:proposer:recovery-1"
    evidence_fields = {
        name: None
        for name in (
            "proposal_artifact_id",
            "proposal_checksum",
            "review_artifact_id",
            "review_checksum",
            "reviewer_invocation_id",
            "g10_gate_package_id",
            "apply_ledger_artifact_id",
            "apply_ledger_checksum",
            "validation_summary_artifact_id",
            "validation_summary_checksum",
            "post_fingerprint",
        )
    }
    parent = SimpleNamespace(
        id=parent_id,
        run_id="run-1",
        stage_id="stage-1",
        attempt_number=3,
        status="superseded",
        completed_at=NOW_UTC,
        proposer_invocation_id=recovered_id,
        **evidence_fields,
    )
    attempt = SimpleNamespace(
        id=child_id,
        run_id="run-1",
        stage_id="stage-1",
        attempt_number=4,
        parent_review_artifact_id=None,
        parent_review_checksum=None,
    )
    continuation = SimpleNamespace(run_id="run-1")
    base = SimpleNamespace(status="uncertain_abandoned")
    retry = SimpleNamespace(
        status="failed",
        retries=0,
        failure_stage="repair_semantics",
        failure_code="REPAIR_PROPOSAL_SCHEMA_INVALID",
    )
    event = SimpleNamespace(
        reason=_SEMANTIC_RECOVERY_REASON,
        payload={"attempt_id": parent_id, "child_attempt_id": child_id},
    )
    session = MagicMock()
    session.scalars.return_value.all.return_value = [event]
    session.scalar.side_effect = [base, retry]

    StageGateService._validate_recovery_parent_lineage(
        session,
        continuation,
        attempt,
        parent,
        {"parent_attempt_id": parent_id, "parent_review_artifact_id": None, "parent_review_checksum": None},
    )


def _seed_child_attempt(
    factory,
    tmp_path,
    *,
    previous_proposal_transform,
) -> None:
    """Seed a production-shaped child (human-revision) repair attempt.

    The parent is seeded through the real FailureEvidenceService writers; the
    child carries a revision-context context pack whose human_revision embeds
    the parent proposal in the given representation. G10 package construction
    mirrors the orchestrator.
    """
    (
        store,
        workspace,
        artifacts,
        parent_id,
        failure,
        context,
        proposal,
        review,
        workspace_fingerprint,
    ) = _seed_g10(factory, tmp_path)
    run_id = "run-1"
    stage_id = "stage-1"
    child_id = "repair-2"

    parent_proposal_payload = json.loads(
        (artifacts / proposal.ref.relative_path).read_text(encoding="utf-8")
    )
    parent_review_payload = json.loads(
        (artifacts / review.ref.relative_path).read_text(encoding="utf-8")
    )
    parent_context_payload = json.loads(
        (artifacts / context.ref.relative_path).read_text(encoding="utf-8")
    )
    revision_context = copy.deepcopy(parent_context_payload)
    revision_context["human_revision"] = {
        "instruction": "Regenerate the proposal from the current evidence.",
        "parent_attempt_id": parent_id,
        "parent_proposal_id": proposal.ref.artifact_id,
        "parent_proposal_checksum": proposal.ref.checksum,
        "previous_proposal": previous_proposal_transform(parent_proposal_payload),
        "reviewer_output": RepairReview.model_validate(parent_review_payload).model_dump(
            mode="json"
        ),
        "grounding_instructions": "CURRENT_WORKSPACE_FILES are the only valid preimage authority.",
    }
    revision_stored = store.write_text_artifact(
        run_id,
        f"05_repairs/attempt-{child_id}/revision-context.json",
        json.dumps(revision_context, sort_keys=True, indent=2),
        ArtifactType.JSON,
        stage_id=stage_id,
        attempt_id=child_id,
        created_by="repair-human-revision",
        created_at=NOW_UTC,
        input_hashes={
            "proposal": proposal.ref.checksum,
            "review": review.ref.checksum,
            "instruction": "sha256:instruction",
        },
        policy_version="repair-human-revision-v1",
    )

    child_proposal_payload = copy.deepcopy(parent_proposal_payload)
    child_proposal_payload["failure_evidence_checksum"] = failure.ref.checksum
    child_proposal_payload["context_pack_checksum"] = revision_stored.ref.checksum
    child_proposal = store.write_text_artifact(
        run_id,
        f"05_repairs/attempt-{child_id}/proposal.json",
        json.dumps(child_proposal_payload, sort_keys=True),
        ArtifactType.JSON,
        stage_id=stage_id,
        attempt_id=child_id,
        created_by="repair-proposal",
        created_at=NOW_UTC,
    )
    child_review_payload = {
        "decision": "accept",
        "findings": [],
        "policy_checks": ["paths"],
        "risk_assessment": "low risk, minimal change",
        "required_validation_targets": ["test"],
        "limitations": [],
        "proposal_checksum": child_proposal.ref.checksum,
    }
    child_review = store.write_text_artifact(
        run_id,
        f"05_repairs/attempt-{child_id}/review.json",
        json.dumps(child_review_payload, sort_keys=True),
        ArtifactType.JSON,
        stage_id=stage_id,
        attempt_id=child_id,
        created_by="repair-review",
        created_at=NOW_UTC,
    )
    child_diff = store.write_text_artifact(
        run_id,
        f"05_repairs/attempt-{child_id}/candidate.diff",
        "--- a/package.json\n+++ b/package.json\n",
        ArtifactType.DIFF,
        stage_id=stage_id,
        attempt_id=child_id,
        created_by="repair-proposer-safe-diff",
        created_at=NOW_UTC,
        input_hashes={"proposal": child_proposal.ref.checksum},
        policy_version="repair-safe-diff-v1",
    )

    session = factory()
    run = session.get(MigrationRunModel, run_id)
    continuation = session.scalar(
        select(TransformationContinuationModel).where(
            TransformationContinuationModel.run_id == run_id
        )
    )
    child = RepairAttemptModel(
        id=child_id,
        run_id=run_id,
        stage_id=stage_id,
        attempt_number=2,
        status="review_accepted",
        risk_level="low",
        diagnosis=f"human revision; parent={parent_id}",
        checkpoint_id="ckpt-pre",
        pre_fingerprint=workspace_fingerprint,
        failure_evidence_artifact_id=failure.ref.artifact_id,
        failure_evidence_checksum=failure.ref.checksum,
        failure_route_artifact_id=failure.ref.artifact_id,
        failure_route_checksum=failure.ref.checksum,
        context_pack_artifact_id=revision_stored.ref.artifact_id,
        context_pack_checksum=revision_stored.ref.checksum,
        proposal_artifact_id=child_proposal.ref.artifact_id,
        proposal_checksum=child_proposal.ref.checksum,
        proposer_invocation_id=f"{child_id}:proposer",
        review_artifact_id=child_review.ref.artifact_id,
        review_checksum=child_review.ref.checksum,
        reviewer_invocation_id=f"{child_id}:reviewer",
        parent_attempt_id=parent_id,
        parent_review_artifact_id=review.ref.artifact_id,
        parent_review_checksum=review.ref.checksum,
        validation_targets=["build", "test"],
        failure_fingerprint="sha256:" + "f" * 64,
        created_at=NOW_UTC,
        updated_at=NOW_UTC,
    )
    session.add(child)
    for stored in (revision_stored, child_proposal, child_review, child_diff):
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
    for invocation_id, role, artifact in (
        (f"{child_id}:proposer", "repair_proposer", child_proposal),
        (f"{child_id}:reviewer", "repair_reviewer", child_review),
    ):
        session.add(
            LlmInvocationModel(
                id=invocation_id,
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key=invocation_id,
                request_checksum="sha256:request",
                input_hashes=[],
                correlation_id=invocation_id,
                actor="transformer",
                role=role,
                task_type="repair_diagnosis" if role == "repair_proposer" else "repair_review",
                provider="azure_openai",
                deployment_alias="azure-openai",
                prompt_version="prompt-repair-v1",
                schema_version="schema-registry-v1",
                pricing_version="mvp-pricing-2026-01",
                stage="repair",
                redacted_summary=json.dumps({"risk_level": "low"}, sort_keys=True),
                status="completed",
                artifact_ids=[artifact.ref.artifact_id],
                artifact_checksums={artifact.ref.artifact_id: artifact.ref.checksum},
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

    session = factory()
    child = session.get(RepairAttemptModel, child_id)
    continuation = session.scalar(
        select(TransformationContinuationModel).where(
            TransformationContinuationModel.run_id == run_id
        )
    )
    binding = session.scalar(
        select(StageWorkspaceBindingModel).where(
            StageWorkspaceBindingModel.run_id == run_id,
            StageWorkspaceBindingModel.stage_id == stage_id,
            StageWorkspaceBindingModel.active.is_(True),
        )
    )
    plan = session.get(MigrationPlanModel, continuation.plan_id)
    stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
    proposer = session.get(LlmInvocationModel, child.proposer_invocation_id)
    reviewer = session.get(LlmInvocationModel, child.reviewer_invocation_id)
    payload = {
        "gate_id": "G10",
        "run_id": run_id,
        "stage_id": stage_id,
        "plan_version": plan.version,
        "stage_plan_checksum": continuation.stage_plan_checksum,
        "workspace_fingerprint": binding.workspace_fingerprint,
        "failure_evidence_checksum": child.failure_evidence_checksum,
        "context_pack_checksum": child.context_pack_checksum,
        "proposal_checksum": child.proposal_checksum,
        "review_checksum": child.review_checksum,
        "repair_attempt_id": child.id,
        "proposal_artifact_id": child.proposal_artifact_id,
        "review_artifact_id": child.review_artifact_id,
        "parent_attempt_id": child.parent_attempt_id,
        "parent_review_artifact_id": child.parent_review_artifact_id,
        "parent_review_checksum": child.parent_review_checksum,
        "proposer_invocation_id": child.proposer_invocation_id,
        "reviewer_invocation_id": child.reviewer_invocation_id,
        "workspace_binding_id": binding.id,
        "workspace_path": binding.workspace_path,
        "risk_level": child.risk_level,
        "validation_targets": ["build", "test"],
        "proposer_invocation_request_checksum": proposer.request_checksum,
        "proposer_invocation_prompt_version": proposer.prompt_version,
        "proposer_invocation_schema_version": proposer.schema_version,
        "reviewer_invocation_request_checksum": reviewer.request_checksum,
        "reviewer_invocation_prompt_version": reviewer.prompt_version,
        "reviewer_invocation_schema_version": reviewer.schema_version,
        "review_override_required": False,
        "diff_artifact_id": child_diff.ref.artifact_id,
        "diff_checksum": child_diff.ref.checksum,
    }
    payload["backend_lineage_checksum"] = TransformerStageService.checksum(
        {key: value for key, value in payload.items() if key != "backend_lineage_checksum"}
    )
    gate = TransformerStageService(scope=_g10_scope(factory)).write_gate_package(
        run_id=run_id,
        stage_id=stage_id,
        artifact_root=str(artifacts),
        gate_id="G10",
        payload=payload,
        attempt_id=child.id,
    )
    TransformerStageService.register_artifact(session, gate, continuation)
    artifact_set_checksum = canonical_artifact_set_checksum(
        [
            {"artifact_id": child.failure_evidence_artifact_id, "checksum": child.failure_evidence_checksum},
            {"artifact_id": child.context_pack_artifact_id, "checksum": child.context_pack_checksum},
            {"artifact_id": child.proposal_artifact_id, "checksum": child.proposal_checksum},
            {"artifact_id": child.review_artifact_id, "checksum": child.review_checksum},
            {"artifact_id": gate.ref.artifact_id, "checksum": gate.ref.checksum},
        ]
    )
    StageGateService().create(
        session,
        continuation,
        gate_id="G10",
        package_artifact_id=gate.ref.artifact_id,
        package_checksum=gate.ref.checksum,
        artifact_set_checksum=artifact_set_checksum,
        workspace_fingerprint=binding.workspace_fingerprint,
    )
    session.commit()
    session.close()


def _seed_recovery_child_g10(
    factory,
    tmp_path,
    *,
    recovery_event=True,
    retry_failure_code="REPAIR_REPLACEMENT_MISSING",
):
    """Seed a G10-ready recovery child with proposal-less parent evidence."""
    (
        store,
        _workspace,
        artifacts,
        child_id,
        failure,
        base_context,
        base_proposal,
        base_review,
        workspace_fingerprint,
    ) = _seed_g10(factory, tmp_path)
    parent_id = "repair-0"
    human_revision = {
        "instruction": "Preserve the existing human repair intent.",
        "parent_attempt_id": "repair-human-source",
        "parent_proposal_id": "artifact-human-proposal",
        "parent_proposal_checksum": "sha256:human-proposal",
        "previous_proposal": {"operations": []},
        "reviewer_output": {"decision": "request_changes"},
        "grounding_instructions": "Use authoritative workspace content.",
    }
    base_payload = json.loads(base_context.content)
    parent_context = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{parent_id}/context.json",
        json.dumps({**base_payload, "human_revision": human_revision}, sort_keys=True),
        ArtifactType.JSON,
        stage_id="stage-1",
        created_by="repair-human-revision",
        created_at=NOW_UTC,
        input_hashes={"failure": failure.ref.checksum},
        policy_version="repair-context-pack-v1",
    )
    child_context = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{child_id}/recovery-context.json",
        json.dumps({**base_payload, "human_revision": human_revision}, sort_keys=True),
        ArtifactType.JSON,
        stage_id="stage-1",
        created_by="repair-recovery-context",
        created_at=NOW_UTC,
        input_hashes={
            "failure": failure.ref.checksum,
            "recovered_from": parent_context.ref.checksum,
        },
        policy_version="repair-context-pack-v1",
    )
    proposal_payload = json.loads(base_proposal.content)
    proposal_payload["context_pack_checksum"] = child_context.ref.checksum
    child_proposal = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{child_id}/recovery-proposal.json",
        json.dumps(proposal_payload, sort_keys=True),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=child_id,
        created_by="repair-proposal",
        created_at=NOW_UTC,
    )
    review_payload = json.loads(base_review.content)
    review_payload["proposal_checksum"] = child_proposal.ref.checksum
    child_review = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{child_id}/recovery-review.json",
        json.dumps(review_payload, sort_keys=True),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=child_id,
        created_by="repair-review",
        created_at=NOW_UTC,
    )
    child_diff = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{child_id}/candidate.diff",
        "--- a/src/app.ts\n+++ b/src/app.ts\n@@ -1 +1 @@\n-old\n+new\n",
        ArtifactType.DIFF,
        stage_id="stage-1",
        attempt_id=child_id,
        created_by="repair-proposer-safe-diff",
        created_at=NOW_UTC,
        input_hashes={"proposal": child_proposal.ref.checksum},
        policy_version="repair-safe-diff-v1",
    )

    session = factory()
    child = session.get(RepairAttemptModel, child_id)
    child.context_pack_artifact_id = child_context.ref.artifact_id
    child.context_pack_checksum = child_context.ref.checksum
    child.proposal_artifact_id = child_proposal.ref.artifact_id
    child.proposal_checksum = child_proposal.ref.checksum
    child.review_artifact_id = child_review.ref.artifact_id
    child.review_checksum = child_review.ref.checksum
    child.parent_attempt_id = parent_id
    child.parent_review_artifact_id = None
    child.parent_review_checksum = None
    child.status = "review_accepted"
    proposer = session.get(LlmInvocationModel, child.proposer_invocation_id)
    reviewer = session.get(LlmInvocationModel, child.reviewer_invocation_id)
    proposer.artifact_ids = [child_proposal.ref.artifact_id]
    proposer.artifact_checksums = {child_proposal.ref.artifact_id: child_proposal.ref.checksum}
    reviewer.artifact_ids = [child_review.ref.artifact_id]
    reviewer.artifact_checksums = {child_review.ref.artifact_id: child_review.ref.checksum}
    session.add(
        RepairAttemptModel(
            id=parent_id,
            run_id="run-1",
            stage_id="stage-1",
            attempt_number=0,
            status="superseded",
            risk_level="unknown",
            diagnosis="semantic retry recovery parent",
            checkpoint_id="ckpt-pre",
            failure_evidence_artifact_id=failure.ref.artifact_id,
            failure_evidence_checksum=failure.ref.checksum,
            failure_route_artifact_id="artifact-route",
            failure_route_checksum="sha256:route",
            context_pack_artifact_id=parent_context.ref.artifact_id,
            context_pack_checksum=parent_context.ref.checksum,
            pre_fingerprint=workspace_fingerprint,
            failure_fingerprint=base_payload["failure_fingerprint"],
            completed_at=NOW_UTC,
            created_at=NOW_UTC,
            updated_at=NOW_UTC,
        )
    )
    for stored in (parent_context, child_context, child_proposal, child_review, child_diff):
        session.add(
            ArtifactMetadataModel(
                id="metadata-" + stored.ref.artifact_id,
                run_id="run-1",
                stage_id="stage-1",
                artifact_type=stored.ref.artifact_type.value,
                relative_path=stored.ref.relative_path,
                checksum=stored.ref.checksum,
                created_at=NOW_UTC,
                finalized_at=NOW_UTC,
                immutable=True,
            )
        )
    for suffix, retries, failure_code in (
        ("", 0, "REPAIR_REPLACEMENT_MISSING"),
        (":semantic-retry-1", 1, retry_failure_code),
    ):
        invocation_id = f"{parent_id}:proposer{suffix}"
        session.add(
            LlmInvocationModel(
                id=invocation_id,
                run_id="run-1",
                stage_id="stage-1",
                idempotency_key=invocation_id,
                request_checksum="sha256:recovery-request-" + str(retries),
                input_hashes=[failure.ref.checksum, parent_context.ref.checksum],
                correlation_id=invocation_id,
                actor="transformer",
                role="repair_proposer",
                task_type="repair_diagnosis",
                provider="azure_openai",
                deployment_alias="azure-openai",
                prompt_version="prompt-repair-proposer-candidate-v2",
                schema_version="schema-registry-v1",
                pricing_version="mvp-pricing-2026-01",
                stage="repair",
                redacted_summary=None,
                status="failed",
                failure_code=failure_code,
                artifact_ids=[],
                artifact_checksums={},
                state_version=1,
                event_sequence=0,
                retries=retries,
                failure_stage="repair_semantics",
                started_at=NOW_UTC,
                completed_at=NOW_UTC,
                created_at=NOW_UTC,
            )
        )
    if recovery_event:
        session.add(
            WorkflowEventModel(
                id="recovery-event",
                run_id="run-1",
                stage_id="stage-1",
                event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED.value,
                idempotency_key="cont-1:semantic-recovery:test",
                actor="operator",
                reason="semantic retry exhausted recovery requested",
                sequence=1,
                payload={"attempt_id": parent_id, "child_attempt_id": child_id},
                occurred_at=NOW_UTC,
            )
        )
    session.commit()
    session.close()


def test_g10_child_lineage_accepts_old_writer_representation(factory, tmp_path):
    _seed_child_attempt(factory, tmp_path, previous_proposal_transform=_old_writer_round_trip)

    session = factory()
    continuation = session.scalar(
        select(TransformationContinuationModel).where(
            TransformationContinuationModel.run_id == "run-1"
        )
    )
    assert continuation is not None
    assert continuation.status == "waiting_gate"
    assert continuation.current_node == "wait_g10"
    session.close()


def test_g10_accepts_recovery_child_with_proven_recovery_ancestry(factory, tmp_path):
    _seed_recovery_child_g10(factory, tmp_path)

    _g10_orchestrator(factory).advance("cont-1", "worker-1")

    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "waiting_gate"
    assert continuation.current_node == "wait_g10"
    session.close()


def test_g10_accepts_recovery_child_with_legacy_ambiguous_retry(factory, tmp_path):
    _seed_recovery_child_g10(
        factory,
        tmp_path,
        retry_failure_code="REPAIR_OPERATION_AMBIGUOUS",
    )

    _g10_orchestrator(factory).advance("cont-1", "worker-1")

    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.status == "waiting_gate"
    assert continuation.current_node == "wait_g10"
    session.close()


def test_g10_rejects_proposalless_recovery_child_without_recovery_event(
    factory, tmp_path
):
    _seed_recovery_child_g10(factory, tmp_path, recovery_event=False)

    with pytest.raises(StageGateError) as raised:
        _g10_orchestrator(factory).advance("cont-1", "worker-1")
    assert raised.value.code == "REPAIR_PARENT_LINEAGE_INVALID"


def test_g10_child_lineage_rejects_semantic_drift(factory, tmp_path):
    def drift(parent_payload):
        drifted = _old_writer_round_trip(parent_payload)
        drifted["operations"][0]["new_text"] = drifted["operations"][0]["new_text"] + "// tampered"
        return drifted

    with pytest.raises(StageGateError) as error:
        _seed_child_attempt(factory, tmp_path, previous_proposal_transform=drift)
    assert error.value.code == "REPAIR_PARENT_LINEAGE_INVALID"


def test_invoke_routes_stagegateerror_to_durable_fail():
    workflow = TransformerWorkflow.__new__(TransformerWorkflow)
    orchestrator = MagicMock()
    workflow.orchestrator = orchestrator
    error = StageGateError(
        "REPAIR_PARENT_LINEAGE_INVALID", "G10 human revision context is incomplete or stale"
    )
    workflow.graph = MagicMock()
    workflow.graph.invoke.side_effect = error

    workflow.invoke("cont-1", "worker-1")

    orchestrator.fail.assert_called_once_with("cont-1", "worker-1", error)


def test_fail_durably_blocks_continuation_on_stagegateerror(tmp_path):
    _engine, factory = _g10_database(tmp_path)
    session = factory()
    run = MigrationRunModel(
        id="run-block",
        status="STAGE_CREATED",
        run_phase="FEASIBILITY_PLANNING",
        phase_status="completed",
        state_version=5,
        run_root=str(tmp_path),
        artifact_root=str(tmp_path / "artifacts"),
        workspace_aliases={"STAGE_SANDBOX": str(tmp_path)},
        created_at=NOW_UTC,
        updated_at=NOW_UTC,
    )
    continuation = TransformationContinuationModel(
        id="cont-block",
        run_id=run.id,
        current_stage_id="stage-block",
        thread_id="thread-block",
        status="running",
        current_node="create_g10",
        g06_approval_id="g06-block",
        plan_id="plan-block",
        plan_checksum="sha256:plan",
        stage_plan_id="stage-plan-block",
        stage_plan_checksum="sha256:stage-plan",
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
    session.add_all([run, continuation])
    session.commit()
    session.close()

    orchestrator = TransformerOrchestrator(scope=_g10_scope(factory))
    orchestrator.fail(
        "cont-block",
        "worker-1",
        StageGateError(
            "REPAIR_PARENT_LINEAGE_INVALID", "G10 human revision context is incomplete or stale"
        ),
    )

    session = factory()
    cont = session.get(TransformationContinuationModel, "cont-block")
    assert cont is not None
    assert cont.status == "blocked"
    assert cont.last_error_code == "REPAIR_PARENT_LINEAGE_INVALID"
    assert cont.last_error_message == "G10 human revision context is incomplete or stale"
    assert cont.worker_id is None
    session.close()
