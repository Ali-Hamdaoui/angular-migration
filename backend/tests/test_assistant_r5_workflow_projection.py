from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.contracts import AssistantNextStepProposalDto
from app.repositories.models import (
    AssistantLifecycleEventModel, Base, CommandExecutionModel, ExecutionProfileModel, G02ApprovalModel, G06ApprovalModel,
    LlmInvocationModel, MigrationRunModel, MigrationStageModel, RepairAttemptModel, SourceSnapshotModel, StageStepModel, UsageCostRecordModel,
)
from app.repositories.planning_review_models import PlanningReviewModel
from app.repositories.models.workflow import WorkflowEventModel
from app.services.workflow_projection_service import WorkflowProjectionService


def _scope(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'r5.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _run(session, run_id, *, status="RUNNING", phase="FEASIBILITY_PLANNING", version=7):
    now = datetime.now(UTC)
    row = MigrationRunModel(id=run_id, status=status, run_phase=phase, phase_status="running", approval_status="approved", repair_status="not_required", state_version=version, source_angular_version="15", target_angular_version="18", created_at=now - timedelta(seconds=30), updated_at=now)
    session.add(row)
    return row


def _g06(run_id, status="pending", version=8):
    now = datetime.now(UTC)
    return G06ApprovalModel(id=f"g06-{run_id}", run_id=run_id, gate_id="G06", gate_version="g06-v1", idempotency_key=f"g06-key-{run_id}", actor="owner", status=status, decision=None, package_checksum="package", artifact_set_checksum="artifacts", plan_checksum="plan", stage_plan_checksum="stage", plan_version=1, workspace_fingerprint="workspace", artifact_ids=[], state_version=version, event_sequence=version, created_at=now, updated_at=now)


def test_g06_owner_overrides_generic_run_approval_and_proposes_governed_review(tmp_path):
    sessions = _scope(tmp_path)
    with sessions() as session:
        _run(session, "g06-run")
        session.add(MigrationStageModel(id="planning-stage", run_id="g06-run", stage_order=1, status="WAITING_APPROVAL", created_at=datetime.now(UTC), started_at=datetime.now(UTC)))
        session.add(StageStepModel(id="planning-step", run_id="g06-run", stage_id="planning-stage", name="planning-review", status="WAITING_APPROVAL", component_type="PlanningReview"))
        session.add(_g06("g06-run"))
        session.add(PlanningReviewModel(id="review", run_id="g06-run", idempotency_key="review-key", request_checksum="checksum", actor="owner", correlation_id="corr", migration_plan_id="plan", stage_plan_id="stage", plan_version=1, artifact_set_checksum="artifacts", status="accepted", package={}, artifact_ids=[], artifact_checksums={}, state_version=8, event_sequence=8, created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
        session.commit()
        projection = WorkflowProjectionService().build(session, "g06-run")
    assert projection.current_gate_id.value == "G06"
    assert projection.gate_state.value == "pending"
    assert projection.phase.value == "Planning"
    assert projection.stage.value == "planning-stage"
    assert projection.step.value == "planning-review"
    assert "Review G06" in projection.remaining_work
    proposal = AssistantNextStepProposalDto.model_validate(projection.next_step_proposals[0])
    assert proposal.action_key == "review_g06"
    assert proposal.target_route.endswith("/plan/review")
    assert proposal.requires_human_approval is True
    assert proposal.executable_by_assistant is False


def test_runtime_blocker_preserves_snapshot_and_g02_and_is_not_source_failure(tmp_path):
    sessions = _scope(tmp_path)
    now = datetime.now(UTC)
    with sessions() as session:
        _run(session, "runtime-run", status="FAILED", phase="PREFLIGHT_SNAPSHOT")
        session.add(MigrationStageModel(id="snapshot-stage", run_id="runtime-run", stage_order=1, status="PASSED", created_at=now, started_at=now, completed_at=now))
        session.add(SourceSnapshotModel(id="snapshot", run_id="runtime-run", idempotency_key="snapshot-key", actor="owner", status="created", source_path="source", snapshot_path="snapshot", policy_version="v1", artifact_ids=[], state_version=3, event_sequence=3, created_at=now, updated_at=now))
        session.add(G02ApprovalModel(id="g02", run_id="runtime-run", gate_id="G02", gate_version="g02-v1", idempotency_key="g02-key", actor="owner", status="approved", decision="approve", package_checksum="package", artifact_set_checksum="artifacts", snapshot_id="snapshot", state_version=4, event_sequence=4, package={}, artifact_ids=[], created_at=now, updated_at=now))
        session.add(ExecutionProfileModel(id="profile", run_id="runtime-run", idempotency_key="profile-key", request_checksum="checksum", policy_version="v1", status="blocked", source_angular_exact="15.2.0", selected_profile_id=None, selected_checksum=None, profiles=[], blockers=["NO_COMPATIBLE_RUNTIME_PROFILE"], guidance=["Install approved paired Node/npm/npx runtime"], artifact_ids=[], state_version=7, event_sequence=7, created_at=now, updated_at=now))
        session.add(WorkflowEventModel(id="source-failed-event", run_id="runtime-run", stage_id=None, event_type="SOURCE_INTAKE_FAILED", reason="event is not the owner", sequence=99, payload={"failure_reason": "stale event text"}, occurred_at=now))
        session.commit()
        projection = WorkflowProjectionService().build(session, "runtime-run")
    assert "Immutable source snapshot" in projection.completed_work
    assert "G02 approval" in projection.completed_work
    assert projection.blocker.value == "NO_COMPATIBLE_RUNTIME_PROFILE"
    assert projection.failure_classification.value == "runtime_profile_unavailable"
    assert projection.failure_reason.value.startswith("Runtime resolution was attempted")
    assert projection.remaining_work == ["Resolve runtime profile and retry"]
    assert projection.next_step_proposals[0].action_key == "retry_runtime_profile_resolution"
    assert projection.next_step_proposals[0].executable_by_assistant is False
    assert projection.semantic_state_version == 7


def test_repair_owner_and_terminal_states_remain_semantically_separate(tmp_path):
    sessions = _scope(tmp_path)
    now = datetime.now(UTC)
    with sessions() as session:
        _run(session, "repair-run", status="FAILED", phase="STAGED_MIGRATION")
        session.add(MigrationStageModel(id="stage", run_id="repair-run", stage_order=1, status="PASSED", created_at=now, started_at=now, completed_at=now))
        session.add(RepairAttemptModel(id="repair", run_id="repair-run", stage_id="stage", attempt_number=1, status="in_progress", risk_level="low", created_at=now, diagnosis="bounded repair"))
        session.commit()
        repair = WorkflowProjectionService().build(session, "repair-run")
        session.add(MigrationRunModel(id="success-run", status="COMPLETED", run_phase="DELIVERY_REPORTING", phase_status="completed", approval_status="not_required", repair_status="not_required", state_version=4, created_at=now, updated_at=now))
        session.add(MigrationStageModel(id="success-stage", run_id="success-run", stage_order=1, status="PASSED", created_at=now, started_at=now, completed_at=now))
        session.add(MigrationRunModel(id="failed-run", status="FAILED", run_phase="STAGED_MIGRATION", phase_status="failed", approval_status="not_required", repair_status="not_required", state_version=5, created_at=now, updated_at=now))
        session.add(MigrationStageModel(id="failed-stage", run_id="failed-run", stage_order=1, status="PASSED", created_at=now, started_at=now, completed_at=now))
        session.add(CommandExecutionModel(id="failed-command", run_id="failed-run", executable="npm", arguments=["test"], status="failed", requested_at=now, finished_at=now, failure_code="EXIT_NONZERO", failure_message="command failed", command_id="test"))
        session.commit()
        success = WorkflowProjectionService().build(session, "success-run")
        failed = WorkflowProjectionService().build(session, "failed-run")
    assert repair.repair_state.value == "in_progress"
    assert "Complete governed repair" in repair.remaining_work
    assert repair.blocker.availability == "unavailable"
    assert repair.failure_reason.availability == "unavailable"
    assert success.remaining_work == []
    assert success.next_step_proposals == []
    assert "success-stage" in success.completed_work
    assert "failed-stage" in failed.completed_work
    assert failed.failure_classification.value == "EXIT_NONZERO"
    assert all(not proposal.executable_by_assistant for proposal in failed.next_step_proposals)


def test_semantic_version_survives_assistant_telemetry_and_pricing_zero_is_available(tmp_path):
    sessions = _scope(tmp_path)
    now = datetime.now(UTC)
    with sessions() as session:
        _run(session, "telemetry-run", version=11)
        before = WorkflowProjectionService().build(session, "telemetry-run")
        session.add(AssistantLifecycleEventModel(id="assistant-event", run_id="telemetry-run", conversation_id="conversation", message_id="message", event_type="ASSISTANT_RESPONSE_COMPLETED", sequence=1, correlation_id="corr", state_version=11, status="completed", idempotency_key="key", payload={}, occurred_at=now))
        session.add(LlmInvocationModel(id="invocation", run_id="telemetry-run", idempotency_key="invocation-key", request_checksum="checksum", input_hashes=[], correlation_id="corr", actor="owner", role="assistant", task_type="assistant_response", provider="test", deployment_alias="test", prompt_version="v1", schema_version="v1", pricing_version="zero", status="completed", state_version=11, event_sequence=1, started_at=now, completed_at=now, created_at=now))
        session.add(UsageCostRecordModel(id="usage", invocation_id="invocation", run_id="telemetry-run", stage_id=None, pricing_version="zero", input_tokens=0, output_tokens=0, total_tokens=0, input_price_per_million=0.0, output_price_per_million=0.0, input_cost_usd=0.0, output_cost_usd=0.0, total_cost_usd=0.0, created_at=now))
        session.commit()
        after = WorkflowProjectionService().build(session, "telemetry-run")
    assert before.semantic_state_version == after.semantic_state_version == 11
    assert before.phase.value == after.phase.value
    assert before.status.value == after.status.value
    assert after.operational_statistics.total_tokens == 0
    assert after.operational_statistics.total_cost_usd == 0.0
    assert after.pricing_availability.value == "available"


def test_missing_pricing_is_not_presented_as_free(tmp_path):
    sessions = _scope(tmp_path)
    with sessions() as session:
        _run(session, "no-price-run")
        projection = WorkflowProjectionService().build(session, "no-price-run")
    assert projection.pricing_availability.availability == "unavailable"
    assert projection.pricing_availability.reason == "not_configured"
    assert projection.operational_statistics.total_cost_usd is None


def test_projection_uses_usage_aggregate_for_non_completed_invocation(tmp_path):
    sessions = _scope(tmp_path)
    now = datetime.now(UTC)
    with sessions() as session:
        _run(session, "non-completed-usage-run")
        session.add(LlmInvocationModel(id="failed-invocation", run_id="non-completed-usage-run", idempotency_key="failed-key", request_checksum="checksum", input_hashes=[], correlation_id="corr", actor="owner", role="assistant", task_type="assistant_response", provider="test", deployment_alias="test", prompt_version="v1", schema_version="v1", pricing_version="pricing", status="failed", state_version=7, event_sequence=1, retries=2, started_at=now, completed_at=now, created_at=now))
        session.add(UsageCostRecordModel(id="failed-usage", invocation_id="failed-invocation", run_id="non-completed-usage-run", stage_id=None, pricing_version="pricing", input_tokens=9, output_tokens=3, total_tokens=17, input_price_per_million=1.0, output_price_per_million=2.0, input_cost_usd=0.000009, output_cost_usd=0.000006, total_cost_usd=0.000015, created_at=now))
        session.commit()
        projection = WorkflowProjectionService().build(session, "non-completed-usage-run")
    assert projection.operational_statistics.llm_calls_by_role == {"assistant": 1}
    assert projection.operational_statistics.input_tokens == 9
    assert projection.operational_statistics.output_tokens == 3
    assert projection.operational_statistics.total_tokens == 17
    assert projection.operational_statistics.total_cost_usd == 0.000015


def test_latest_command_is_deterministic_and_missing_pricing_is_unavailable(tmp_path):
    sessions = _scope(tmp_path)
    now = datetime.now(UTC)
    with sessions() as session:
        _run(session, "command-run", phase="STAGED_MIGRATION")
        for command_id, requested, status in (("older", now - timedelta(seconds=2), "completed"), ("latest", now, "failed")):
            session.add(CommandExecutionModel(id=command_id, run_id="command-run", executable="npm", arguments=["test"], status=status, requested_at=requested, finished_at=requested, failure_code="EXIT_NONZERO" if status == "failed" else None, failure_message="command failed" if status == "failed" else None, command_id=command_id))
        session.commit()
        projection = WorkflowProjectionService().build(session, "command-run")
    assert projection.latest_command_result.value["command_key"] == "latest"
    assert projection.failure_classification.value == "EXIT_NONZERO"
    assert projection.pricing_availability.availability == "unavailable"
    assert projection.pricing_availability.reason == "not_configured"
