"""Application service for stage workspace preparation (S3-F05)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from collections.abc import Callable

from sqlalchemy import select

from app.api.stage_contracts import (
    G07ReviewResponse,
    StageBootstrapInstallResponse,
    StageBootstrapStatusResponse,
    StagePrepareResponse,
    StageSandboxResponse,
)
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactRefDto, ArtifactType, StageStatus, WorkflowEventType
from app.domain.stage_workspace import (
    BootstrapInstallResult,
    G07ApprovalPackage,
    G07ApprovalPackageBuilder,
    G07ApprovalResult,
    G07ApprovalService,
    G07Decision,
    StageExecutionPlan,
    StageFingerprint,
    StageInputManifest,
    StageSandboxVerification,
    StageWorkspaceService,
    WorkspaceCopyReport,
    _artifact_set_checksum,
)
from app.repositories.models import ArtifactMetadataModel, MigrationRunModel, StageStepModel, WorkerLeaseModel
from app.repositories.models.workflow import MigrationStageModel, WorkflowEventModel
from app.repositories.models import SourceSnapshotModel
from app.repositories.planning_models import ActivePlanVersionModel, MigrationPlanModel, StageExecutionPlanModel
from app.repositories.planning_review_models import G06ApprovalModel as PlanningG06ApprovalModel
from app.domain.planning_review import G06Gate
from app.services.planning_review_application_service import PlanRevisionService
from app.services.planning_review_evidence_application_service import PlanningReviewEvidenceApplicationService
from app.repositories.session import session_scope
from app.repositories.stage_workspace_models import (
    G07ApprovalModel,
    G07DecisionHistoryModel,
    StageWorkspaceModel,
)
from app.state.transition_service import StateTransitionService, TransitionRequest
from app.state.transition_service import LeaseRequiredError
from app.workspaces.baseline import BaselineBoundaryError, BaselineCopyCancelled, BaselineSandboxService
from app.workspaces.services import WorkspaceService
from app.snapshots.services import SnapshotService


class StageApplicationError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.status_code = status_code


class StagePreparationApplicationService:
    """Application service for S3-F05 stage sandbox preparation and G07 gate."""

    GATE_ID = "G07"
    GATE_VERSION = "g07-v1"
    STAGE_POLICY_VERSION = "stage-workspace-policy-v1"
    WORKSPACE_ALIAS = "STAGE_SANDBOX"

    def __init__(self, *, session_scope_factory=session_scope, now_provider=None, policy_version: str | None = None,
                 current_version_detector: Callable[[Path], str | None] | None = None) -> None:
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._policy_version = policy_version or self.STAGE_POLICY_VERSION
        self._current_version_detector = current_version_detector or self._detect_current_version

    def prepare_stage(self, run_id: str, request) -> StagePrepareResponse:
        """Prepare a stage and always clean up the preparation lease."""
        lease_holder = {}
        try:
            return self._prepare_stage(run_id, request, lease_holder=lease_holder)
        finally:
            lease = lease_holder.get("lease")
            if lease is not None:
                self._release_prepare_lease(lease.id, lease.worker_id)

    def _prepare_stage(self, run_id: str, request, *, lease_holder=None) -> StagePrepareResponse:
        """Resolve and durably prepare one stage boundary.

        All prerequisites are resolved from durable planning, G06, and snapshot
        authorities. Missing authority is an error; request fields are never a
        production planning fallback.
        """
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise StageApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            self._authorize_run(run, request.actor)
            if run.state_version != request.expected_state_version and session.scalar(
                select(MigrationStageModel).where(MigrationStageModel.run_id == run_id)
            ) is None:
                raise StageApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)
            active = self._resolve_active_plan(session, run_id, request.stage_key)
            plan, stage_plan, g06, input_fingerprint, snapshot = active
            deterministic_stage_id = f"stage-{hashlib.sha256(f'{run_id}:{stage_plan.id}:{stage_plan.version}:{stage_plan.checksum}'.encode()).hexdigest()[:12]}"
            replay_stage = session.get(MigrationStageModel, deterministic_stage_id)
            if replay_stage is not None:
                if replay_stage.run_id != run_id or replay_stage.status not in {status.value for status in StageStatus}:
                    self._fail("IDEMPOTENCY_PAYLOAD_MISMATCH", "The idempotency key was already used with a different payload.", status_code=409)
                replay_gate = session.scalar(select(G07ApprovalModel).where(
                    G07ApprovalModel.run_id == run_id, G07ApprovalModel.stage_id == replay_stage.id,
                ).order_by(G07ApprovalModel.created_at.desc()))
                expected_checksum = self._prepare_binding_checksum(
                    run_id, request, replay_stage, plan, stage_plan, g06, input_fingerprint,
                    snapshot.id, self._intended_destination(run, replay_stage.id),
                )
                if replay_gate is None or replay_gate.prepare_request_checksum != expected_checksum:
                    if replay_gate is not None and replay_gate.idempotency_key != f"{request.idempotency_key}:g07":
                        self._fail("ACTIVE_STAGE_EXISTS", "The run already has an active stage preparation.", status_code=409)
                    self._fail("IDEMPOTENCY_PAYLOAD_MISMATCH", "The idempotency key was already used with a different payload.", status_code=409)
                for artifact_id in replay_gate.artifact_ids or []:
                    self._verify_stage_artifact(run, artifact_id)
                return StagePrepareResponse(
                    run_id=run_id, stage_id=replay_stage.id, stage_key=request.stage_key,
                    status=StageStatus(replay_stage.status).value, state_version=replay_gate.state_version,
                    event_sequence=replay_gate.event_sequence,
                    plan=self._stage_plan_payload_from_gate(session, replay_stage.id),
                    idempotent_replay=True,
                )
            detected = self._current_version_detector(Path(snapshot.snapshot_path))
            expected = stage_plan.stage_plan.get("source_exact") or stage_plan.stage_plan.get("source_version")
            if not detected:
                self._fail("CURRENT_VERSION_UNAVAILABLE", "Current Angular version detection is unavailable.", status_code=409)
            if expected and detected != expected:
                self._fail("CURRENT_VERSION_MISMATCH", "Detected current Angular version does not match the active stage plan.", status_code=409)

            # Deterministic stage identity makes a retry of the same request a
            # replay instead of creating a second active stage.
            stage_id = deterministic_stage_id
            active_stage = session.scalar(select(MigrationStageModel).where(
                MigrationStageModel.run_id == run_id,
                MigrationStageModel.status.in_((StageStatus.PREPARING.value, StageStatus.PLAN_LOCKED.value,
                                                StageStatus.WAITING_APPROVAL.value, StageStatus.SANDBOX_READY.value)),
                MigrationStageModel.id != stage_id,
            ))
            if active_stage is not None:
                self._fail("ACTIVE_STAGE_EXISTS", "The run already has an active stage preparation.", status_code=409)
            stage = session.get(MigrationStageModel, stage_id)
            if stage is not None:
                if stage.run_id != run_id or stage.status not in {
                    StageStatus.PREPARING.value, StageStatus.PLAN_LOCKED.value,
                    StageStatus.WAITING_APPROVAL.value, StageStatus.SANDBOX_READY.value,
                }:
                    self._fail("IDEMPOTENCY_PAYLOAD_MISMATCH", "The idempotency key was already used with a different stage.", status_code=409)
                return StagePrepareResponse(
                    run_id=run_id, stage_id=stage.id, stage_key=request.stage_key,
                    status=stage.status, state_version=run.state_version,
                    event_sequence=self._latest_event_sequence(session, run_id),
                    plan=self._stage_plan_payload(active, request), idempotent_replay=True,
                )

            # Create migration stage record
            stage = MigrationStageModel(
                id=stage_id,
                run_id=run_id,
                stage_order=1,
                source_version_family=stage_plan.stage_plan.get("source_family", ""),
                target_version_family=stage_plan.stage_plan.get("target_family", ""),
                status="preparing",
                current_agent=None,
                created_at=now,
            )
            session.add(stage)
            session.flush()

            # Acquire the existing Transition Service lease before durable
            # workflow mutation.  Lease acquisition itself is non-stateful.
            try:
                prepare_lease = StateTransitionService(session).acquire_lease(
                    run_id=run_id, worker_id=f"stage-preparer:{stage_id}", lease_owner=request.actor, now=now
                )
            except LeaseRequiredError as error:
                self._fail("LEASE_CONFLICT", str(error), status_code=409)
            if lease_holder is not None:
                lease_holder["lease"] = prepare_lease

            plan = self._stage_plan_contract(active, request)

            # Emit STAGE_CREATED event
            transition = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=run.state_version,
                idempotency_key=f"{request.idempotency_key}:stage_created",
                event_type=WorkflowEventType.STAGE_CREATED, actor=request.actor,
                reason="Stage workspace record created", occurred_at=now,
                stage_id=stage.id,
                next_stage_status=StageStatus.PREPARING,
                payload={"stage_id": stage.id, "stage_key": plan.stage_key, "plan_version": plan.plan_version,
                         "plan_checksum": plan.plan_checksum, "input_fingerprint": input_fingerprint},
            ))

            # Emit STAGE_PREPARING event
            transition2 = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=transition.next_state_version,
                idempotency_key=f"{request.idempotency_key}:preparing",
                event_type=WorkflowEventType.STAGE_PREPARING, actor=request.actor,
                reason="Stage sandbox preparation started", occurred_at=now,
                stage_id=stage.id, next_stage_status=StageStatus.PREPARING,
                payload={"stage_id": stage.id, "stage_key": plan.stage_key},
            ))
            transition3 = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=transition2.next_state_version,
                idempotency_key=f"{request.idempotency_key}:plan_locked",
                event_type=WorkflowEventType.STAGE_PLAN_LOCKED, actor=request.actor,
                reason="Authoritative stage execution plan locked", occurred_at=now,
                stage_id=stage.id, next_stage_status=StageStatus.PLAN_LOCKED,
                payload={"stage_id": stage.id, "plan_checksum": plan.plan_checksum},
            ))
            transition4 = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=transition3.next_state_version,
                idempotency_key=f"{request.idempotency_key}:waiting_approval",
                event_type=WorkflowEventType.STAGE_WAITING_APPROVAL, actor=request.actor,
                reason="Stage preparation awaits current G07 approval", occurred_at=now,
                stage_id=stage.id, next_stage_status=StageStatus.WAITING_APPROVAL,
                payload={"stage_id": stage.id},
            ))
            manifest = StageInputManifest(
                    stage_id=stage.id, run_id=run_id, source_fingerprint=input_fingerprint,
                    snapshot_id=snapshot.id, plan=plan,
                    manifest_checksum=self._checksum({"stage_id": stage.id, "snapshot_id": snapshot.id,
                                                     "source_fingerprint": input_fingerprint,
                                                     "plan_checksum": plan.plan_checksum}),
                )
            self._persist_stage_start_evidence(
                session, run, stage, request, active[0], stage_plan, g06, snapshot, input_fingerprint,
            )
            stage_artifacts = self._stage_artifacts(session, run_id, stage.id)
            package = G07ApprovalPackageBuilder().build(
                    run_id=run_id, state_version=transition4.next_state_version, actor=request.actor,
                    stage_id=stage.id, stage_key=plan.stage_key, gate_version=self.GATE_VERSION,
                    plan_version=plan.plan_version, source_fingerprint=input_fingerprint,
                    workspace_fingerprint=None, input_manifest=manifest, copy_report=None,
                    migration_plan_id=active[0].id, migration_plan_checksum=active[0].checksum,
                    stage_plan_id=active[1].id, stage_plan_checksum=active[1].checksum,
                    profile=stage_plan.stage_plan.get("execution_profile_id"),
                    approved_commands=tuple(self._stage_plan_contract(active, request).approved_commands),
                    g06_id=g06.id, g06_gate_version=g06.gate_version,
                    g06_package_checksum=g06.package_checksum, input_snapshot_id=snapshot.id,
                    intended_destination=self._intended_destination(run, stage.id), workspace_alias=self.WORKSPACE_ALIAS,
                    artifacts=stage_artifacts,
                )
            session.add(G07ApprovalModel(
                    id=f"g07-{hashlib.sha256(f'{run_id}:{stage.id}:prepare'.encode()).hexdigest()[:12]}",
                    run_id=run_id, stage_id=stage.id, gate_id=self.GATE_ID, gate_version=self.GATE_VERSION,
                    idempotency_key=f"{request.idempotency_key}:g07", actor=request.actor, status="pending",
                    decision=None, package_checksum=package.package_checksum, artifact_set_checksum=package.artifact_set_checksum,
                    stage_key=plan.stage_key, plan_version=plan.plan_version, state_version=transition4.next_state_version,
                    event_sequence=transition4.event_sequence, package=package.model_dump(mode="json"),
                    artifact_ids=[item.artifact_id for item in stage_artifacts],
                    stale_reason=None, comment=None, created_at=now, updated_at=now,
                    prepare_request_checksum=self._prepare_binding_checksum(
                        run_id, request, stage, active[0], active[1], active[2],
                        input_fingerprint, snapshot.id, self._intended_destination(run, stage.id),
                    ),
                ))
            session.flush()
            created_event = StateTransitionService(session).append_audit_event(
                run_id=run_id, idempotency_key=f"{request.idempotency_key}:g07-created",
                event_type=WorkflowEventType.G07_CREATED, actor=request.actor,
                reason="Current G07 package persisted", occurred_at=now,
                payload={"stage_id": stage.id, "package_checksum": package.package_checksum},
            )
            gate = session.scalar(select(G07ApprovalModel).where(G07ApprovalModel.stage_id == stage.id))
            gate.event_sequence = created_event.event_sequence
            stage.started_at = now
            session.flush()

            return StagePrepareResponse(
                run_id=run_id,
                stage_id=stage.id,
                stage_key=request.stage_key,
                status=StageStatus.WAITING_APPROVAL.value,
                state_version=transition4.next_state_version,
                event_sequence=created_event.event_sequence,
                plan=plan.model_dump(mode="json"),
                idempotent_replay=True,
            )

    def _release_prepare_lease(self, lease_id: str, worker_id: str) -> None:
        """Release only the exact preparation lease acquired by this call."""
        with self._scope() as session:
            try:
                StateTransitionService(session).release_lease(lease_id=lease_id, worker_id=worker_id)
            except LeaseRequiredError:
                # The enclosing transaction may already have rolled back the
                # lease; in that case there is nothing left for this call to
                # release.  Never broaden cleanup to another worker's lease.
                return

    def _persist_stage_start_evidence(self, session, run, stage, request, plan, stage_plan, g06, snapshot, input_fingerprint):
        destination = self._intended_destination(run, stage.id)
        bindings = self._locked_bindings(
            run, stage, plan, stage_plan, g06, input_fingerprint, destination, request.actor,
            _artifact_set_checksum(self._stage_artifacts(session, run.id, stage.id)),
        )
        payload = {
            "run_id": run.id, "stage_id": stage.id, "stage_key": stage_plan.stage_id,
            "migration_plan": {"id": plan.id, "version": plan.version, "checksum": plan.checksum},
            "stage_plan": {"id": stage_plan.id, "version": stage_plan.version, "checksum": stage_plan.checksum},
            "g06": {"id": g06.id, "gate_version": g06.gate_version, "package_checksum": g06.package_checksum},
            "input_snapshot": {"id": snapshot.id, "fingerprint": input_fingerprint},
            "input_source_path": snapshot.snapshot_path,
            "input_file_count": snapshot.file_count,
            "input_total_size_bytes": snapshot.total_size_bytes,
            "profile": stage_plan.stage_plan.get("execution_profile_id"),
            "approved_commands": stage_plan.stage_plan.get("commands", {}),
            "destination": destination, "workspace_alias": self.WORKSPACE_ALIAS,
            "g07_package_checksum": self._checksum(bindings),
            "artifact_set_checksum": _artifact_set_checksum(self._stage_artifacts(session, run.id, stage.id)),
        }
        content = json.dumps(payload, sort_keys=True, indent=2, default=str)
        store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
        relative_path = f"stages/{stage.id}/stage_start_evidence.json"
        existing = None
        try:
            existing = store.read_artifact(run.id, relative_path)
            if existing.ref.checksum != self._content_checksum(existing.content):
                self._fail("ARTIFACT_TAMPERED", "Stage-start evidence checksum verification failed.", status_code=409)
            if json.loads(existing.content) != payload:
                self._fail("ARTIFACT_BINDINGS_CHANGED", "Stage-start evidence bindings changed.", status_code=409)
            stored = existing
        except FileNotFoundError:
            stored = store.write_text_artifact(
                run.id, relative_path, content, ArtifactType.JSON, stage_id=stage.id,
                created_by="stage-preparation-service", created_at=self._now(),
                input_hashes={"input_fingerprint": input_fingerprint, "g06": g06.package_checksum},
                policy_version=self._policy_version,
            )
        metadata_id = f"metadata-{stored.ref.artifact_id}"
        if session.get(ArtifactMetadataModel, metadata_id) is None:
            session.add(ArtifactMetadataModel(
                id=metadata_id, run_id=run.id, stage_id=stage.id,
                artifact_type=stored.ref.artifact_type.value, relative_path=stored.ref.relative_path,
                checksum=stored.ref.checksum, created_at=stored.ref.created_at,
            ))
            session.flush()
        return stored.ref

    def _verify_stage_artifact(self, run, artifact_id: str) -> None:
        store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
        try:
            stored = store.read_artifact_by_id(artifact_id)
        except (FileNotFoundError, OSError, ValueError) as error:
            self._fail("ARTIFACT_INVALID", "Stage evidence artifact is unavailable.", status_code=409)
        if stored.ref.checksum != self._content_checksum(stored.content):
            self._fail("ARTIFACT_TAMPERED", "Stage evidence artifact checksum verification failed.", status_code=409)

    def _resolve_active_plan(self, session, run_id: str, stage_key: str):
        authority = PlanningReviewEvidenceApplicationService(scope=lambda: session)
        try:
            plan, stage_plan = authority._active_plan_pair(session, run_id)
            authority._require_active_binding(
                plan, stage_plan,
                {"checksum": plan.checksum},
                {"checksum": stage_plan.checksum, "plan_version": plan.version},
            )
        except Exception as error:
            self._fail("PLAN_NOT_FOUND", str(error), status_code=409)
        if stage_plan.stage_id != stage_key or stage_plan.run_id != run_id or stage_plan.migration_plan_id != plan.id:
            self._fail("STAGE_PLAN_NOT_FOUND", "The requested stage is not the active stage.", status_code=409)
        snapshot = session.scalar(select(SourceSnapshotModel).where(
            SourceSnapshotModel.run_id == run_id, SourceSnapshotModel.status == "created",
            SourceSnapshotModel.fingerprint.is_not(None),
        ).order_by(SourceSnapshotModel.created_at.desc()))
        input_fingerprint = snapshot.fingerprint if snapshot else None
        if snapshot is None or not input_fingerprint:
            self._fail("INPUT_FINGERPRINT_REQUIRED", "An authoritative input fingerprint is required.", status_code=409)
        g06 = session.scalar(select(PlanningG06ApprovalModel).where(
            PlanningG06ApprovalModel.run_id == run_id,
            PlanningG06ApprovalModel.gate_id == "G06",
        ).order_by(PlanningG06ApprovalModel.state_version.desc(), PlanningG06ApprovalModel.created_at.desc()))
        if g06 is None:
            self._fail("G06_APPROVAL_REQUIRED", "An approved current G06 gate is required before stage preparation.", status_code=409)
        try:
            current_artifact_checksum = _artifact_set_checksum(self._stage_artifacts(session, run_id, stage_plan.stage_id))
            PlanRevisionService().require_approved_g06(
                G06Gate(run_id=run_id, gate_version=g06.gate_version, status=g06.status,
                        artifact_set_checksum=g06.artifact_set_checksum, plan_checksum=g06.plan_checksum,
                        stage_plan_checksum=g06.stage_plan_checksum, package_checksum=g06.package_checksum,
                        workspace_fingerprint=g06.workspace_fingerprint, state_version=g06.state_version),
                state_version=g06.state_version,
                artifact_set_checksum=current_artifact_checksum,
                plan_checksum=plan.checksum, stage_plan_checksum=stage_plan.checksum,
                workspace_fingerprint=input_fingerprint,
            )
        except Exception as error:
            self._fail("G06_STALE" if g06.status == "approved" else "G06_APPROVAL_REQUIRED", str(error), status_code=409)
        return plan, stage_plan, g06, input_fingerprint, snapshot

    def _prepare_binding_checksum(self, run_id, request, stage, plan, stage_plan, g06, input_fingerprint, snapshot_id, destination):
        return self._checksum({
            "run_id": run_id, "stage_id": stage.id, "stage_key": stage_plan.stage_id,
            "idempotency_key": request.idempotency_key, "actor": request.actor,
            "migration_plan_id": plan.id, "migration_plan_version": plan.version,
            "migration_plan_checksum": plan.checksum, "stage_plan_id": stage_plan.id,
            "stage_plan_checksum": stage_plan.checksum, "g06_id": g06.id,
            "g06_package_checksum": g06.package_checksum, "input_snapshot_id": snapshot_id,
            "input_fingerprint": input_fingerprint, "profile": stage_plan.stage_plan.get("execution_profile_id"),
            "approved_commands": stage_plan.stage_plan.get("commands", {}), "destination": destination,
        })

    @staticmethod
    def _stage_authority_key(session, stage):
        gate = session.scalar(select(G07ApprovalModel).where(
            G07ApprovalModel.run_id == stage.run_id, G07ApprovalModel.stage_id == stage.id,
        ).order_by(G07ApprovalModel.created_at.desc()))
        if gate is not None and isinstance(gate.package, dict):
            manifest = gate.package.get("input_manifest") or {}
            plan = manifest.get("plan") or {}
            if plan.get("stage_key"):
                return str(plan["stage_key"])
            if gate.stage_key:
                return gate.stage_key
        return stage.id

    def _stage_plan_contract(self, active, request) -> StageExecutionPlan:
        plan, stage_plan, _g06, input_fingerprint, _snapshot = active
        raw = stage_plan.stage_plan
        commands = raw.get("commands") or {}
        approved = []
        for refs in commands.values():
            if isinstance(refs, list):
                approved.extend(item if isinstance(item, str) else item.get("command", item.get("command_id", "")) for item in refs)
        return StageExecutionPlan(
            stage_key=stage_plan.stage_id,
            source_version_family=raw.get("source_family", ""),
            target_version_family=raw.get("target_family", ""),
            source_angular_version=raw.get("source_exact"), target_angular_version=raw.get("target_exact"),
            toolchain_profile=raw.get("execution_profile_id", ""), approved_commands=tuple(filter(None, approved)),
            plan_version=str(plan.version), plan_checksum=stage_plan.checksum,
        )

    def _stage_plan_payload(self, active, request):
        return self._stage_plan_contract(active, request).model_dump(mode="json")

    def _stage_plan_payload_from_gate(self, session, stage_id: str):
        gate = session.scalar(select(G07ApprovalModel).where(
            G07ApprovalModel.run_id == session.get(MigrationStageModel, stage_id).run_id,
            G07ApprovalModel.stage_id == stage_id,
        ).order_by(G07ApprovalModel.created_at.desc()))
        if gate is None:
            self._fail("PLAN_LOCK_NOT_FOUND", "The persisted stage lock is unavailable.", status_code=409)
        package = G07ApprovalPackage.model_validate(gate.package)
        return package.input_manifest.plan.model_dump(mode="json")

    @staticmethod
    def _detect_current_version(snapshot_root: Path) -> str | None:
        try:
            payload = json.loads((snapshot_root / "package.json").read_text(encoding="utf-8"))
            version = (payload.get("dependencies") or {}).get("@angular/core")
            version = version or (payload.get("devDependencies") or {}).get("@angular/core")
            if not version:
                return None
            value = str(version).lstrip("^~>=< ")
            parts = value.split(".")
            return ".".join(parts[:3]) if len(parts) >= 3 else None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _latest_event_sequence(session, run_id: str) -> int:
        from app.repositories.models.workflow import WorkflowEventModel
        return int(session.scalar(select(__import__("sqlalchemy", fromlist=["func"]).func.max(WorkflowEventModel.sequence)).where(WorkflowEventModel.run_id == run_id)) or 1)

    def _validate_current_g07(self, session, gate, run, stage, plan, stage_plan, g06, input_fingerprint, snapshot_id, *, require_approved=True):
        if gate is None or (require_approved and gate.status not in {"approved", "approved_with_comment"}):
            self._fail("G07_APPROVAL_REQUIRED", "A current approved G07 decision is required before sandbox creation.", status_code=409)
        if gate.expires_at is not None and gate.expires_at <= self._now():
            self._invalidate_g07(session, gate, "G07_EXPIRED")
            self._fail("G07_STALE", "The G07 approval has expired.", status_code=409)
        if gate.state_version != run.state_version:
            self._invalidate_g07(session, gate, "G07_STATE_VERSION_CHANGED")
            self._fail("G07_STALE", "The G07 approval is stale after a state transition.", status_code=409)
        package = G07ApprovalPackage.model_validate(gate.package)
        integrity = G07ApprovalService().decide(package, G07Decision.APPROVED)
        if integrity.stale or package.package_checksum != gate.package_checksum:
            self._fail("G07_PACKAGE_INVALID", "The persisted G07 package checksum is invalid.", status_code=409)
        if (
            package.run_id != run.id or package.stage_id != stage.id or package.stage_key != stage_plan.stage_id
            or package.plan_version != str(plan.version) or package.source_fingerprint != input_fingerprint
            or package.input_manifest.snapshot_id != snapshot_id
            or package.input_manifest.plan.plan_checksum != stage_plan.checksum
            or gate.artifact_set_checksum != package.artifact_set_checksum
            or g06 is None or g06.status != "approved"
            or g06.plan_checksum != plan.checksum or g06.stage_plan_checksum != stage_plan.checksum
            or g06.workspace_fingerprint != input_fingerprint
            or package.migration_plan_id != plan.id
            or package.migration_plan_checksum != plan.checksum
            or package.stage_plan_id != stage_plan.id
            or package.stage_plan_checksum != stage_plan.checksum
            or package.input_snapshot_id != snapshot_id
            or package.intended_destination != self._intended_destination(run, stage.id)
            or package.workspace_alias != self.WORKSPACE_ALIAS
            or package.g06_id != g06.id
            or package.g06_gate_version != g06.gate_version
            or package.g06_package_checksum != g06.package_checksum
            or package.profile != stage_plan.stage_plan.get("execution_profile_id")
            or tuple(package.approved_commands) != tuple(self._stage_plan_contract((plan, stage_plan, g06, input_fingerprint, None), None).approved_commands)
            or package.artifact_set_checksum != _artifact_set_checksum(self._stage_artifacts(session, run.id, stage.id))
        ):
            self._invalidate_g07(session, gate, "G07_BINDINGS_CHANGED")
            self._fail("G07_STALE", "The approved G07 binding no longer matches current authorities.", status_code=409)
        return package

    def _invalidate_g07(self, session, gate, reason: str) -> None:
        if gate.status == "stale":
            return
        gate.status = "stale"
        gate.stale_reason = reason
        gate.updated_at = self._now()
        session.flush()
        StateTransitionService(session).append_audit_event(
            run_id=gate.run_id, idempotency_key=f"{gate.id}:stale",
            event_type=WorkflowEventType.G07_STALE, actor="system",
            reason=reason, occurred_at=gate.updated_at,
            payload={"stage_id": gate.stage_id, "package_checksum": gate.package_checksum},
        )
        session.commit()

    @staticmethod
    def _content_checksum(content: str) -> str:
        return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"

    @staticmethod
    def _stage_artifacts(session, run_id: str, stage_id: str):
        rows = session.scalars(select(ArtifactMetadataModel).where(
            ArtifactMetadataModel.run_id == run_id, ArtifactMetadataModel.stage_id == stage_id,
        ))
        return [ArtifactRefDto(
            artifact_id=row.id.removeprefix("metadata-"), run_id=run_id, stage_id=stage_id,
            artifact_type=ArtifactType(row.artifact_type), relative_path=row.relative_path,
            created_at=row.created_at, checksum=row.checksum,
        ) for row in rows if not Path(row.relative_path).stem.startswith(("sandbox_copy_report", "sandbox_verification"))]

    def _locked_bindings(self, run, stage, plan, stage_plan, g06, input_fingerprint, destination, actor=None, artifact_set_checksum=None):
        return {
            "run_id": run.id, "stage_id": stage.id, "stage_key": stage_plan.stage_id, "actor": actor,
            "migration_plan_id": plan.id, "migration_plan_version": plan.version,
            "migration_plan_checksum": plan.checksum, "stage_plan_id": stage_plan.id,
            "stage_plan_checksum": stage_plan.checksum, "source_version": stage_plan.stage_plan.get("source_exact"),
            "target_version": stage_plan.stage_plan.get("target_exact"),
            "profile": stage_plan.stage_plan.get("execution_profile_id"),
            "approved_commands": stage_plan.stage_plan.get("commands", {}),
            "g06_id": g06.id, "g06_package_checksum": g06.package_checksum,
            "g06_plan_checksum": g06.plan_checksum, "g06_stage_plan_checksum": g06.stage_plan_checksum,
            "input_snapshot_fingerprint": input_fingerprint, "destination": destination,
            "artifact_set_checksum": artifact_set_checksum,
        }

    def _intended_destination(self, run, stage_id: str) -> str:
        if not run.run_root:
            self._fail("REGISTERED_WORKSPACE_REQUIRED", "A registered run workspace root is required.", status_code=409)
        return str((WorkspaceService(Path(run.run_root)).workspace_root / "sandboxes" / "stages" / stage_id).resolve())

    def _binding_checksum(self, run, stage, plan, stage_plan, g06, input_fingerprint, destination, actor=None, artifact_set_checksum=None):
        return self._checksum(self._locked_bindings(run, stage, plan, stage_plan, g06, input_fingerprint, destination, actor, artifact_set_checksum))

    @staticmethod
    def _verification_from_workspace(workspace):
        return StageSandboxVerification(
            stage_id=workspace.stage_id, sandbox_path=workspace.sandbox_path,
            pre_fingerprint=StageFingerprint(workspace_path=workspace.sandbox_path, fingerprint=workspace.source_fingerprint,
                policy_version=workspace.policy_version, file_count=workspace.file_count, total_size_bytes=workspace.total_size_bytes),
            post_fingerprint=StageFingerprint(workspace_path=workspace.sandbox_path, fingerprint=workspace.workspace_fingerprint,
                policy_version=workspace.policy_version, file_count=workspace.file_count, total_size_bytes=workspace.total_size_bytes),
            verification_checksum=workspace.verification_checksum or "sha256:unavailable",
            verified=workspace.copy_status == "verified",
        )

    @staticmethod
    def _fail(code: str, message: str, *, status_code: int = 422):
        raise StageApplicationError(code, message, status_code=status_code)

    def create_sandbox(self, run_id: str, stage_id: str, request) -> StageSandboxResponse:
        """Create the isolated stage sandbox by copying files from the source snapshot."""
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise StageApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            self._authorize_run(run, request.actor)
            stage = session.get(MigrationStageModel, stage_id)
            if stage is None or stage.run_id != run_id:
                raise StageApplicationError("STAGE_NOT_FOUND", "Stage does not exist.", status_code=404)
            existing_workspace = session.scalar(select(StageWorkspaceModel).where(
                StageWorkspaceModel.run_id == run_id, StageWorkspaceModel.stage_id == stage_id
            ))
            current_gate = session.scalar(select(G07ApprovalModel).where(
                G07ApprovalModel.run_id == run_id, G07ApprovalModel.stage_id == stage_id,
            ).order_by(G07ApprovalModel.created_at.desc()))
            if current_gate is None or current_gate.status not in {"approved", "approved_with_comment"}:
                self._fail("G07_APPROVAL_REQUIRED", "A current approved G07 decision is required before sandbox creation.", status_code=409)
            if run.state_version != request.expected_state_version and not (
                existing_workspace is not None and existing_workspace.request_idempotency_key == request.idempotency_key
            ):
                raise StageApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)

            try:
                active = self._resolve_active_plan(session, run_id, self._stage_authority_key(session, stage))
            except StageApplicationError as error:
                if current_gate is not None and current_gate.status in {"pending", "approved", "approved_with_comment"}:
                    self._invalidate_g07(session, current_gate, error.code)
                raise

            # Check for existing idempotent sandbox
            existing = session.scalar(
                select(StageWorkspaceModel)
                .where(StageWorkspaceModel.run_id == run_id, StageWorkspaceModel.stage_id == stage_id)
            )
            if existing is not None:
                plan, stage_plan, g06, input_fingerprint, snapshot = active
                current_bindings = self._locked_bindings(
                    run, stage, plan, stage_plan, g06, input_fingerprint,
                    self._intended_destination(run, stage.id), request.actor,
                    _artifact_set_checksum(self._stage_artifacts(session, run_id, stage_id)),
                )
                if existing.request_binding_checksum != self._checksum(current_bindings) or existing.locked_bindings != current_bindings:
                    self._fail("SANDBOX_REPLAY_MISMATCH", "The persisted sandbox bindings drifted.", status_code=409)
                if existing.request_idempotency_key != request.idempotency_key:
                    self._fail("IDEMPOTENCY_PAYLOAD_MISMATCH", "The sandbox idempotency key was already used with a different payload.", status_code=409)
                ready_event = session.scalar(select(WorkflowEventModel).where(
                    WorkflowEventModel.run_id == run.id,
                    WorkflowEventModel.event_type == WorkflowEventType.STAGE_SANDBOX_READY.value,
                    WorkflowEventModel.stage_id == stage.id,
                ))
                recovered_from_interruption = existing.copy_status != "verified" or ready_event is None
                if recovered_from_interruption:
                    try:
                        recovered = BaselineSandboxService().reconstruct(
                            run_id=run.id, snapshot_root=Path(snapshot.snapshot_path),
                            baseline_path=Path(existing.sandbox_path), approved_snapshot_fingerprint=input_fingerprint,
                            registered_run_root=WorkspaceService(Path(run.run_root)).workspace_root,
                        )
                    except (BaselineBoundaryError, BaselineCopyCancelled, FileExistsError, OSError) as error:
                        self._fail("SANDBOX_RECONSTRUCTION_FAILED", str(error), status_code=409)
                    existing.workspace_fingerprint = recovered.fingerprint
                    existing.file_count, existing.total_size_bytes = self._tree_stats(recovered.sandbox_path)
                    expected_count, expected_size = self._copy_tree_stats(Path(snapshot.snapshot_path))
                    expected_fingerprint = self._content_fingerprint(Path(snapshot.snapshot_path), copied_only=True)
                    if (recovered.fingerprint != expected_fingerprint or existing.file_count != expected_count
                            or existing.total_size_bytes != expected_size):
                        self._fail("SANDBOX_FINGERPRINT_MISMATCH", "Reconstructed sandbox verification failed.", status_code=409)
                    pre = StageFingerprint(workspace_path=str(snapshot.snapshot_path), fingerprint=input_fingerprint,
                                           policy_version=self._policy_version, file_count=expected_count, total_size_bytes=expected_size)
                    post = StageFingerprint(workspace_path=str(recovered.sandbox_path), fingerprint=recovered.fingerprint,
                                            policy_version=self._policy_version, file_count=existing.file_count, total_size_bytes=existing.total_size_bytes)
                    verification = StageSandboxVerification(
                        stage_id=stage.id, sandbox_path=str(recovered.sandbox_path), pre_fingerprint=pre, post_fingerprint=post,
                        verification_checksum=self._checksum({"pre": pre.model_dump(), "post": post.model_dump()}), verified=True,
                    )
                    existing.completed_at = now
                    self._persist_sandbox_evidence(
                        session, run, stage, existing, verification,
                        source_path=str(snapshot.snapshot_path), reconstruction=True,
                    )
                    existing.copy_status = "verified"
                    existing.verification = verification.model_dump(mode="json")
                    existing.verification_checksum = verification.verification_checksum
                    session.flush()
                    session.commit()
                    transition = StateTransitionService(session).apply_transition(TransitionRequest(
                        run_id=run.id, expected_state_version=run.state_version,
                        idempotency_key=f"{request.idempotency_key}:sandbox-ready",
                        event_type=WorkflowEventType.STAGE_SANDBOX_READY, stage_id=stage.id,
                        next_stage_status=StageStatus.SANDBOX_READY, actor=request.actor,
                        reason="Recovered approved G07 sandbox copied and verified", occurred_at=now,
                        payload={"stage_id": stage.id, "sandbox_path": existing.sandbox_path,
                                 "sandbox_fingerprint": existing.workspace_fingerprint},
                    ))
                    existing.state_version = transition.next_state_version
                    existing.event_sequence = transition.event_sequence
                    session.commit()
                actual = self._content_fingerprint(Path(existing.sandbox_path))
                if actual == "sha256:unavailable" or actual != existing.workspace_fingerprint:
                    self._fail("SANDBOX_REPLAY_MISMATCH", "The persisted sandbox contents drifted or cannot be fingerprinted.", status_code=409)
                self._verify_sandbox_evidence(run, existing)
                verification = existing.verification
                if verification is None:
                    verification = self._verification_from_workspace(existing).model_dump(mode="json")
                return StageSandboxResponse(
                    run_id=run_id, stage_id=stage_id, sandbox_path=existing.sandbox_path,
                    status="sandbox_ready" if existing.copy_status == "verified" else existing.copy_status,
                    state_version=existing.state_version,
                    event_sequence=existing.event_sequence, verification=verification, idempotent_replay=True,
                )
            return self._create_authoritative_sandbox(session, run, stage, request, now, active)


    def _create_authoritative_sandbox(self, session, run, stage, request, now, active):
        plan, stage_plan, g06, input_fingerprint, snapshot = active
        gate = session.scalar(select(G07ApprovalModel).where(
            G07ApprovalModel.run_id == run.id, G07ApprovalModel.stage_id == stage.id,
        ).order_by(G07ApprovalModel.created_at.desc()))
        if gate is None or gate.status not in {"approved", "approved_with_comment"}:
            self._fail("G07_APPROVAL_REQUIRED", "A current approved G07 decision is required before sandbox creation.", status_code=409)
        package = self._validate_current_g07(session, gate, run, stage, plan, stage_plan, g06, input_fingerprint, snapshot.id)
        destination = self._intended_destination(run, stage.id)
        bindings = self._locked_bindings(
            run, stage, plan, stage_plan, g06, input_fingerprint, destination, request.actor,
            _artifact_set_checksum(self._stage_artifacts(session, run.id, stage.id)),
        )
        binding_checksum = self._checksum(bindings)
        workspace = StageWorkspaceModel(
            id=f"wksp-{hashlib.sha256(f'{run.id}:{stage.id}'.encode()).hexdigest()[:12]}",
            run_id=run.id, stage_id=stage.id, sandbox_path=destination,
            source_fingerprint=input_fingerprint, workspace_fingerprint="sha256:pending",
            policy_version=self._policy_version, file_count=0, total_size_bytes=0,
            copy_status="pending", request_idempotency_key=request.idempotency_key,
            request_binding_checksum=binding_checksum, locked_bindings=bindings,
            verification={"status": "pending", "bindings_checksum": binding_checksum},
            verification_checksum=self._checksum({"status": "pending", "bindings_checksum": binding_checksum}),
            state_version=run.state_version, event_sequence=self._latest_event_sequence(session, run.id),
            created_at=now,
        )
        lease = None
        try:
            lease = StateTransitionService(session).acquire_lease(
                run_id=run.id, worker_id=f"stage-executor:{stage.id}", lease_owner=request.actor, now=now
            )
            session.add(workspace)
            session.flush()
            session.commit()
            workspace.copy_status = "copying"
            workspace.verification = {"status": "copying", "bindings_checksum": binding_checksum}
            session.commit()
            snapshot_root = Path(snapshot.snapshot_path)
            source_before = self._authoritative_snapshot_fingerprint(snapshot)
            if source_before == "sha256:unavailable" or source_before != input_fingerprint:
                self._fail("SOURCE_FINGERPRINT_UNAVAILABLE", "The approved source fingerprint cannot be verified before copy.", status_code=409)
            workspace_root = WorkspaceService(Path(run.run_root)).workspace_root.resolve(strict=True)
            baseline_path = workspace_root / "sandboxes" / "stages" / stage.id
            record = BaselineSandboxService().create(
                run_id=run.id, snapshot_root=snapshot_root, baseline_path=baseline_path,
                approved_snapshot_fingerprint=input_fingerprint, registered_run_root=workspace_root,
            )
            source_after = self._authoritative_snapshot_fingerprint(snapshot)
            if source_after == "sha256:unavailable" or source_after != source_before:
                self._fail("SOURCE_MUTATED_DURING_COPY", "The source changed during sandbox copy.", status_code=409)
            file_count, total_size = self._tree_stats(record.sandbox_path)
            source_count, source_size = self._copy_tree_stats(snapshot_root)
            expected_fingerprint = self._content_fingerprint(snapshot_root, copied_only=True)
            if (record.fingerprint != expected_fingerprint or file_count != source_count or
                    total_size != source_size or self._policy_version != workspace.policy_version):
                self._fail("SANDBOX_FINGERPRINT_MISMATCH", "Sandbox fingerprint, file count, or size verification failed.", status_code=409)
            pre = StageFingerprint(workspace_path=str(snapshot_root), fingerprint=input_fingerprint,
                                   policy_version=self._policy_version, file_count=source_count, total_size_bytes=source_size)
            post = StageFingerprint(workspace_path=str(record.sandbox_path), fingerprint=record.fingerprint,
                                    policy_version=self._policy_version, file_count=file_count, total_size_bytes=total_size)
            verification = StageSandboxVerification(
                stage_id=stage.id, sandbox_path=str(record.sandbox_path), pre_fingerprint=pre,
                post_fingerprint=post, verification_checksum=self._checksum({"pre": pre.model_dump(), "post": post.model_dump()}),
                verified=True,
            )
            workspace.workspace_fingerprint = record.fingerprint
            workspace.file_count, workspace.total_size_bytes = file_count, total_size
            workspace.completed_at = now
            self._persist_sandbox_evidence(
                session, run, stage, workspace, verification,
                source_path=str(snapshot_root), reconstruction=False,
            )
            workspace.verification = verification.model_dump(mode="json")
            workspace.verification_checksum = verification.verification_checksum
            workspace.copy_status = "verified"
            session.flush()
            transition = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run.id, expected_state_version=run.state_version, idempotency_key=f"{request.idempotency_key}:sandbox-ready",
                event_type=WorkflowEventType.STAGE_SANDBOX_READY, stage_id=stage.id, next_stage_status=StageStatus.SANDBOX_READY,
                actor=request.actor, reason="Approved G07 sandbox copied and verified", occurred_at=now,
                payload={"stage_id": stage.id, "sandbox_path": str(record.sandbox_path), "sandbox_fingerprint": record.fingerprint},
            ))
            workspace.state_version, workspace.event_sequence = transition.next_state_version, transition.event_sequence
            session.commit()
            return StageSandboxResponse(run_id=run.id, stage_id=stage.id, sandbox_path=str(record.sandbox_path), status=StageStatus.SANDBOX_READY.value,
                                        state_version=transition.next_state_version, event_sequence=transition.event_sequence,
                                        verification=verification.model_dump(mode="json"))
        except Exception as error:
            if workspace.copy_status in {"pending", "copying"}:
                workspace.copy_status = "interrupted" if isinstance(error, (BaselineCopyCancelled, KeyboardInterrupt)) else "failed"
                workspace.verification = {"status": workspace.copy_status, "reason": str(error), "bindings_checksum": binding_checksum}
                workspace.verification_checksum = self._checksum(workspace.verification)
                session.flush()
                session.commit()
            raise error if isinstance(error, StageApplicationError) else StageApplicationError("SANDBOX_COPY_FAILED", str(error), status_code=409)
        finally:
            if lease is not None:
                try:
                    StateTransitionService(session).release_lease(lease_id=lease.id, worker_id=lease.worker_id)
                    session.commit()
                except LeaseRequiredError:
                    session.rollback()

    @staticmethod
    def _tree_stats(path: Path) -> tuple[int, int]:
        files = [item for item in path.rglob("*") if item.is_file()]
        return len(files), sum(item.stat().st_size for item in files)

    def _persist_sandbox_evidence(self, session, run, stage, workspace, verification, *, source_path: str, reconstruction: bool) -> None:
        """Write checksum-bound sandbox evidence before the ready transition."""
        store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
        copy_payload = {
            "run_id": run.id,
            "stage_id": stage.id,
            "workspace_id": workspace.id,
            "correlation_id": stage.id,
            "source": {"path": source_path, "fingerprint": workspace.source_fingerprint},
            "workspace": {"path": workspace.sandbox_path, "fingerprint": workspace.workspace_fingerprint},
            "copy_result": "verified",
            "file_count": workspace.file_count,
            "total_size_bytes": workspace.total_size_bytes,
            "reconstruction": reconstruction,
            "recovery": {"detected_incomplete": reconstruction, "reconstruction_invoked": reconstruction},
            "created_at": workspace.created_at.isoformat(),
        }
        copy_stored = store.write_text_artifact(
            run.id, f"stages/{stage.id}/sandbox_copy_report.json",
            json.dumps(copy_payload, sort_keys=True, separators=(",", ":"), default=str), ArtifactType.JSON,
            stage_id=stage.id, created_by="stage-preparation-service", created_at=workspace.created_at,
            input_hashes={"source_fingerprint": workspace.source_fingerprint}, policy_version=self._policy_version,
        )
        self._verify_stored_artifact(copy_stored, copy_stored.ref.checksum)
        self._persist_artifact_metadata(session, copy_stored)
        verification_payload = {
            "run_id": run.id,
            "stage_id": stage.id,
            "workspace_id": workspace.id,
            "correlation_id": stage.id,
            "source_fingerprint": verification.pre_fingerprint.fingerprint,
            "sandbox_fingerprint": verification.post_fingerprint.fingerprint,
            "file_count": verification.post_fingerprint.file_count,
            "total_size_bytes": verification.post_fingerprint.total_size_bytes,
            "verified": verification.verified,
            "workspace_path": verification.sandbox_path,
            "copy_report_artifact_id": copy_stored.ref.artifact_id,
            "copy_report_checksum": copy_stored.ref.checksum,
            "recovery": {"detected_incomplete": reconstruction, "reconstruction_invoked": reconstruction},
        }
        verification_stored = store.write_text_artifact(
            run.id, f"stages/{stage.id}/sandbox_verification.json",
            json.dumps(verification_payload, sort_keys=True, separators=(",", ":"), default=str), ArtifactType.JSON,
            stage_id=stage.id, created_by="stage-preparation-service", created_at=workspace.completed_at,
            input_hashes={"copy_report_checksum": copy_stored.ref.checksum}, policy_version=self._policy_version,
        )
        self._verify_stored_artifact(verification_stored, verification_stored.ref.checksum)
        self._persist_artifact_metadata(session, verification_stored)
        workspace.copy_report_artifact_id = copy_stored.ref.artifact_id
        workspace.copy_report_artifact_checksum = copy_stored.ref.checksum
        workspace.verification_artifact_id = verification_stored.ref.artifact_id
        workspace.verification_artifact_checksum = verification_stored.ref.checksum
        session.flush()

    def _verify_sandbox_evidence(self, run, workspace) -> None:
        if not all((workspace.copy_report_artifact_id, workspace.copy_report_artifact_checksum,
                    workspace.verification_artifact_id, workspace.verification_artifact_checksum)):
            self._fail("SANDBOX_EVIDENCE_MISSING", "The verified sandbox has no immutable evidence references.", status_code=409)
        store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
        try:
            copy_stored = store.read_artifact_by_id(workspace.copy_report_artifact_id)
            verification_stored = store.read_artifact_by_id(workspace.verification_artifact_id)
        except (FileNotFoundError, OSError, ValueError) as error:
            self._fail("SANDBOX_EVIDENCE_MISSING", str(error), status_code=409)
        self._verify_stored_artifact(copy_stored, workspace.copy_report_artifact_checksum)
        self._verify_stored_artifact(verification_stored, workspace.verification_artifact_checksum)
        try:
            copy_payload = json.loads(copy_stored.content)
            verification_payload = json.loads(verification_stored.content)
        except json.JSONDecodeError as error:
            self._fail("SANDBOX_EVIDENCE_INVALID", str(error), status_code=409)
        if (copy_payload.get("correlation_id") != workspace.stage_id or
                verification_payload.get("correlation_id") != workspace.stage_id or
                verification_payload.get("copy_report_artifact_id") != workspace.copy_report_artifact_id or
                verification_payload.get("copy_report_checksum") != workspace.copy_report_artifact_checksum):
            self._fail("SANDBOX_EVIDENCE_INVALID", "Sandbox evidence does not match the durable workspace chain.", status_code=409)

    def _persist_artifact_metadata(self, session, stored) -> None:
        metadata_id = f"metadata-{stored.ref.artifact_id}"
        session.add(ArtifactMetadataModel(
            id=metadata_id, run_id=stored.ref.run_id, stage_id=stored.ref.stage_id,
            artifact_type=stored.ref.artifact_type.value, relative_path=stored.ref.relative_path,
            checksum=stored.ref.checksum, created_at=stored.ref.created_at,
        ))

    def _verify_stored_artifact(self, stored, expected_checksum: str) -> None:
        if stored.ref.checksum != expected_checksum or self._content_checksum(stored.content) != expected_checksum:
            self._fail("ARTIFACT_TAMPERED", "Sandbox evidence checksum verification failed.", status_code=409)

    @staticmethod
    def _copy_tree_stats(path: Path) -> tuple[int, int]:
        files = [
            item for item in path.rglob("*")
            if item.is_file() and item.name not in {"source-manifest.json", "snapshot-fingerprint.json"}
            and not (item.relative_to(path).parts and item.relative_to(path).parts[0] in {"node_modules", ".angular", "dist", "coverage"})
        ]
        return len(files), sum(item.stat().st_size for item in files)

    @staticmethod
    def _authoritative_snapshot_fingerprint(snapshot) -> str:
        try:
            return SnapshotService(Path(snapshot.snapshot_path).parent).inspect_snapshot(snapshot.id).fingerprint
        except (OSError, ValueError):
            return "sha256:unavailable"

    def get_g07(self, run_id: str, stage_id: str, actor: str | None = None) -> G07ReviewResponse | None:
        """Get the current G07 gate status for a stage."""
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise StageApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            if actor is not None:
                self._authorize_run(run, actor)
            record = session.scalar(
                select(G07ApprovalModel)
                .where(G07ApprovalModel.run_id == run_id, G07ApprovalModel.stage_id == stage_id)
                .order_by(G07ApprovalModel.created_at.desc())
            )
            return self._g07_dto(record) if record else None

    def decide_g07(self, run_id: str, stage_id: str, request) -> G07ReviewResponse:
        """Decide the G07 approval gate for a stage."""
        if request.gate_id != self.GATE_ID:
            raise StageApplicationError("GATE_NOT_FOUND", "Only G07 is supported by this endpoint.", status_code=404)
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise StageApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            self._authorize_run(run, request.actor)
            stage = session.get(MigrationStageModel, stage_id)
            if stage is None or stage.run_id != run_id:
                raise StageApplicationError("STAGE_NOT_FOUND", "Stage does not exist.", status_code=404)
            try:
                active = self._resolve_active_plan(session, run_id, self._stage_authority_key(session, stage))
            except StageApplicationError as error:
                gate = session.scalar(select(G07ApprovalModel).where(
                    G07ApprovalModel.run_id == run_id, G07ApprovalModel.stage_id == stage_id,
                ).order_by(G07ApprovalModel.created_at.desc()))
                if gate is not None and gate.status in {"pending", "approved", "approved_with_comment"}:
                    self._invalidate_g07(session, gate, error.code)
                raise
            plan, active_stage_plan, current_g06, input_fingerprint, snapshot = active

            # Check for existing idempotent decision only after current authority validation.
            history = session.scalar(
                select(G07DecisionHistoryModel).where(
                    G07DecisionHistoryModel.run_id == run_id,
                    G07DecisionHistoryModel.idempotency_key == request.idempotency_key,
                )
            )
            if history is not None:
                existing = session.get(G07ApprovalModel, history.gate_id)
                if existing is None:
                    self._fail("G07_HISTORY_GATE_MISSING", "The historical decision gate is missing.", status_code=409)
                package = G07ApprovalPackage.model_validate(existing.package)
                checksum = self._checksum({
                    "run_id": run_id, "stage_id": stage_id, "actor": request.actor,
                    "decision": request.decision.value, "comment": request.comment,
                    "package_checksum": package.package_checksum,
                })
                if history.request_checksum != checksum:
                    self._fail("IDEMPOTENCY_PAYLOAD_MISMATCH", "The idempotency key was already used with a different payload.", status_code=409)
                self._validate_current_g07(
                    session, existing, run, stage, plan, active_stage_plan, current_g06,
                    input_fingerprint, snapshot.id, require_approved=False,
                )
                return self._g07_dto(existing, replay=True, decision_id=history.id)
            if run.state_version != request.expected_state_version:
                raise StageApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)

            gate = session.scalar(select(G07ApprovalModel).where(
                G07ApprovalModel.run_id == run_id, G07ApprovalModel.stage_id == stage_id,
            ).order_by(G07ApprovalModel.created_at.desc()))
            if gate is None:
                self._fail("G07_NOT_FOUND", "The current G07 package was not found.", status_code=409)
            if gate.status != "pending":
                self._fail("G07_NOT_PENDING", "The current G07 package requires a newly current package before another decision.", status_code=409)
            package = G07ApprovalPackage.model_validate(gate.package)
            if package.package_checksum != gate.package_checksum or package.workspace_fingerprint is not None:
                self._fail("G07_PACKAGE_INVALID", "The current G07 package checksum or boundary is invalid.", status_code=409)
            self._validate_current_g07(session, gate, run, stage, plan, active_stage_plan, current_g06, input_fingerprint, snapshot.id, require_approved=False)
            try:
                result = G07ApprovalService().decide(package, request.decision, comment=request.comment)
            except ValueError as error:
                self._fail("G07_DECISION_INVALID", str(error))
            decision_checksum = self._checksum({
                "run_id": run_id, "stage_id": stage_id, "actor": request.actor,
                "decision": request.decision.value, "comment": request.comment,
                "package_checksum": package.package_checksum,
            })
            try:
                lease = StateTransitionService(session).acquire_lease(
                    run_id=run_id, worker_id=f"stage-reviewer:{stage_id}", lease_owner=request.actor, now=now
                )
                event_type = {
                    G07Decision.APPROVED: WorkflowEventType.G07_APPROVED,
                    G07Decision.APPROVED_WITH_COMMENT: WorkflowEventType.G07_APPROVED,
                    G07Decision.MODIFICATION_REQUESTED: WorkflowEventType.G07_MODIFICATION_REQUESTED,
                    G07Decision.REJECTED: WorkflowEventType.G07_REJECTED,
                }[result.decision]
                if result.stale:
                    event_type = WorkflowEventType.G07_STALE
                decision_id = f"g07d-{hashlib.sha256(f'{run_id}:{request.idempotency_key}'.encode()).hexdigest()[:48]}"
                session.add(G07DecisionHistoryModel(
                    id=decision_id,
                    run_id=run_id,
                    stage_id=stage_id,
                    gate_id=gate.id,
                    gate_version=gate.gate_version,
                    decision=result.decision.value,
                    actor=request.actor,
                    comment=request.comment,
                    payload_checksum=package.package_checksum,
                    request_checksum=decision_checksum,
                    idempotency_key=request.idempotency_key,
                    correlation_id=stage_id,
                    bindings=package.model_dump(mode="json"),
                    created_at=now,
                ))
                gate.status = result.decision.value if not result.stale else "stale"
                gate.decision = result.decision.value
                gate.actor = request.actor
                gate.comment = request.comment
                gate.decision_idempotency_key = request.idempotency_key
                gate.decision_request_checksum = decision_checksum
                gate.stale_reason = result.reason if result.stale else None
                gate.updated_at = now
                transition = StateTransitionService(session).apply_transition(TransitionRequest(
                    run_id=run_id, expected_state_version=run.state_version, idempotency_key=f"{request.idempotency_key}:decision",
                    event_type=event_type, stage_id=stage_id, actor=request.actor,
                    reason=result.reason or "G07 decision recorded", occurred_at=now,
                    payload={"stage_id": stage_id, "package_checksum": gate.package_checksum, "decision": gate.decision},
                ))
                gate.state_version = transition.next_state_version
                gate.event_sequence = transition.event_sequence
                session.flush()
                return self._g07_dto(gate, decision_id=decision_id)
            finally:
                if "lease" in locals():
                    StateTransitionService(session).release_lease(lease_id=lease.id, worker_id=lease.worker_id)


    def _g07_dto(self, record: G07ApprovalModel, *, replay: bool = False, decision_id: str | None = None) -> G07ReviewResponse:
        return G07ReviewResponse(
            run_id=record.run_id, stage_id=record.stage_id,
            gate_id=record.gate_id, gate_version=record.gate_version,
            status=record.status, decision=record.decision,
            package=record.package, state_version=record.state_version,
            event_sequence=record.event_sequence,
            idempotent_replay=replay, stale_reason=record.stale_reason,
            comment=record.comment,
            decision_id=decision_id,
        )

    @staticmethod
    def _authorize_run(run, actor: str) -> None:
        if run.actor and run.actor != actor:
            raise StageApplicationError("RUN_NOT_AUTHORIZED", "Authenticated actor is not authorized for this run.", status_code=403)

    def _dir_fingerprint(self, path: Path) -> str:
        """Compute a content-bound directory fingerprint."""
        return self._content_fingerprint(path)

    @staticmethod
    def _content_fingerprint(path: Path, *, copied_only: bool = False) -> str:
        try:
            digest = hashlib.sha256()
            files = (f for f in path.rglob("*") if f.is_file())
            if copied_only:
                files = (f for f in files if f.name not in {"source-manifest.json", "snapshot-fingerprint.json"}
                         and not (f.relative_to(path).parts and f.relative_to(path).parts[0] in {"node_modules", ".angular", "dist", "coverage"}))
            for file_path in sorted(files, key=lambda f: f.relative_to(path).as_posix()):
                digest.update(file_path.relative_to(path).as_posix().encode("utf-8"))
                digest.update(hashlib.sha256(file_path.read_bytes()).digest())
            return f"sha256:{digest.hexdigest()}"
        except OSError:
            return "sha256:unavailable"

    @staticmethod
    def _checksum(value: object) -> str:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
