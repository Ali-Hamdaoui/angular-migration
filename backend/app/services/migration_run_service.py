"""Authoritative creation and production handoff for migration runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactRefDto, ArtifactType, RunPhase, RunStatus, WorkflowEventDto, WorkflowEventType
from app.domain.preflight import PreflightSnapshot
from app.orchestration.source_intake import SourceIntakeGraph, UnconfiguredSourceIntakeGraph
from app.repositories.models import ActiveRunClaimModel, ArtifactMetadataModel, MigrationRunModel, WorkflowEventModel
from app.repositories.preflight_models import ApprovalGateModel, PreflightModel
from app.repositories.session import session_scope
from app.state.transition_service import StateTransitionService, TransitionRequest


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


class MigrationRunService:
    """Own run lifecycle decisions; graph coordination remains an adapter."""

    _MUTATING_STATUSES = {
        RunStatus.CREATED.value, RunStatus.SOURCE_VALIDATION_RUNNING.value,
        RunStatus.SOURCE_VALIDATED.value, RunStatus.WORKSPACE_CLASSIFICATION_RUNNING.value,
        RunStatus.BASELINE_RUNNING.value, RunStatus.RUNNING.value, RunStatus.WAITING.value,
        RunStatus.CANCEL_REQUESTED.value, RunStatus.CANCELLING.value, RunStatus.RECOVERY_RUNNING.value,
    }

    def __init__(self, settings, *, session_scope_factory=session_scope, graph: SourceIntakeGraph | None = None, now_provider=None) -> None:
        self._scope = session_scope_factory
        self._graph = graph or UnconfiguredSourceIntakeGraph()
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._lease_seconds = settings.worker_lease_seconds
        self._artifacts = LocalFilesystemArtifactStore(settings.artifact_root)

    def create(self, request: CreateRunRequest) -> RunResult:
        with self._scope() as session:
            replay = session.scalar(select(WorkflowEventModel).where(WorkflowEventModel.idempotency_key == request.idempotency_key))
            if replay is not None:
                return self._result_from_event(session, replay, replay=True)
            snapshot, gate = self._approved_preflight(session, request)
            active = session.scalar(select(MigrationRunModel).where(MigrationRunModel.status.in_(self._MUTATING_STATUSES)).limit(1))
            if active is not None:
                raise MigrationRunError("ACTIVE_RUN_EXISTS", "Only one mutating migration run may be active.")
            run_id = f"run-{uuid4().hex[:12]}"
            thread_id = f"source-intake-{run_id}"
            now = self._now()
            run = MigrationRunModel(
                id=run_id, status=RunStatus.CREATED.value, run_phase=RunPhase.PREFLIGHT_SNAPSHOT.value,
                phase_status="running", approval_status="approved", repair_status="not_required", state_version=1,
                source_version_family=snapshot.get("source_version_family"), target_version_family=snapshot.get("target_angular_family"),
                source_angular_version=snapshot.get("source_angular_version"), target_angular_version=snapshot.get("target_angular_family"),
                preflight_id=request.preflight_id, source_path=snapshot.get("source_path"), target_output_path=snapshot.get("target_output_path"),
                graph_thread_id=thread_id, client_constraints=request.client_constraints,
                target_policy_snapshot={"target_angular_family": snapshot.get("target_angular_family"), "migration_mode": snapshot.get("migration_mode")},
                run_policy_snapshot={"input_checksum": request.input_checksum, "artifact_set_checksum": request.artifact_set_checksum, "gate_version": gate.gate_version},
                pricing_snapshot=request.pricing_snapshot, actor=request.actor,
                created_at=now, updated_at=now,
            )
            session.add(run)
            session.flush()
            self._artifacts.ensure_run_layout(run_id)
            target_path = str(snapshot.get("target_output_path") or "")
            previous_claim = session.scalar(select(ActiveRunClaimModel).where(ActiveRunClaimModel.target_output_path == target_path))
            if previous_claim is not None:
                previous_run = session.get(MigrationRunModel, previous_claim.run_id)
                if previous_run is not None and previous_run.status in self._MUTATING_STATUSES:
                    raise MigrationRunError("TARGET_OWNERSHIP_EXISTS", "The target is owned by an active migration run.")
                session.delete(previous_claim)
            session.add(ActiveRunClaimModel(id=f"claim-{uuid4().hex[:12]}", run_id=run_id, target_output_path=target_path, lease_owner=request.actor, acquired_at=now, expires_at=now + timedelta(seconds=self._lease_seconds)))
            evidence = {
                "create_run_request.json": {"preflight_id": request.preflight_id, "input_checksum": request.input_checksum, "artifact_set_checksum": request.artifact_set_checksum, "idempotency_key": request.idempotency_key, "actor": request.actor},
                "client_constraints.json": request.client_constraints,
                "target_policy.json": run.target_policy_snapshot,
                "run_policy_snapshot.json": run.run_policy_snapshot,
                "run_initial_state.json": {"run_id": run_id, "status": run.status, "run_phase": run.run_phase, "state_version": run.state_version, "graph_thread_id": thread_id},
            }
            artifact_refs = tuple(self._write_evidence(session, run_id, evidence, now, request.input_checksum))
            transition = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=1, idempotency_key=request.idempotency_key,
                event_type=WorkflowEventType.RUN_CREATED, actor=request.actor,
                reason="created from approved G01 preflight", payload={
                    "preflight_id": request.preflight_id, "input_checksum": request.input_checksum,
                    "artifact_set_checksum": request.artifact_set_checksum, "gate_id": gate.gate_id,
                    "graph_thread_id": thread_id, "source_path": snapshot.get("source_path"),
                    "target_output_path": snapshot.get("target_output_path"),
                    "client_constraints": json.dumps(request.client_constraints, sort_keys=True),
                    "policy_snapshot_checksum": self._checksum({"preflight": snapshot, "pricing": request.pricing_snapshot or {}}),
                }, occurred_at=now,
            ))
            return RunResult(run_id, run.status, transition.next_state_version, transition.event_sequence, thread_id, artifacts=artifact_refs)

    def start(self, *, run_id: str, expected_state_version: int, idempotency_key: str, actor: str) -> RunResult:
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise MigrationRunError("RUN_NOT_FOUND", "Migration run does not exist.")
            existing = session.scalar(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id, WorkflowEventModel.idempotency_key == idempotency_key))
            if existing is not None:
                return self._result_from_event(session, existing, replay=True)
            if run.status != RunStatus.CREATED.value:
                raise MigrationRunError("RUN_NOT_STARTABLE", "Only a newly created run can be started.")
            thread_id = self._thread_id(session, run_id)
            accepted = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=expected_state_version, idempotency_key=idempotency_key + ":accepted",
                event_type=WorkflowEventType.RUN_START_ACCEPTED, next_run_status=RunStatus.SOURCE_VALIDATION_RUNNING,
                actor=actor, reason="source-intake handoff accepted", payload={"graph_thread_id": thread_id}, occurred_at=self._now()))
            try:
                self._graph.start(run_id=run_id, thread_id=thread_id)
            except Exception as error:
                raise MigrationRunError("GRAPH_HANDOFF_FAILED", "Source-intake graph handoff failed safely.") from error
            started = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=accepted.next_state_version, idempotency_key=idempotency_key,
                event_type=WorkflowEventType.RUN_STARTED, actor=actor, reason="source-intake graph started",
                payload={"graph_thread_id": thread_id}, occurred_at=self._now()))
            return RunResult(run_id, started.status, started.next_state_version, started.event_sequence, thread_id, artifacts=tuple(self._artifacts_for_run(session, run_id)))

    def get_state(self, run_id: str):
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise MigrationRunError("RUN_NOT_FOUND", "Migration run does not exist.")
            return {
                "run_id": run.id, "status": run.status, "run_phase": run.run_phase, "phase_status": run.phase_status,
                "approval_status": run.approval_status, "repair_status": run.repair_status, "state_version": run.state_version,
                "preflight_id": run.preflight_id, "source_path": run.source_path, "target_output_path": run.target_output_path,
                "graph_thread_id": run.graph_thread_id, "created_at": run.created_at, "updated_at": run.updated_at,
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
        payload = event.payload
        return RunResult(event.run_id, run.status if run else str(payload.get("next_run_status", RunStatus.CREATED.value)), run.state_version if run else int(payload.get("next_state_version", 1)), event.sequence, str(payload.get("graph_thread_id") or f"source-intake-{event.run_id}"), replay, tuple(MigrationRunService._artifacts_for_run(session, event.run_id)))

    def _write_evidence(self, session, run_id: str, evidence: dict[str, object], now: datetime, input_checksum: str) -> list[ArtifactRefDto]:
        refs: list[ArtifactRefDto] = []
        for name, payload in evidence.items():
            stored = self._artifacts.write_text_artifact(run_id, f"00_job_setup/{name}", json.dumps(payload, sort_keys=True, indent=2), ArtifactType.JSON, created_by="migration-run-service", created_at=now, input_hashes={"preflight": input_checksum}, policy_version="s1-f06-v1")
            refs.append(stored.ref)
            session.add(ArtifactMetadataModel(id=f"metadata-{stored.ref.artifact_id}", run_id=run_id, stage_id=None, artifact_type=stored.ref.artifact_type.value, relative_path=stored.ref.relative_path, checksum=stored.ref.checksum, created_at=now))
        return refs

    @staticmethod
    def _artifacts_for_run(session, run_id: str) -> list[ArtifactRefDto]:
        return [ArtifactRefDto(artifact_id=row.id.removeprefix("metadata-"), run_id=run_id, stage_id=row.stage_id, artifact_type=ArtifactType(row.artifact_type), relative_path=row.relative_path, created_at=row.created_at, checksum=row.checksum) for row in session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id).order_by(ArtifactMetadataModel.relative_path))]

    @staticmethod
    def _events_for_run(session, run_id: str) -> list[WorkflowEventDto]:
        return [WorkflowEventDto(event_id=row.id, run_id=run_id, stage_id=row.stage_id, event_type=row.event_type, occurred_at=row.occurred_at, sequence=row.sequence, payload=row.payload) for row in session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id).order_by(WorkflowEventModel.sequence))]

    @staticmethod
    def _checksum(value: object) -> str:
        return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
