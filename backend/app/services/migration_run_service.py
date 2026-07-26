"""Authoritative creation and production handoff for migration runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from pathlib import Path

from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactRefDto, ArtifactType, CommandStatus, RunPhase, RunStatus, WorkflowEventDto, WorkflowEventType
from app.domain.preflight import PreflightSnapshot
from app.orchestration.source_intake import SourceIntakeGraph, default_source_intake_graph
from app.repositories.models import ActiveRunClaimModel, ArtifactMetadataModel, CommandExecutionModel, CompatibilityResolutionModel, DiscoveryEvidenceModel, MigrationRunModel, PathValidationModel, SourceIntakeJobModel, TargetReservationModel, WorkflowEventModel
from app.repositories.preflight_models import ApprovalGateModel, PreflightModel
from app.repositories.session import session_scope
from app.state.transition_service import StateTransitionService, StaleStateVersionError, TransitionError, TransitionRequest
from app.services.migration_workspace_layout_service import MigrationWorkspaceLayoutService, WorkspaceLayoutError


class MigrationRunError(ValueError):
    """Stable domain error raised when a run cannot be created or started."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CreateRunRequest:
    preflight_id: str
    input_checksum: str
    artifact_set_checksum: str
    idempotency_key: str
    actor: str
    client_constraints: dict[str, bool]
    pricing_snapshot: dict[str, str | float | int] | None = None


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str
    state_version: int
    event_sequence: int
    graph_thread_id: str
    idempotent_replay: bool = False
    artifacts: tuple[ArtifactRefDto, ...] = ()
    job_id: str | None = None


class MigrationRunService:
    """Own run lifecycle decisions; graph coordination remains an adapter."""

    _MUTATING_STATUSES = {
        RunStatus.CREATED.value, RunStatus.SOURCE_VALIDATION_RUNNING.value,
        RunStatus.SOURCE_VALIDATED.value, RunStatus.WORKSPACE_CLASSIFICATION_RUNNING.value,
        RunStatus.BASELINE_RUNNING.value, RunStatus.RUNNING.value, RunStatus.WAITING.value,
        RunStatus.CANCEL_REQUESTED.value, RunStatus.CANCELLING.value, RunStatus.RECOVERY_RUNNING.value,
    }
    _CANCELLABLE_STATUSES = {
        RunStatus.CREATED.value, RunStatus.SOURCE_VALIDATED.value, RunStatus.WAITING.value,
    }

    def __init__(self, settings, *, session_scope_factory=session_scope, graph: SourceIntakeGraph | None = None, now_provider=None) -> None:
        self._scope = session_scope_factory
        self._graph = graph or default_source_intake_graph(settings)
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._lease_seconds = settings.worker_lease_seconds
        self._settings = settings
        self._layout = MigrationWorkspaceLayoutService(platform_repository_root=settings.platform_repository_root)

    def create(self, request: CreateRunRequest) -> RunResult:
        with self._scope() as session:
            replay = session.scalar(select(WorkflowEventModel).where(WorkflowEventModel.idempotency_key == request.idempotency_key))
            if replay is not None:
                return self._result_from_event(session, replay, replay=True)
            snapshot, gate = self._approved_preflight(session, request)
            active = session.scalar(select(MigrationRunModel).where(MigrationRunModel.status.in_(self._MUTATING_STATUSES)).limit(1))
            if active is not None:
                raise MigrationRunError("ACTIVE_RUN_EXISTS", "Only one mutating migration run may be active.")
            preflight = session.get(PreflightModel, request.preflight_id)
            path_id = (preflight.binding or {}).get("path_validation_id") if preflight else None
            path = session.get(PathValidationModel, path_id)
            target_root = snapshot.get("resolved_output_root") or snapshot.get("target_output_path")
            stale_claim = session.scalar(select(ActiveRunClaimModel).where(ActiveRunClaimModel.target_output_path == target_root))
            if stale_claim is not None:
                stale_run = session.get(MigrationRunModel, stale_claim.run_id)
                if stale_run is not None and stale_run.status in self._MUTATING_STATUSES:
                    raise MigrationRunError("TARGET_OWNERSHIP_EXISTS", "The target is owned by an active migration run.")
                self._release_reservation_for_run(session, stale_run)
                session.delete(stale_claim)
                session.flush()
            reservation = session.get(TargetReservationModel, snapshot.get("target_reservation_id"))
            if reservation is None or reservation.target_path != target_root or reservation.status not in {"reserved", "eligible"} or self._utc(reservation.expires_at) <= self._utc(self._now()):
                raise MigrationRunError("TARGET_RESERVATION_INVALID", "The approved target reservation is missing, expired, or unavailable.")
            if path is None or reservation.validation_id != path.id:
                raise MigrationRunError("TARGET_RESERVATION_INVALID", "The approved target reservation is not bound to the path validation.")
            run_id = f"run-{uuid4().hex[:12]}"
            thread_id = f"source-intake-{run_id}"
            now = self._now()
            try:
                layout = self._layout.for_run(snapshot.get("resolved_output_root") or snapshot.get("target_output_path") or self._settings.artifact_root, run_id)
            except WorkspaceLayoutError as error:
                raise MigrationRunError("UNSAFE_WORKSPACE_LAYOUT", str(error)) from error
            artifacts = LocalFilesystemArtifactStore(layout.artifact_root, fixed_run_root=layout.artifact_root)
            run = MigrationRunModel(
                id=run_id, status=RunStatus.CREATED.value, run_phase=RunPhase.PREFLIGHT_SNAPSHOT.value,
                phase_status="running", approval_status="approved", repair_status="not_required", state_version=1,
                source_version_family=snapshot.get("source_version_family"), target_version_family=snapshot.get("target_angular_family"),
                source_angular_version=snapshot.get("source_angular_version"), target_angular_version=snapshot.get("target_angular_family"),
                preflight_id=request.preflight_id, source_path=snapshot.get("source_path"), target_output_path=str(layout.output_root),
                target_parent_path=snapshot.get("target_parent_path"), generated_output_name=snapshot.get("generated_output_name"),
                resolved_output_root=str(layout.output_root), run_root=str(layout.run_root), artifact_root=str(layout.artifact_root),
                log_root=str(layout.log_root), report_root=str(layout.report_root), temporary_root=str(layout.temporary_root),
                migrated_app_path=str(layout.migrated_app), workspace_aliases=layout.aliases(), output_layout_version=self._layout.layout_version,
                graph_thread_id=thread_id, client_constraints=request.client_constraints,
                target_policy_snapshot={"target_angular_family": snapshot.get("target_angular_family"), "migration_mode": snapshot.get("migration_mode")},
                run_policy_snapshot={"input_checksum": request.input_checksum, "artifact_set_checksum": request.artifact_set_checksum, "gate_version": gate.gate_version},
                pricing_snapshot=request.pricing_snapshot, actor=request.actor,
                created_at=now, updated_at=now,
            )
            session.add(run)
            session.flush()
            layout.metadata_root.mkdir(parents=True, exist_ok=True)
            for path in (layout.artifact_root, layout.log_root, layout.report_root, layout.temporary_root):
                path.mkdir(parents=True, exist_ok=True)
            artifacts.ensure_run_layout(run_id)
            target_path = str(layout.output_root)
            previous_claim = session.scalar(select(ActiveRunClaimModel).where(ActiveRunClaimModel.target_output_path == target_path))
            if previous_claim is not None:
                previous_run = session.get(MigrationRunModel, previous_claim.run_id)
                if previous_run is not None and previous_run.status in self._MUTATING_STATUSES:
                    raise MigrationRunError("TARGET_OWNERSHIP_EXISTS", "The target is owned by an active migration run.")
                self._release_reservation_for_run(session, previous_run)
                session.delete(previous_claim)
                # SQLite enforces the unique target claim immediately. Flush
                # the stale claim deletion before inserting its replacement.
                session.flush()
            reservation.status = "claimed"
            session.add(ActiveRunClaimModel(id=f"claim-{uuid4().hex[:12]}", run_id=run_id, target_output_path=target_path, lease_owner=request.actor, acquired_at=now, expires_at=now + timedelta(seconds=self._lease_seconds)))
            evidence = {
                "create_run_request.json": {"preflight_id": request.preflight_id, "input_checksum": request.input_checksum, "artifact_set_checksum": request.artifact_set_checksum, "idempotency_key": request.idempotency_key, "actor": request.actor},
                "client_constraints.json": request.client_constraints,
                "external_source_reference.json": {"source_path": run.source_path, "target_parent_path": run.target_parent_path},
                "output_layout.json": layout.aliases(),
                "workspace_alias_registry.json": layout.aliases(),
                "target_policy.json": run.target_policy_snapshot,
                "run_policy_snapshot.json": run.run_policy_snapshot,
                "run_initial_state.json": {"run_id": run_id, "status": run.status, "run_phase": run.run_phase, "state_version": run.state_version, "graph_thread_id": thread_id},
            }
            artifact_refs = tuple(self._write_evidence(artifacts, session, run_id, evidence, now, request.input_checksum))
            transition = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=1, idempotency_key=request.idempotency_key,
                event_type=WorkflowEventType.RUN_CREATED, actor=request.actor,
                reason="created from approved G01 preflight", payload={
                    "preflight_id": request.preflight_id, "input_checksum": request.input_checksum,
                    "artifact_set_checksum": request.artifact_set_checksum, "gate_id": gate.gate_id,
                    "graph_thread_id": thread_id, "source_path": snapshot.get("source_path"),
                    "target_parent_path": snapshot.get("target_parent_path"), "resolved_output_root": str(layout.output_root), "run_root": str(layout.run_root),
                    "client_constraints": json.dumps(request.client_constraints, sort_keys=True),
                    "policy_snapshot_checksum": self._checksum({"preflight": snapshot, "pricing": request.pricing_snapshot or {}}),
                }, occurred_at=now,
            ))
            return RunResult(run_id, run.status, transition.next_state_version, transition.event_sequence, thread_id, artifacts=artifact_refs)

    def renew_claim(self, *, run_id: str, actor: str = "worker") -> None:
        """Renew the authoritative run claim for a live workflow heartbeat."""
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            claim = session.scalar(select(ActiveRunClaimModel).where(ActiveRunClaimModel.run_id == run_id, ActiveRunClaimModel.target_output_path == (run.target_output_path if run else None)))
            if run is None or claim is None or run.status not in self._MUTATING_STATUSES:
                raise MigrationRunError("TARGET_RESERVATION_INVALID", "The run does not own a renewable target claim.")
            now = self._now()
            claim.lease_owner = actor
            claim.expires_at = now + timedelta(seconds=self._lease_seconds)

    def start(self, *, run_id: str, expected_state_version: int, idempotency_key: str, actor: str) -> RunResult:
        thread_id = ""
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise MigrationRunError("RUN_NOT_FOUND", "Migration run does not exist.")
            existing = session.scalar(select(WorkflowEventModel).where(
                WorkflowEventModel.run_id == run_id,
                WorkflowEventModel.idempotency_key.in_({idempotency_key, idempotency_key + ":accepted"}),
            ).order_by(WorkflowEventModel.sequence.desc()))
            if existing is not None:
                return self._result_from_event(session, existing, replay=True)
            if run.status != RunStatus.CREATED.value:
                raise MigrationRunError("RUN_NOT_STARTABLE", "Only a newly created run can be started.")
            self._validate_start_boundary(session, run)
            active_job = session.scalar(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == run_id, SourceIntakeJobModel.status.in_({"queued", "running", "waiting_g02", "waiting_runtime_selection"})))
            if active_job is not None:
                raise MigrationRunError("SOURCE_INTAKE_ALREADY_ACTIVE", "A source-intake job is already active for this run.")
            thread_id = self._thread_id(session, run_id)
            accepted = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=expected_state_version, idempotency_key=idempotency_key + ":accepted",
                event_type=WorkflowEventType.RUN_START_ACCEPTED, next_run_status=RunStatus.SOURCE_VALIDATION_RUNNING,
                actor=actor, reason="source-intake handoff accepted", payload={"graph_thread_id": thread_id}, occurred_at=self._now()))
            queued = SourceIntakeJobModel(
                id=f"intake-{uuid4().hex[:12]}", run_id=run_id, thread_id=thread_id,
                status="queued", actor=actor, idempotency_key=idempotency_key,
                attempt=1, queued_at=self._now(), state_version=accepted.next_state_version,
            )
            session.add(queued)
            StateTransitionService(session).append_audit_event(
                run_id=run_id, idempotency_key=f"{idempotency_key}:queued",
                event_type=WorkflowEventType.SOURCE_INTAKE_QUEUED, actor=actor,
                reason="source-intake work item persisted before dispatch",
                occurred_at=self._now(), payload={"job_id": queued.id, "graph_thread_id": thread_id},
            )
            session.flush()
            result = RunResult(run_id, accepted.status, accepted.next_state_version, accepted.event_sequence, thread_id, artifacts=tuple(self._artifacts_for_run(session, run_id)), job_id=queued.id)
        try:
            self._graph.start(run_id=run_id, thread_id=thread_id)
        except Exception as error:
            self._record_dispatch_failure(queued.id, run_id, idempotency_key, actor)
            raise MigrationRunError("GRAPH_HANDOFF_FAILED", "Source-intake handoff failed safely; the durable job records the failure.") from error
        return result

    def retry_source_intake(self, *, run_id: str, expected_state_version: int, idempotency_key: str, actor: str) -> RunResult:
        """Explicitly retry a failed source-intake attempt without erasing history."""
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise MigrationRunError("RUN_NOT_FOUND", "Migration run does not exist.")
            existing = session.scalar(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id, WorkflowEventModel.idempotency_key.in_({idempotency_key, idempotency_key + ":accepted"})).order_by(WorkflowEventModel.sequence.desc()))
            if existing is not None:
                return self._result_from_event(session, existing, replay=True)
            if run.status != RunStatus.FAILED.value:
                raise MigrationRunError("SOURCE_INTAKE_RETRY_NOT_ALLOWED", "Source-intake retry is only available after a failed run.")
            previous = session.scalar(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == run_id).order_by(SourceIntakeJobModel.attempt.desc()))
            retryable_codes = {"GRAPH_HANDOFF_FAILED", "SNAPSHOT_CREATION_FAILED", "SOURCE_CHANGED_DURING_COPY", "SNAPSHOT_LAYOUT_MISSING", "ExecutionProfileApplicationError"}
            if previous is None or previous.status != "failed" or previous.last_error_code not in retryable_codes:
                raise MigrationRunError("SOURCE_INTAKE_RETRY_NOT_ALLOWED", "The failed run does not have a retryable source-intake failure.")
            self._validate_start_boundary(session, run)
            if run.state_version != expected_state_version:
                raise MigrationRunError("STALE_STATE_VERSION", "The run state changed. Refresh the authoritative state and retry.")
            active_job = session.scalar(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == run_id, SourceIntakeJobModel.status.in_({"queued", "running", "waiting_g02", "waiting_runtime_selection"})))
            if active_job is not None:
                raise MigrationRunError("SOURCE_INTAKE_ALREADY_ACTIVE", "A source-intake job is already active for this run.")
            thread_id = previous.thread_id
            post_g03 = previous.last_error_code == "ExecutionProfileApplicationError" and session.scalar(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id, WorkflowEventModel.event_type == WorkflowEventType.G03_APPROVED.value)) is not None
            accepted = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=expected_state_version, idempotency_key=idempotency_key + ":accepted",
                event_type=WorkflowEventType.RUN_STATE_CHANGED, next_run_status=RunStatus.SOURCE_VALIDATION_RUNNING,
                actor=actor, reason="explicit source-intake retry accepted", payload={"previous_job_id": previous.id, "attempt": previous.attempt + 1}, occurred_at=self._now()))
            queued = SourceIntakeJobModel(
                id=f"intake-{uuid4().hex[:12]}", run_id=run_id, thread_id=thread_id,
                status="waiting_g03" if post_g03 else "queued", actor=actor, idempotency_key=idempotency_key,
                attempt=previous.attempt + 1, queued_at=self._now(), state_version=accepted.next_state_version,
            )
            session.add(queued)
            StateTransitionService(session).append_audit_event(
                run_id=run_id, idempotency_key=f"{idempotency_key}:queued", event_type=WorkflowEventType.SOURCE_INTAKE_QUEUED,
                actor=actor, reason="retry source-intake work item persisted before dispatch", occurred_at=self._now(),
                payload={"job_id": queued.id, "previous_job_id": previous.id, "attempt": queued.attempt},
            )
            session.flush()
            result = RunResult(run_id, accepted.status, accepted.next_state_version, accepted.event_sequence, thread_id, artifacts=tuple(self._artifacts_for_run(session, run_id)), job_id=queued.id)
        try:
            self._graph.start(run_id=run_id, thread_id=thread_id)
        except Exception as error:
            self._record_dispatch_failure(queued.id, run_id, idempotency_key, actor)
            raise MigrationRunError("GRAPH_HANDOFF_FAILED", "Source-intake retry handoff failed safely; the new attempt records the failure.") from error
        return result

    def _record_dispatch_failure(self, job_id: str, run_id: str, idempotency_key: str, actor: str) -> None:
        with self._scope() as failure_session:
            job = failure_session.get(SourceIntakeJobModel, job_id)
            run = failure_session.get(MigrationRunModel, run_id)
            if job is not None:
                job.status = "failed"
                job.finished_at = self._now()
                job.last_error_code = "GRAPH_HANDOFF_FAILED"
                job.last_error_message = "Source-intake worker dispatch failed."
            if run is not None:
                StateTransitionService(failure_session).apply_transition(TransitionRequest(
                    run_id=run_id, idempotency_key=f"{idempotency_key}:dispatch-failed", expected_state_version=run.state_version,
                    event_type=WorkflowEventType.SOURCE_INTAKE_FAILED, actor=actor, next_run_status=RunStatus.FAILED,
                    reason="source-intake worker dispatch failed", occurred_at=self._now(),
                    payload={"job_id": job_id, "error_code": "GRAPH_HANDOFF_FAILED"},
                ))

    def _validate_start_boundary(self, session, run: MigrationRunModel) -> None:
        """Revalidate G01 and ownership immediately before durable dispatch."""
        preflight = session.get(PreflightModel, run.preflight_id) if run.preflight_id else None
        gate = session.scalar(select(ApprovalGateModel).where(ApprovalGateModel.preflight_id == run.preflight_id, ApprovalGateModel.gate_id == "G01")) if run.preflight_id else None
        if preflight is None or gate is None or gate.status not in {"approved", "approved_with_comment"}:
            raise MigrationRunError("G01_NOT_APPROVED", "Start requires a currently approved G01 gate.")
        try:
            snapshot = PreflightSnapshot.model_validate(preflight.snapshot)
        except Exception as error:
            raise MigrationRunError("G01_EVIDENCE_INVALID", "The approved G01 snapshot could not be revalidated.") from error
        if snapshot.source_path != run.source_path or snapshot.target_output_path != run.target_output_path:
            raise MigrationRunError("G01_BOUNDARY_CHANGED", "The approved source or target boundary no longer matches the run.")
        claim = session.scalar(select(ActiveRunClaimModel).where(ActiveRunClaimModel.run_id == run.id, ActiveRunClaimModel.target_output_path == run.target_output_path))
        if claim is None or self._utc(claim.expires_at) <= self._utc(self._now()):
            raise MigrationRunError("TARGET_RESERVATION_INVALID", "The run no longer owns a live target reservation.")
        if snapshot.target_reservation_id:
            reservation = session.get(TargetReservationModel, snapshot.target_reservation_id)
            if reservation is None or reservation.target_path != run.target_output_path or reservation.status not in {"claimed", "consumed"}:
                raise MigrationRunError("TARGET_RESERVATION_INVALID", "The transferred target reservation is missing or does not match the run boundary.")

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    def cancel(self, *, run_id: str, expected_state_version: int, idempotency_key: str, actor: str) -> RunResult:
        """Cancel a quiescent run and atomically release its active-run claim.

        Evidence and the external run directory are intentionally retained for
        auditability. A run with a live command must be cancelled through that
        command's cancellation endpoint before its ownership can be released.
        """
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise MigrationRunError("RUN_NOT_FOUND", "Migration run does not exist.")
            existing = session.scalar(select(WorkflowEventModel).where(
                WorkflowEventModel.run_id == run_id,
                WorkflowEventModel.idempotency_key == idempotency_key,
            ))
            if existing is not None:
                return self._result_from_event(session, existing, replay=True)
            if run.status not in self._CANCELLABLE_STATUSES:
                raise MigrationRunError(
                    "RUN_NOT_CANCELLABLE",
                    "The run can only be cancelled at a safe checkpoint. Cancel any active command or wait for the current operation to finish.",
                )
            active_command = session.scalar(select(CommandExecutionModel).where(
                CommandExecutionModel.run_id == run_id,
                CommandExecutionModel.status.in_({
                    CommandStatus.QUEUED.value, CommandStatus.PENDING.value, CommandStatus.RUNNING.value,
                }),
            ).limit(1))
            if active_command is not None:
                raise MigrationRunError(
                    "RUN_CANCELLATION_BLOCKED",
                    "Cancel the active command before cancelling the migration run.",
                )
            try:
                transition = StateTransitionService(session).apply_transition(TransitionRequest(
                    run_id=run_id, expected_state_version=expected_state_version,
                    idempotency_key=idempotency_key, event_type=WorkflowEventType.RUN_CANCELLED,
                    next_run_status=RunStatus.CANCELLED, actor=actor,
                    reason="operator cancelled run; evidence retained and ownership released",
                    payload={"claim_released": "true"}, occurred_at=self._now(),
                ))
            except StaleStateVersionError as error:
                raise MigrationRunError("STALE_STATE_VERSION", "The run changed. Refresh its authoritative state and retry.") from error
            except TransitionError as error:
                raise MigrationRunError("RUN_CANCELLATION_FAILED", "The migration run could not be cancelled safely.") from error
            claims = list(session.scalars(select(ActiveRunClaimModel).where(ActiveRunClaimModel.run_id == run_id)))
            for claim in claims:
                self._release_reservation_for_run(session, run)
                session.delete(claim)
            session.flush()
            return RunResult(
                run_id, transition.status, transition.next_state_version, transition.event_sequence,
                self._thread_id(session, run_id), artifacts=tuple(self._artifacts_for_run(session, run_id)),
            )

    @staticmethod
    def _release_reservation_for_run(session, run: MigrationRunModel | None) -> None:
        if run is None or not run.preflight_id:
            return
        preflight = session.get(PreflightModel, run.preflight_id)
        reservation_id = (preflight.snapshot or {}).get("target_reservation_id") if preflight else None
        reservation = session.get(TargetReservationModel, reservation_id) if reservation_id else None
        if reservation is not None and reservation.status in {"claimed", "consumed"}:
            reservation.status = "eligible"

    def get_state(self, run_id: str):
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise MigrationRunError("RUN_NOT_FOUND", "Migration run does not exist.")
            resolution = session.scalar(select(CompatibilityResolutionModel).where(CompatibilityResolutionModel.run_id == run_id).order_by(CompatibilityResolutionModel.state_version.desc(), CompatibilityResolutionModel.created_at.desc()))
            package = resolution.package if resolution else {}
            profile = (package or {}).get("selected_profile") or {}
            discovery = session.scalar(select(DiscoveryEvidenceModel).where(DiscoveryEvidenceModel.run_id == run_id).order_by(DiscoveryEvidenceModel.created_at.desc()))
            builder = next((finding.get("value", [{}])[0].get("builder") for scanner in (discovery.scanner_results if discovery else []) if scanner.get("scanner") == "builders" for finding in scanner.get("findings", []) if finding.get("key") == "inventory" and finding.get("value")), None)
            plan_inputs = ({
                "source_exact": (package or {}).get("source_exact"),
                "source_family": (package or {}).get("source_family"),
                "target_family": (package or {}).get("target_family"),
                "catalogue_version": (package or {}).get("catalogue_version"),
                "input_fingerprint": resolution.artifact_set_checksum if resolution else None,
                "execution_profile_id": profile.get("profile_id"),
                "stage_route": [[item.get("source_family"), item.get("target_family"), item.get("stage_id"), item.get("target_angular_exact"), item.get("target_cli_exact")] for item in ((package or {}).get("route") or [])],
                "target_cli_exact": (((package or {}).get("route") or [{}])[0]).get("target_cli_exact") if (package or {}).get("route") else None,
                "builder": builder,
            } if resolution else None)
            return {
                "run_id": run.id, "status": run.status, "run_phase": run.run_phase, "phase_status": run.phase_status,
                "approval_status": run.approval_status, "repair_status": run.repair_status, "state_version": run.state_version,
                "preflight_id": run.preflight_id, "source_path": run.source_path, "target_parent_path": run.target_parent_path, "generated_output_name": run.generated_output_name, "resolved_output_root": run.resolved_output_root, "run_root": run.run_root, "migrated_app_path": run.migrated_app_path, "target_output_path": run.target_output_path,
                "graph_thread_id": run.graph_thread_id, "created_at": run.created_at, "updated_at": run.updated_at,
                "workspace_aliases": dict(run.workspace_aliases or {}),
                "source_angular_exact": (run.run_policy_snapshot or {}).get("source_angular_exact"), "catalogue_version": (run.run_policy_snapshot or {}).get("catalogue_version"),
                "registry_snapshot": (run.run_policy_snapshot or {}).get("registry_snapshot"), "runtime_candidates": (run.run_policy_snapshot or {}).get("runtime_candidates", []),
                "plan_inputs": plan_inputs,
                "artifacts": self._artifacts_for_run(session, run_id), "workflow_events": self._events_for_run(session, run_id),
            }

    def _approved_preflight(self, session, request: CreateRunRequest) -> tuple[dict, ApprovalGateModel]:
        row = session.get(PreflightModel, request.preflight_id)
        gate = session.scalar(select(ApprovalGateModel).where(ApprovalGateModel.preflight_id == request.preflight_id, ApprovalGateModel.gate_id == "G01"))
        if row is None or gate is None:
            raise MigrationRunError("G01_NOT_FOUND", "An existing G01 preflight is required.")
        if gate.status not in {"approved", "approved_with_comment"}:
            raise MigrationRunError("G01_NOT_APPROVED", "Run creation requires an approved G01 decision.")
        if row.input_checksum != request.input_checksum or row.artifact_set_checksum != request.artifact_set_checksum:
            raise MigrationRunError("G01_STALE", "The supplied G01 checksums are stale.")
        snapshot = PreflightSnapshot.model_validate(row.snapshot)
        expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
        if expires <= self._now():
            raise MigrationRunError("G01_EXPIRED", "The approved G01 preflight has expired.")
        if snapshot.status == "blocked":
            raise MigrationRunError("PREFLIGHT_BLOCKED", "A blocked preflight cannot create a run.")
        return snapshot.model_dump(mode="json"), gate

    @staticmethod
    def _thread_id(session, run_id: str) -> str:
        event = session.scalar(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id, WorkflowEventModel.event_type == WorkflowEventType.RUN_CREATED.value))
        return str((event.payload if event else {}).get("graph_thread_id") or f"source-intake-{run_id}")

    @staticmethod
    def _result_from_event(session, event: WorkflowEventModel, *, replay: bool) -> RunResult:
        run = session.get(MigrationRunModel, event.run_id)
        job = session.scalar(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == event.run_id).order_by(SourceIntakeJobModel.attempt.desc()))
        payload = event.payload
        return RunResult(event.run_id, run.status if run else str(payload.get("next_run_status", RunStatus.CREATED.value)), run.state_version if run else int(payload.get("next_state_version", 1)), event.sequence, str(payload.get("graph_thread_id") or f"source-intake-{event.run_id}"), replay, tuple(MigrationRunService._artifacts_for_run(session, event.run_id)), job.id if job else None)

    def _write_evidence(self, artifacts: LocalFilesystemArtifactStore, session, run_id: str, evidence: dict[str, object], now: datetime, input_checksum: str) -> list[ArtifactRefDto]:
        refs: list[ArtifactRefDto] = []
        for name, payload in evidence.items():
            stored = artifacts.write_text_artifact(run_id, f"00_job_setup/{name}", json.dumps(payload, sort_keys=True, indent=2), ArtifactType.JSON, created_by="migration-run-service", created_at=now, input_hashes={"preflight": input_checksum}, policy_version="s1-f06-v1")
            refs.append(stored.ref)
            session.add(ArtifactMetadataModel(id=f"metadata-{stored.ref.artifact_id}", run_id=run_id, stage_id=None, artifact_type=stored.ref.artifact_type.value, relative_path=stored.ref.relative_path, checksum=stored.ref.checksum, created_at=now))
        return refs

    @staticmethod
    def _artifacts_for_run(session, run_id: str) -> list[ArtifactRefDto]:
        return [ArtifactRefDto(
            artifact_id=row.id.removeprefix("metadata-"), run_id=run_id, stage_id=row.stage_id,
            artifact_type=ArtifactType(row.artifact_type), relative_path=row.relative_path,
            created_at=row.created_at, checksum=row.checksum, immutable=row.immutable,
            redacted=row.redacted, truncated=row.truncated,
        ) for row in session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id).order_by(ArtifactMetadataModel.relative_path))]

    @staticmethod
    def _events_for_run(session, run_id: str) -> list[WorkflowEventDto]:
        return [WorkflowEventDto(event_id=row.id, run_id=run_id, stage_id=row.stage_id, event_type=row.event_type, occurred_at=row.occurred_at, sequence=row.sequence, payload=row.payload) for row in session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id).order_by(WorkflowEventModel.sequence))]

    @staticmethod
    def _checksum(value: object) -> str:
        return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
