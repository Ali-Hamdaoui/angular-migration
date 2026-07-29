"""One read-only, owner-based workflow projection for Assistant consumers."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.contracts import AssistantEvidenceReferenceDto, AssistantOperationalStatisticsDto, AssistantWorkflowProjectionDto, ProjectionValue
from app.repositories.analysis_models import AnalysisMetadataModel, G04ApprovalModel
from app.repositories.compatibility_models import CompatibilityResolutionModel, G05ApprovalModel
from app.repositories.models import (
    ArtifactMetadataModel, CommandExecutionModel, ExecutionProfileModel, G02ApprovalModel,
    LlmInvocationModel, MigrationRunModel, MigrationStageModel, RepairAttemptModel,
    SourceSnapshotModel, StageStepModel, UsageCostRecordModel, WorkflowEventModel,
)
from app.repositories.planning_review_models import G06ApprovalModel, PlanningReviewModel
from app.services.assistant_capabilities import build_next_step_proposals


def _value(value, *, supported: bool = True, reason: str | None = None) -> ProjectionValue:
    if not supported:
        return ProjectionValue(value=None, availability="unsupported", reason=reason or "owner_not_available")
    if value is None or value == "":
        return ProjectionValue(value=None, availability="unavailable", reason=reason or "owner_not_available")
    return ProjectionValue(value=value, availability="known")


def _seconds(start: datetime | None, end: datetime | None) -> float | None:
    if not start or not end:
        return None
    if start.tzinfo is None and end.tzinfo is not None:
        start = start.replace(tzinfo=end.tzinfo)
    elif end.tzinfo is None and start.tzinfo is not None:
        end = end.replace(tzinfo=start.tzinfo)
    return max(0.0, (end - start).total_seconds())


class WorkflowProjectionService:
    """Compose semantic facts from their persisted owners; events are chronology only."""

    @staticmethod
    def _latest(session, model, run_id: str, *ordering):
        return session.scalar(select(model).where(model.run_id == run_id).order_by(*ordering))

    def build(self, session, run_id: str) -> AssistantWorkflowProjectionDto:
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise ValueError("Migration run does not exist.")
        stages = list(session.scalars(select(MigrationStageModel).where(MigrationStageModel.run_id == run_id).order_by(MigrationStageModel.stage_order, MigrationStageModel.id)))
        steps = list(session.scalars(select(StageStepModel).where(StageStepModel.run_id == run_id).order_by(StageStepModel.id)))
        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id).order_by(WorkflowEventModel.sequence, WorkflowEventModel.id)))
        commands = list(session.scalars(select(CommandExecutionModel).where(CommandExecutionModel.run_id == run_id).order_by(CommandExecutionModel.requested_at, CommandExecutionModel.id)))
        invocations = list(session.scalars(select(LlmInvocationModel).where(LlmInvocationModel.run_id == run_id).order_by(LlmInvocationModel.created_at, LlmInvocationModel.id)))
        usage_records = list(session.scalars(select(UsageCostRecordModel).where(UsageCostRecordModel.run_id == run_id).order_by(UsageCostRecordModel.created_at, UsageCostRecordModel.id)))
        usage = {item.invocation_id: item for item in usage_records}
        artifacts = list(session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id).order_by(ArtifactMetadataModel.created_at, ArtifactMetadataModel.id)))
        snapshot = self._latest(session, SourceSnapshotModel, run_id, SourceSnapshotModel.updated_at.desc(), SourceSnapshotModel.created_at.desc(), SourceSnapshotModel.id.desc())
        g02 = self._latest(session, G02ApprovalModel, run_id, G02ApprovalModel.state_version.desc(), G02ApprovalModel.updated_at.desc(), G02ApprovalModel.id.desc())
        execution_profile = self._latest(session, ExecutionProfileModel, run_id, ExecutionProfileModel.updated_at.desc(), ExecutionProfileModel.id.desc())
        analysis = self._latest(session, AnalysisMetadataModel, run_id, AnalysisMetadataModel.state_version.desc(), AnalysisMetadataModel.updated_at.desc(), AnalysisMetadataModel.id.desc())
        compatibility = self._latest(session, CompatibilityResolutionModel, run_id, CompatibilityResolutionModel.state_version.desc(), CompatibilityResolutionModel.updated_at.desc(), CompatibilityResolutionModel.id.desc())
        g04 = self._latest(session, G04ApprovalModel, run_id, G04ApprovalModel.state_version.desc(), G04ApprovalModel.updated_at.desc(), G04ApprovalModel.id.desc())
        g05 = self._latest(session, G05ApprovalModel, run_id, G05ApprovalModel.state_version.desc(), G05ApprovalModel.updated_at.desc(), G05ApprovalModel.id.desc())
        planning_review = self._latest(session, PlanningReviewModel, run_id, PlanningReviewModel.state_version.desc(), PlanningReviewModel.updated_at.desc(), PlanningReviewModel.id.desc())
        g06 = self._latest(session, G06ApprovalModel, run_id, G06ApprovalModel.state_version.desc(), G06ApprovalModel.updated_at.desc(), G06ApprovalModel.id.desc())
        repairs = list(session.scalars(select(RepairAttemptModel).where(RepairAttemptModel.run_id == run_id).order_by(RepairAttemptModel.attempt_number.desc(), RepairAttemptModel.created_at.desc(), RepairAttemptModel.id.desc())))

        terminal = str(run.status).upper() in {"COMPLETED", "CANCELLED", "FAILED", "TIMED_OUT", "WORKER_LOST", "ORPHANED", "CLEANUP_FAILED"}
        current_stage = next((item for item in reversed(stages) if str(item.status).upper() not in {"PASSED", "COMPLETED", "CANCELLED"}), None)
        if current_stage is None and stages:
            current_stage = stages[-1]
        current_step = next((item for item in reversed(steps) if str(item.status).upper() not in {"PASSED", "COMPLETED", "CANCELLED"}), None)
        if current_step is None and current_stage:
            current_step = next((item for item in reversed(steps) if item.stage_id == current_stage.id), None)
        current_event = events[-1] if events else None
        end = run.updated_at if terminal else (current_event.occurred_at if current_event else None)
        duration = _seconds(run.created_at, end)

        counts: dict[str, int] = {}
        for item in commands:
            counts[item.status] = counts.get(item.status, 0) + 1
        completed_usage = [item for item in usage_records if item.invocation_id in {invocation.id for invocation in invocations if invocation.status == "completed"}]
        stats = AssistantOperationalStatisticsDto(
            run_start_timestamp=run.created_at, recorded_workflow_duration_seconds=duration,
            current_active_run_age_seconds=None if terminal else _seconds(run.created_at, datetime.now(UTC)),
            stage_durations_seconds={item.id: value for item in stages if (value := _seconds(item.started_at, item.completed_at)) is not None} or None,
            command_totals_by_status=counts or None, successful_commands=sum(v for k, v in counts.items() if k in {"succeeded", "completed"}) or (0 if commands else None),
            failed_commands=sum(v for k, v in counts.items() if k in {"failed", "timed_out", "rejected", "interrupted"}) or (0 if commands else None),
            relevant_command_ids=[item.id for item in commands], llm_calls_by_role={role: sum(1 for invocation in invocations if invocation.role == role) for role in {invocation.role for invocation in invocations}} or None,
            input_tokens=sum(item.input_tokens for item in completed_usage) if completed_usage else None,
            output_tokens=sum(item.output_tokens for item in completed_usage) if completed_usage else None,
            total_tokens=sum(item.total_tokens for item in completed_usage) if completed_usage else None,
            input_cost_usd=sum(item.input_cost_usd for item in completed_usage) if completed_usage else None,
            output_cost_usd=sum(item.output_cost_usd for item in completed_usage) if completed_usage else None,
            total_cost_usd=sum(item.total_cost_usd for item in completed_usage) if completed_usage else None,
        )

        phase_labels = {"PREFLIGHT_SNAPSHOT": "Preflight Snapshot", "DISCOVERY_BASELINE": "Baseline", "FEASIBILITY_PLANNING": "Planning", "STAGED_MIGRATION": "Transformation", "FINAL_ASSURANCE": "Validation", "DELIVERY_REPORTING": "Completion"}
        completed_work = [item.id for item in stages if str(item.status).upper() in {"PASSED", "COMPLETED"}]
        if snapshot is not None and snapshot.status == "created": completed_work.append("Immutable source snapshot")
        if g02 is not None and str(g02.status).lower() == "approved": completed_work.append("G02 approval")
        if analysis is not None and analysis.status == "completed": completed_work.append("Analysis package")
        if compatibility is not None and compatibility.status in {"feasible", "feasible_with_warnings"}: completed_work.append("Compatibility package")
        if planning_review is not None and planning_review.status in {"accepted", "approved", "completed"}: completed_work.append("Planning review")
        if g06 is not None and g06.status in {"approved", "approved_with_comment"}: completed_work.append("G06 approval")
        completed_work = list(dict.fromkeys(completed_work))

        gate_owner = next((item for item in (g06, g05, g04, g02) if item is not None and str(item.status).lower() not in {"stale", "cancelled"}), None)
        gate_id = getattr(gate_owner, "gate_id", None)
        gate_state = getattr(gate_owner, "status", None)
        blocker = failure = failure_classification = blocker_phase = waiting = None
        profile_blockers = list(execution_profile.blockers or []) if execution_profile else []
        if execution_profile is not None and execution_profile.status == "blocked":
            blocker = profile_blockers[0] if profile_blockers else "NO_COMPATIBLE_RUNTIME_PROFILE"
            failure = "Runtime resolution was attempted and completed with a blocked result."
            failure_classification, blocker_phase = "runtime_profile_unavailable", "runtime_resolution"
        elif compatibility is not None and compatibility.status == "blocked":
            blocker = (compatibility.blockers or ["compatibility_unavailable"])[0]
            failure, failure_classification, blocker_phase = blocker, "compatibility_unavailable", "compatibility"
        failed_command = next((item for item in reversed(commands) if str(item.status).lower() in {"failed", "timed_out", "rejected", "interrupted"}), None)
        if failed_command is not None and blocker is None:
            failure, failure_classification, blocker_phase = failed_command.failure_message or failed_command.failure_code or "command_failed", failed_command.failure_code or "command_failed", failed_command.stage_id
        elif analysis is not None and analysis.status in {"failed", "blocked"} and blocker is None:
            failure, failure_classification, blocker_phase = analysis.error_code or "analysis_failed", analysis.failure_subtype or "analysis_failed", "analysis"
        if gate_owner is not None and str(gate_state).lower() in {"pending", "waiting", "in_review"}:
            waiting = f"Human decision required for {gate_id}."

        remaining: list[str] = []
        if waiting: remaining.append(f"Review {gate_id}")
        if blocker_phase == "runtime_resolution": remaining.append("Resolve runtime profile and retry")
        elif blocker_phase: remaining.append(f"Resolve {blocker_phase}")
        if failed_command is not None and blocker is None: remaining.append("Repair or retry failed command")
        repair_status = repairs[0].status if repairs else run.repair_status
        if str(repair_status).lower() in {"pending", "in_progress", "running", "waiting_approval"}:
            remaining.append("Complete governed repair")
        if not terminal and not remaining and not completed_work: remaining.append("Reach the next governed workflow owner")
        remaining = [item for item in dict.fromkeys(remaining) if item not in completed_work]

        proposals = build_next_step_proposals(run_id=run_id, gate_id=gate_id, gate_state=gate_state, blocker_phase=blocker_phase, terminal=terminal, waiting_reason=waiting, command_failed=failed_command is not None)
        latest_command = commands[-1] if commands else None
        records_present = bool(usage_records)
        referenced = [aid for event in events for aid in (event.payload.get("artifact_ids", []) if isinstance(event.payload.get("artifact_ids", []), list) else [])]
        if snapshot and snapshot.status == "created": referenced.extend(snapshot.artifact_ids or [])
        if g02 and g02.status == "approved": referenced.extend(g02.artifact_ids or [])
        if execution_profile: referenced.extend(execution_profile.artifact_ids or [])
        order = {item: index for index, item in enumerate(referenced)}
        selected = [item for item in artifacts if item.immutable and (item.id in order or item.id.removeprefix("metadata-") in order)]
        selected.sort(key=lambda item: (order.get(item.id, order.get(item.id.removeprefix("metadata-"), 10**9)), item.created_at, item.id))
        evidence = [AssistantEvidenceReferenceDto(artifact_id=item.id, label=item.relative_path, checksum=item.checksum, run_id=item.run_id, stage_id=item.stage_id, category=item.artifact_type, lineage=item.owner_reference, immutable=item.immutable) for item in selected]
        return AssistantWorkflowProjectionDto(
            application_name=_value("Angular migration"), run_id=run_id, current_angular_version=_value(run.source_angular_version), target_angular_version=_value(run.target_angular_version),
            node_execution_profile=_value((run.workspace_aliases or {}).get("NODE_EXECUTION_PROFILE")), package_manager=_value((run.run_policy_snapshot or {}).get("package_manager")), migration_route=_value((run.target_policy_snapshot or {}).get("migration_route")),
            stage_workspace_reference=_value((run.workspace_aliases or {}).get("STAGE_SANDBOX")), source_fingerprint=_value((run.run_policy_snapshot or {}).get("source_fingerprint")), stage_fingerprint=_value(None, supported=False),
            phase=_value(phase_labels.get(run.run_phase, run.run_phase)), stage=_value(current_stage.id if current_stage else None, reason="not_reached"), step=_value(current_step.name if current_step else None, reason="not_reached"),
            gate=_value(gate_id, reason="not_reached"), current_gate_id=_value(gate_id, reason="not_reached"), gate_state=_value(gate_state, reason="not_reached"), status=_value(run.status), completed_work=completed_work, remaining_work=remaining,
            blocker=_value(blocker, reason="not_reached" if blocker is None and not terminal else "owner_not_available"), waiting_reason=_value(waiting), failure_reason=_value(failure), failure_classification=_value(failure_classification), repair_state=_value(repair_status),
            next_permitted_action=_value(proposals[0]["label"] if proposals else None, reason="not_applicable" if terminal else "owner_not_available"), next_step_proposals=proposals,
            latest_command_result=_value({"command_key": latest_command.command_id or latest_command.executable, "status": latest_command.status, "exit_code": latest_command.exit_code, "failure_code": latest_command.failure_code, "started_at": latest_command.started_at, "completed_at": latest_command.finished_at, "correlation_id": latest_command.correlation_id} if latest_command else None),
            semantic_state_version=run.state_version, workflow_state_version=run.state_version, operational_event_sequence=current_event.sequence if current_event else 0, phase_duration_seconds=_value(duration), stage_duration_seconds=_value(_seconds(current_stage.started_at, current_stage.completed_at) if current_stage else None, reason="not_reached"), pricing_availability=_value("available" if records_present else None, reason="not_configured"), operational_statistics=stats, evidence_references=evidence,
        )
