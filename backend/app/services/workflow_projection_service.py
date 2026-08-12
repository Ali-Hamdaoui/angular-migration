"""Shared, read-only semantic projection for cross-phase Assistant consumers."""

from __future__ import annotations

import re
import json
from pathlib import Path

from sqlalchemy import select

from app.domain.contracts import (
    AssistantEvidenceReferenceDto,
    AssistantOperationalStatisticsDto,
    AssistantWorkflowProjectionDto,
    ProjectionValue,
    RunTimingDto,
)
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    ExecutionProfileModel,
    G02ApprovalModel,
    MigrationRunModel,
    MigrationStageModel,
    RepairAttemptModel,
    StageStepModel,
    SourceSnapshotModel,
    WorkflowEventModel,
    TransformationContinuationModel,
)
from app.services.assistant_capabilities import build_next_step_proposals
from app.services.llm_evidence_application_service import aggregate_run_llm_usage
from app.services.run_timing_service import RunTimingService
from app.artifact_store import ArtifactStoreError, LocalFilesystemArtifactStore

_PHASES = ["Preflight Snapshot", "Baseline", "Planning", "Transformation", "Validation", "Completion"]
_PHASE_LABELS = {
    "PREFLIGHT_SNAPSHOT": "Preflight Snapshot",
    "DISCOVERY_BASELINE": "Baseline",
    "FEASIBILITY_PLANNING": "Planning",
    "STAGED_MIGRATION": "Transformation",
    "FINAL_ASSURANCE": "Validation",
    "DELIVERY_REPORTING": "Completion",
}
_GATE_EVENT = re.compile(r"^(G\d{2})_(CREATED|APPROVED|REJECTED)$")


def _value(value, *, supported: bool = True) -> ProjectionValue:
    if not supported:
        return ProjectionValue(value=None, availability="unsupported")
    if value is None or value == "":
        return ProjectionValue(value=None, availability="unavailable")
    return ProjectionValue(value=value, availability="known")


def _application_name(source_path: str | None) -> str | None:
    if not source_path:
        return None
    parts = [part for part in re.split(r"[\\/]", source_path.rstrip("\\/")) if part]
    return parts[-1] if parts else None


def _angular_major(value: object) -> str | None:
    match = re.search(r"\d+", str(value or ""))
    return match.group(0) if match else None


def _migration_route(run: MigrationRunModel, stages: list[MigrationStageModel]) -> str | None:
    configured = (run.target_policy_snapshot or {}).get("migration_route")
    if configured:
        return str(configured)
    stage_routes = [
        str(value)
        for stage in stages
        for value in ((getattr(stage, "target_version", None),) if getattr(stage, "target_version", None) else ())
    ]
    if stage_routes:
        source = _angular_major(run.source_angular_version or run.source_version_detected)
        majors = [major for value in stage_routes if (major := _angular_major(value))]
        if source and majors:
            return "→".join(dict.fromkeys([source, *majors]))
    source = _angular_major(run.source_angular_version or run.source_version_detected)
    target = _angular_major(run.target_angular_version)
    return f"{source}→{target}" if source and target else None


def _event_detail(event: WorkflowEventModel | None) -> str | None:
    if event is None:
        return None
    payload = event.payload or {}
    return next(
        (
            str(value)
            for value in (
                payload.get("blocker"),
                payload.get("failure_reason"),
                payload.get("error_code"),
                payload.get("reason_code"),
                payload.get("error"),
                event.reason,
            )
            if value
        ),
        None,
    )


def _command_stdout(session, run: MigrationRunModel, command: CommandExecutionModel | None) -> str:
    """Read immutable command output for small terminal fact extraction."""
    if command is None or not run.artifact_root:
        return ""
    try:
        store = LocalFilesystemArtifactStore(Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root))
        content: list[str] = []
        for artifact_id in (command.stdout_artifact_id, command.stderr_artifact_id):
            if not artifact_id:
                continue
            metadata = session.get(ArtifactMetadataModel, f"metadata-{artifact_id}") or session.get(ArtifactMetadataModel, artifact_id)
            if metadata is not None:
                content.append(store.read_artifact(run.id, metadata.relative_path).content)
        return "\n".join(content)
    except (ArtifactStoreError, OSError, ValueError):
        return ""


def _artifact_json(run: MigrationRunModel, metadata: ArtifactMetadataModel | None) -> dict[str, object]:
    if metadata is None or not run.artifact_root:
        return {}
    try:
        store = LocalFilesystemArtifactStore(Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root))
        payload = json.loads(store.read_artifact(run.id, metadata.relative_path).content)
        return payload if isinstance(payload, dict) else {}
    except (ArtifactStoreError, OSError, TypeError, ValueError):
        return {}


def _installed_angular_version(session, run: MigrationRunModel, commands: list[CommandExecutionModel]) -> str | None:
    command = next(
        (item for item in reversed(commands) if item.command_id == "angular-version-verify" and item.status == "succeeded"),
        None,
    )
    output = _command_stdout(session, run, command)
    match = re.search(r"@angular/core[^\r\n]*?([0-9]+\.[0-9]+\.[0-9]+)", output)
    return match.group(1) if match else None


def _terminal_test_summary(session, run: MigrationRunModel, commands: list[CommandExecutionModel]) -> str | None:
    command = next(
        (item for item in reversed(commands) if item.command_id == "npm-script-test-ci" and item.status == "succeeded"),
        None,
    )
    output = _command_stdout(session, run, command)
    suites = re.search(r"Test Suites:\s*(\d+) passed", output)
    tests = re.search(r"Tests:\s*(\d+) passed", output)
    if not command:
        return None
    detail = []
    if suites:
        detail.append(f"{suites.group(1)} suites")
    if tests:
        detail.append(f"{tests.group(1)} tests")
    suffix = f" ({', '.join(detail)})" if detail else ""
    return f"Tests passed{suffix} [{command.id}]"


def _apply_timing_statistics(
    stats: AssistantOperationalStatisticsDto,
    timing: RunTimingDto,
    phase_durations: dict[str, float],
    stage_durations: dict[str, float],
) -> AssistantOperationalStatisticsDto:
    """Add timing-owned fields without changing usage-owned statistics."""
    return stats.model_copy(
        update={
            "run_start_timestamp": timing.started_at,
            "recorded_workflow_duration_seconds": timing.total_duration_seconds,
            "current_active_run_age_seconds": timing.total_duration_seconds if timing.total_measurement_status == "running" else None,
            "phase_durations_seconds": phase_durations or None,
            "stage_durations_seconds": stage_durations or None,
        }
    )


class WorkflowProjectionService:
    """Compose one query-ready projection from persisted run records and events."""

    def build(self, session, run_id: str) -> AssistantWorkflowProjectionDto:
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise ValueError("Migration run does not exist.")
        stages = list(session.scalars(select(MigrationStageModel).where(MigrationStageModel.run_id == run_id).order_by(MigrationStageModel.stage_order)))
        steps = list(session.scalars(select(StageStepModel).where(StageStepModel.run_id == run_id).order_by(StageStepModel.id)))
        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id).order_by(WorkflowEventModel.sequence)))
        commands = list(session.scalars(select(CommandExecutionModel).where(CommandExecutionModel.run_id == run_id).order_by(CommandExecutionModel.requested_at, CommandExecutionModel.id)))
        llm_usage = aggregate_run_llm_usage(session, run_id)
        artifacts = list(session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id).order_by(ArtifactMetadataModel.created_at, ArtifactMetadataModel.id)))
        def latest_artifact(predicate):
            return next((item for item in reversed(artifacts) if item.immutable and predicate(item.relative_path.replace("\\", "/"))), None)

        dependency_closure_artifact = latest_artifact(lambda path: "/dependency-closure/" in path and path.endswith(".json"))
        version_verification_artifact = latest_artifact(lambda path: path.endswith("/transformation/version-verification.json"))
        validation_summary_artifact = latest_artifact(lambda path: path.endswith("/validation/summary.json"))
        seal_artifact = latest_artifact(lambda path: path.endswith("/seal/seal.json"))
        snapshot = session.scalar(select(SourceSnapshotModel).where(SourceSnapshotModel.run_id == run_id).order_by(SourceSnapshotModel.created_at.desc()))
        g02 = session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == run_id).order_by(G02ApprovalModel.updated_at.desc()))
        execution_profile = session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.updated_at.desc()))
        continuation = session.scalar(select(TransformationContinuationModel).where(TransformationContinuationModel.run_id == run_id).order_by(TransformationContinuationModel.updated_at.desc()))
        repair = session.scalar(select(RepairAttemptModel).where(RepairAttemptModel.run_id == run_id).order_by(RepairAttemptModel.attempt_number.desc()))
        timing = RunTimingService().build(session, run_id)

        current_stage = next((item for item in reversed(stages) if item.status not in {"PASSED", "COMPLETED", "CANCELLED"}), None) or (stages[-1] if stages else None)
        current_step = next((item for item in reversed(steps) if item.status not in {"PASSED", "COMPLETED", "CANCELLED"}), None)
        current_event = events[-1] if events else None
        terminal = str(run.status).upper() in {"COMPLETED", "CANCELLED", "FAILED", "TIMED_OUT", "WORKER_LOST", "ORPHANED", "CLEANUP_FAILED"}
        sealed = terminal and bool(stages) and all(stage.status == "sealed" for stage in stages)
        phase_durations = {item.key: item.duration_seconds for item in timing.phases if item.duration_seconds is not None}
        stage_durations = {item.key: item.duration_seconds for item in timing.stages if item.duration_seconds is not None}
        current_phase_duration = phase_durations.get(str(run.run_phase))
        current_stage_duration = stage_durations.get(current_stage.id) if current_stage else None

        counts: dict[str, int] = {}
        for command in commands:
            counts[command.status] = counts.get(command.status, 0) + 1
        role_counts = {item.key: item.calls for item in llm_usage.by_role}
        usage_available = llm_usage.usage_recorded_calls > 0
        stats = AssistantOperationalStatisticsDto(
            command_totals_by_status=counts or None,
            successful_commands=sum(value for key, value in counts.items() if key in {"succeeded", "completed"}) if commands else None,
            failed_commands=sum(value for key, value in counts.items() if key in {"failed", "timed_out", "rejected", "interrupted"}) if commands else None,
            relevant_command_ids=[item.id for item in commands],
            llm_calls_by_role=role_counts or None,
            input_tokens=llm_usage.input_tokens if usage_available else None,
            output_tokens=llm_usage.output_tokens if usage_available else None,
            total_tokens=llm_usage.total_tokens if usage_available else None,
            input_cost_usd=llm_usage.input_cost_usd if usage_available else None,
            output_cost_usd=llm_usage.output_cost_usd if usage_available else None,
            total_cost_usd=llm_usage.total_cost_usd if usage_available else None,
        )
        stats = _apply_timing_statistics(stats, timing, phase_durations, stage_durations)

        referenced_artifact_ids = [artifact_id for event in events for artifact_id in (event.payload.get("artifact_ids", []) if isinstance(event.payload.get("artifact_ids", []), list) else [])]
        if snapshot is not None and snapshot.status == "created":
            referenced_artifact_ids.extend(snapshot.artifact_ids or [])
        if g02 is not None and g02.status == "approved":
            referenced_artifact_ids.extend(g02.artifact_ids or [])
        if execution_profile is not None:
            referenced_artifact_ids.extend(execution_profile.artifact_ids or [])
        referenced_order = {artifact_id: index for index, artifact_id in enumerate(referenced_artifact_ids)}
        selected_artifacts = [item for item in artifacts if item.immutable and {item.id, item.id.removeprefix("metadata-")} & referenced_order.keys()]
        selected_artifacts.sort(key=lambda item: referenced_order.get(item.id, referenced_order.get(item.id.removeprefix("metadata-"), len(referenced_order))))
        if sealed:
            final_command_ids = {
                item.id
                for command_key in ("angular-version-verify", "npm-ci-final", "npm-script-build-production", "npm-script-test-ci")
                for item in [next((command for command in reversed(commands) if command.command_id == command_key and command.status == "succeeded"), None)]
                if item is not None
            }
            authoritative_documents = {
                item.id for item in (
                    dependency_closure_artifact,
                    version_verification_artifact,
                    validation_summary_artifact,
                    seal_artifact,
                ) if item is not None
            }
            selected_artifacts = [
                item for item in artifacts
                if item.immutable and (
                    item.id in authoritative_documents
                    or (
                        item.execution_id in final_command_ids
                        and item.relative_path.replace("\\", "/").endswith(".result.json")
                    )
                )
            ]
        evidence = [AssistantEvidenceReferenceDto(artifact_id=item.id, label=item.relative_path, checksum=item.checksum, run_id=item.run_id, stage_id=item.stage_id, category=item.artifact_type, lineage=item.owner_reference, immutable=item.immutable) for item in selected_artifacts]

        phase = "Completion" if sealed else ("Transformation" if continuation is not None and continuation.status not in {"completed", "cancelled"} else _PHASE_LABELS.get(run.run_phase, run.run_phase))
        completed_work = [stage.id for stage in stages if stage.status in {"PASSED", "COMPLETED"}]
        if snapshot is not None and snapshot.status == "created":
            completed_work.append("Immutable source snapshot")
        if g02 is not None and g02.status == "approved":
            completed_work.append("G02 approval")
        for event in events:
            if event.event_type == "SNAPSHOT_CREATED" or event.event_type.endswith(("_COMPLETED", "_SUCCEEDED", "_APPROVED", "_VERIFIED")):
                completed_work.append(event.event_type.replace("_", " ").title())
        completed_work = list(dict.fromkeys(completed_work))
        installed_version = (
            _installed_angular_version(session, run, commands)
            or (current_stage.target_angular_version if current_stage is not None else None)
            or run.target_version_resolved
        ) if sealed else None
        dependency_closure_payload = _artifact_json(run, dependency_closure_artifact) if sealed else {}
        dependency_closure_report = dependency_closure_payload.get("report", {})
        dependency_closure_passed = (
            isinstance(dependency_closure_report, dict)
            and dependency_closure_report.get("ok") is True
            and not dependency_closure_report.get("violations", [])
        )
        seal_payload = _artifact_json(run, seal_artifact) if sealed else {}
        validation_payload = _artifact_json(run, validation_summary_artifact) if sealed else {}
        stage_fingerprint = seal_payload.get("output_fingerprint") or validation_payload.get("workspace_fingerprint")
        if sealed:
            final_commands = {
                key: next((item for item in reversed(commands) if item.command_id == key and item.status == "succeeded"), None)
                for key in ("npm-ci-final", "npm-script-build-production")
            }
            test_summary = _terminal_test_summary(session, run, commands)
            completed_work = [
                f"Angular migrated from {run.source_angular_version or run.source_version_detected or 'unknown'} to {installed_version or (current_stage.target_angular_version if current_stage else None) or run.target_angular_version or 'unknown'}",
                f"Governed dependency and test-compatibility repairs applied ({repair.attempt_number if repair is not None else 0} attempts)",
                *( ["Dependency closure passed"] if dependency_closure_passed else [] ),
                *( [f"Final npm install passed [{final_commands['npm-ci-final'].id}]"] if final_commands["npm-ci-final"] else [] ),
                *( [f"Production build passed [{final_commands['npm-script-build-production'].id}]"] if final_commands["npm-script-build-production"] else [] ),
                *( [test_summary] if test_summary else [] ),
                f"Stage {current_stage.id if current_stage else 'unknown'} sealed",
            ]
        try:
            remaining_work = _PHASES[_PHASES.index(phase) + 1 :]
        except ValueError:
            remaining_work = []
        if "Baseline" in remaining_work and any(
            event.event_type in {"BASELINE_QUALIFIED", "G03_CREATED", "G03_APPROVED"}
            for event in events
        ):
            remaining_work.remove("Baseline")
        if repair is not None and repair.status not in {"completed", "validated", "rejected", "cancelled"}:
            remaining_work.insert(0, "Complete governed repair")
        if sealed:
            remaining_work = []

        latest_gate = next((match for event in reversed(events) if (match := _GATE_EVENT.match(event.event_type))), None)
        if latest_gate:
            gate_name, gate_state = latest_gate.groups()
            gate_pending = gate_state == "CREATED"
            gate_value = f"{gate_name} {'pending' if gate_pending else gate_state.lower()}"
        else:
            gate_value = run.approval_status if run.approval_status not in {None, "not_required"} else None
            gate_pending = str(gate_value).lower() in {"pending", "waiting_approval"}

        profile_blockers = list(execution_profile.blockers or []) if execution_profile is not None else []
        profile_guidance = list(execution_profile.guidance or []) if execution_profile is not None else []
        failed_event = next((event for event in reversed(events) if event.event_type.endswith(("_FAILED", "_BLOCKED", "_REJECTED"))), None)
        if sealed:
            failed_event = None
        if failed_event is not None:
            blocked_gate = re.search(r"(G\d{2})_APPROVAL_REQUIRED", _event_detail(failed_event) or "")
            if blocked_gate and any(
                event.sequence > failed_event.sequence and event.event_type == f"{blocked_gate.group(1)}_APPROVED"
                for event in events
            ):
                failed_event = None
        blocker_value = profile_blockers[0] if execution_profile is not None and execution_profile.status == "blocked" and profile_blockers else _event_detail(failed_event)
        failure_value = _event_detail(failed_event)
        if continuation is not None and continuation.last_error_code and continuation.status not in {"completed", "cancelled"}:
            blocker_value = continuation.last_error_code
            failure_value = continuation.last_error_message or continuation.last_error_code
        waiting_reason = f"Human decision required for {gate_value.split()[0]}." if gate_pending and gate_value else None
        if gate_pending and gate_value:
            next_action = f"Review and decide {gate_value.split()[0]} through the governed cockpit control."
        elif blocker_value and profile_guidance:
            next_action = f"{profile_guidance[0]} Retry runtime-profile resolution."
        elif terminal:
            next_action = "Review final evidence and reporting."
        elif phase == "Preflight Snapshot":
            next_action = "Continue the governed source-intake and baseline workflow."
        else:
            next_action = f"Continue the governed {phase.lower()} workflow."

        stage_value = current_stage.id if current_stage else (gate_value or phase)
        step_value = continuation.current_node if continuation is not None and continuation.status not in {"completed", "cancelled"} else (current_step.name if current_step else (current_event.event_type if current_event else run.phase_status))
        gate_id = gate_value.split()[0] if gate_value and gate_value.split()[0].startswith("G") else None
        gate_state = gate_value.split()[1] if gate_value and len(gate_value.split()) > 1 else ("pending" if gate_pending else gate_value)
        failed_command = next((item for item in reversed(commands) if str(item.status).lower() in {"failed", "timed_out", "rejected", "interrupted"}), None)
        blocker_phase = "runtime_resolution" if execution_profile is not None and execution_profile.status == "blocked" else (phase.lower().replace(" ", "_") if blocker_value else None)
        proposals = build_next_step_proposals(run_id=run_id, gate_id=gate_id, gate_state=gate_state, blocker_phase=blocker_phase, terminal=terminal, waiting_reason=waiting_reason, command_failed=failed_command is not None)
        failure_classification = None if sealed else ((repair.diagnosis if repair is not None else None) or (continuation.last_error_code if continuation is not None else None) or failure_value or blocker_value)
        latest_command = commands[-1] if commands else None
        return AssistantWorkflowProjectionDto(
            application_name=_value(_application_name(run.source_path)),
            run_id=run_id,
            current_angular_version=_value(
                installed_version
                or run.source_angular_version
                or run.source_version_detected
                or (execution_profile.source_angular_exact if execution_profile is not None else None)
            ),
            target_angular_version=_value(run.target_angular_version),
            node_execution_profile=_value((run.workspace_aliases or {}).get("NODE_EXECUTION_PROFILE")),
            package_manager=_value((run.run_policy_snapshot or {}).get("package_manager")),
            migration_route=_value(_migration_route(run, stages)),
            stage_workspace_reference=_value((run.workspace_aliases or {}).get("STAGE_SANDBOX")),
            source_fingerprint=_value((run.run_policy_snapshot or {}).get("source_fingerprint")),
            stage_fingerprint=_value(stage_fingerprint, supported=stage_fingerprint is not None),
            phase=_value(phase),
            stage=_value(stage_value),
            step=_value(step_value),
            gate=_value(gate_value),
            current_gate_id=_value(gate_id, supported=gate_id is not None),
            gate_state=_value(gate_state, supported=gate_state is not None),
            status=_value(continuation.status.upper() if continuation is not None and continuation.status not in {"completed", "cancelled"} else run.status),
            completed_work=completed_work,
            remaining_work=remaining_work,
            blocker=_value(blocker_value or "none"),
            waiting_reason=_value(waiting_reason),
            failure_reason=_value(failure_value),
            failure_classification=_value(failure_classification),
            repair_state=_value(
                (
                    f"attempt {repair.attempt_number}; reviewer accepted; waiting for G10 human approval"
                    if repair is not None and repair.status == "waiting_g10"
                    else repair.status if repair is not None else run.repair_status
                )
            ),
            next_permitted_action=_value(next_action),
            next_step_proposals=proposals,
            latest_command_result=_value({"command_key": latest_command.command_id or latest_command.executable, "status": latest_command.status, "exit_code": latest_command.exit_code, "failure_code": latest_command.failure_code, "started_at": latest_command.started_at, "completed_at": latest_command.finished_at, "correlation_id": latest_command.correlation_id} if latest_command else None, supported=latest_command is not None),
            semantic_state_version=run.state_version,
            operational_event_sequence=current_event.sequence if current_event else 0,
            phase_duration_seconds=_value(current_phase_duration, supported=current_phase_duration is not None),
            stage_duration_seconds=_value(current_stage_duration, supported=current_stage_duration is not None),
            pricing_availability=_value("available" if usage_available else None, supported=usage_available),
            workflow_state_version=run.state_version,
            operational_statistics=stats,
            evidence_references=evidence,
        )
