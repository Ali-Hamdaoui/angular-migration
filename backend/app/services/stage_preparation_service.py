"""Application service for stage workspace preparation (S3-F05)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from shutil import copytree, ignore_patterns
from uuid import uuid4

from sqlalchemy import select

from app.api.stage_contracts import (
    G07ReviewResponse,
    StageBootstrapInstallResponse,
    StageBootstrapStatusResponse,
    StagePrepareResponse,
    StageSandboxResponse,
)
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactRefDto, ArtifactType, WorkflowEventType
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
)
from app.repositories.models import ArtifactMetadataModel, MigrationRunModel, StageStepModel
from app.repositories.models.workflow import MigrationStageModel
from app.repositories.session import session_scope
from app.repositories.stage_workspace_models import (
    G07ApprovalModel,
    StageWorkspaceModel,
)
from app.state.transition_service import StateTransitionService, TransitionRequest


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

    def __init__(self, *, session_scope_factory=session_scope, now_provider=None, policy_version: str | None = None) -> None:
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._policy_version = policy_version or self.STAGE_POLICY_VERSION

    def prepare_stage(self, run_id: str, request) -> StagePrepareResponse:
        """Create/reuse a stage record and lock its execution plan."""
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise StageApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            if run.state_version != request.expected_state_version:
                raise StageApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)

            # Create migration stage record
            stage = MigrationStageModel(
                id=f"stage-{uuid4().hex[:12]}",
                run_id=run_id,
                stage_order=1,
                source_version_family=request.source_version_family,
                target_version_family=request.target_version_family,
                status="preparing",
                current_agent=None,
                created_at=now,
            )
            session.add(stage)
            session.flush()

            # Lock execution plan
            plan_dict = {
                "stage_key": request.stage_key,
                "source_version_family": request.source_version_family,
                "target_version_family": request.target_version_family,
                "plan_version": request.plan_version,
                "plan_checksum": "",
            }
            plan_checksum = self._checksum(plan_dict)
            plan_dict["plan_checksum"] = plan_checksum
            plan = StageExecutionPlan(**plan_dict)

            # Emit STAGE_CREATED event
            transition = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=run.state_version,
                idempotency_key=f"{request.idempotency_key}:stage_created",
                event_type=WorkflowEventType.STAGE_CREATED, actor=request.actor,
                reason="Stage workspace record created", occurred_at=now,
                payload={"stage_id": stage.id, "stage_key": request.stage_key, "plan_version": request.plan_version},
            ))

            # Emit STAGE_PREPARING event
            transition2 = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=transition.next_state_version,
                idempotency_key=f"{request.idempotency_key}:preparing",
                event_type=WorkflowEventType.STAGE_PREPARING, actor=request.actor,
                reason="Stage sandbox preparation started", occurred_at=now,
                payload={"stage_id": stage.id, "stage_key": request.stage_key},
            ))

            return StagePrepareResponse(
                run_id=run_id,
                stage_id=stage.id,
                stage_key=request.stage_key,
                status="preparing",
                state_version=transition2.next_state_version,
                event_sequence=transition2.event_sequence,
                plan=plan.model_dump(mode="json"),
            )

    def create_sandbox(self, run_id: str, stage_id: str, request) -> StageSandboxResponse:
        """Create the isolated stage sandbox by copying files from the source snapshot."""
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise StageApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            stage = session.get(MigrationStageModel, stage_id)
            if stage is None or stage.run_id != run_id:
                raise StageApplicationError("STAGE_NOT_FOUND", "Stage does not exist.", status_code=404)
            if run.state_version != request.expected_state_version:
                raise StageApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)

            # Check for existing idempotent sandbox
            existing = session.scalar(
                select(StageWorkspaceModel)
                .where(StageWorkspaceModel.run_id == run_id, StageWorkspaceModel.stage_id == stage_id)
            )
            if existing is not None:
                verification = StageSandboxVerification(
                    stage_id=stage_id,
                    sandbox_path=existing.sandbox_path,
                    pre_fingerprint=StageFingerprint(
                        workspace_path=existing.sandbox_path,
                        fingerprint=existing.source_fingerprint,
                        policy_version=existing.policy_version,
                        file_count=existing.file_count,
                        total_size_bytes=existing.total_size_bytes,
                    ),
                    post_fingerprint=StageFingerprint(
                        workspace_path=existing.sandbox_path,
                        fingerprint=existing.workspace_fingerprint,
                        policy_version=existing.policy_version,
                        file_count=existing.file_count,
                        total_size_bytes=existing.total_size_bytes,
                    ),
                    verification_checksum=existing.verification_checksum or "",
                    verified=(existing.source_fingerprint == existing.workspace_fingerprint),
                )
                return StageSandboxResponse(
                    run_id=run_id, stage_id=stage_id,
                    sandbox_path=existing.sandbox_path,
                    status="waiting_approval",
                    state_version=existing.state_version,
                    event_sequence=existing.event_sequence,
                    verification=verification.model_dump(mode="json"),
                    idempotent_replay=True,
                )

            # Resolve output root and sandbox path
            output_root = run.resolved_output_root or run.target_output_path
            if not output_root:
                raise StageApplicationError("OUTPUT_ROOT_NOT_CONFIGURED", "Run output root is not configured.", status_code=409)
            run_root = run.run_root or f"{output_root}/.migration-factory/runs/{run_id}"
            sandbox_path = Path(f"{run_root}/sandboxes/stages/{stage_id}")

            if sandbox_path.exists():
                raise StageApplicationError("SANDBOX_ALREADY_EXISTS", "Stage sandbox already exists.", status_code=409)

            # Determine source path from snapshot or run source
            from app.repositories.models import SourceSnapshotModel
            snapshot = session.scalar(
                select(SourceSnapshotModel).where(SourceSnapshotModel.run_id == run_id).order_by(SourceSnapshotModel.created_at.desc())
            )
            source_path = Path(snapshot.snapshot_path) if snapshot and snapshot.snapshot_path else Path(run.source_path)
            if not source_path.exists():
                raise StageApplicationError("SOURCE_PATH_NOT_FOUND", "Source path does not exist.", status_code=409)

            # Perform copy
            try:
                sandbox_path.parent.mkdir(parents=True, exist_ok=True)
                copytree(str(source_path), str(sandbox_path), symlinks=True, ignore=ignore_patterns("node_modules", ".git", "__pycache__"))
            except OSError as e:
                raise StageApplicationError("SANDBOX_COPY_FAILED", f"Failed to copy workspace: {e}", status_code=500)

            # Fingerprint after copy
            pre_fingerprint = StageFingerprint(
                workspace_path=str(sandbox_path),
                fingerprint=self._dir_fingerprint(source_path),
                policy_version=self._policy_version,
                file_count=0,
                total_size_bytes=0,
            )
            post_fingerprint = StageFingerprint(
                workspace_path=str(sandbox_path),
                fingerprint=self._dir_fingerprint(sandbox_path),
                policy_version=self._policy_version,
                file_count=0,
                total_size_bytes=0,
            )

            workspace_service = StageWorkspaceService()
            verification = workspace_service.build_sandbox_verification(
                stage_id=stage_id,
                sandbox_path=str(sandbox_path),
                pre_fingerprint=pre_fingerprint,
                post_fingerprint=post_fingerprint,
            )

            # Store artifacts — guard against None artifact_root
            if not run.artifact_root:
                raise StageApplicationError("ARTIFACT_ROOT_NOT_CONFIGURED", "Run artifact root is not configured.", status_code=409)
            store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
            evidence_refs = []

            def write_evidence(name: str, payload: dict) -> None:
                stored = store.write_text_artifact(
                    run_id, f"stages/{stage_id}/{name}",
                    json.dumps(payload, sort_keys=True, indent=2),
                    ArtifactType.JSON, created_by="stage-prep-service", created_at=now,
                    input_hashes={"stage_id": stage_id},
                )
                evidence_refs.append(stored.ref)
                session.add(ArtifactMetadataModel(
                    id=f"metadata-{stored.ref.artifact_id}", run_id=run_id,
                    stage_id=stage_id, artifact_type=stored.ref.artifact_type.value,
                    relative_path=stored.ref.relative_path, checksum=stored.ref.checksum,
                    created_at=now,
                ))

            write_evidence("workspace_copy_report.json", {
                "source_path": str(source_path),
                "destination_path": str(sandbox_path),
                "pre_fingerprint": pre_fingerprint.model_dump(mode="json"),
                "post_fingerprint": post_fingerprint.model_dump(mode="json"),
                "verification": verification.model_dump(mode="json"),
            })

            # Emit PLAN_LOCKED event
            t1 = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=run.state_version,
                idempotency_key=f"{request.idempotency_key}:plan_locked",
                event_type=WorkflowEventType.STAGE_PLAN_LOCKED, actor=request.actor,
                reason="Stage execution plan locked", occurred_at=now,
                payload={"stage_id": stage_id, "sandbox_path": str(sandbox_path)},
            ))

            # Emit WAITING_APPROVAL
            t2 = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=t1.next_state_version,
                idempotency_key=f"{request.idempotency_key}:waiting_approval",
                event_type=WorkflowEventType.STAGE_WAITING_APPROVAL, actor=request.actor,
                reason="Stage sandbox ready - awaiting G07 approval", occurred_at=now,
                payload={"stage_id": stage_id},
            ))

            # Record workspace
            wsm = StageWorkspaceModel(
                id=f"wksp-{uuid4().hex[:12]}",
                run_id=run_id, stage_id=stage_id,
                sandbox_path=str(sandbox_path),
                source_fingerprint=pre_fingerprint.fingerprint,
                workspace_fingerprint=post_fingerprint.fingerprint,
                policy_version=self._policy_version,
                file_count=0, total_size_bytes=0,
                copy_status="completed",
                verification_checksum=verification.verification_checksum,
                state_version=t2.next_state_version,
                event_sequence=t2.event_sequence,
                created_at=now, completed_at=now,
            )
            session.add(wsm)

            stage.status = "waiting_approval"
            stage.started_at = now
            session.flush()

            return StageSandboxResponse(
                run_id=run_id, stage_id=stage_id,
                sandbox_path=str(sandbox_path),
                status="waiting_approval",
                state_version=t2.next_state_version,
                event_sequence=t2.event_sequence,
                verification=verification.model_dump(mode="json"),
            )

    def get_g07(self, run_id: str, stage_id: str) -> G07ReviewResponse | None:
        """Get the current G07 gate status for a stage."""
        with self._scope() as session:
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
            stage = session.get(MigrationStageModel, stage_id)
            if stage is None or stage.run_id != run_id:
                raise StageApplicationError("STAGE_NOT_FOUND", "Stage does not exist.", status_code=404)
            if run.state_version != request.expected_state_version:
                raise StageApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)

            # Check for existing idempotent decision
            existing = session.scalar(
                select(G07ApprovalModel)
                .where(G07ApprovalModel.run_id == run_id, G07ApprovalModel.idempotency_key == request.idempotency_key)
            )
            if existing is not None:
                return self._g07_dto(existing, replay=True)

            # Build approval package
            workspace = session.scalar(
                select(StageWorkspaceModel)
                .where(StageWorkspaceModel.run_id == run_id, StageWorkspaceModel.stage_id == stage_id)
                .order_by(StageWorkspaceModel.created_at.desc())
            )
            if workspace is None:
                raise StageApplicationError("WORKSPACE_NOT_FOUND", "Stage workspace must be created before G07 decision.", status_code=409)

            artifacts = []
            from app.domain.contracts import ArtifactRefDto
            artifact_rows = list(session.scalars(
                select(ArtifactMetadataModel).where(
                    ArtifactMetadataModel.run_id == run_id,
                    ArtifactMetadataModel.stage_id == stage_id,
                )
            ))
            for row in artifact_rows:
                aid = row.id.removeprefix("metadata-")
                artifacts.append(ArtifactRefDto(
                    artifact_id=aid, run_id=run_id, stage_id=stage_id,
                    artifact_type=ArtifactType(row.artifact_type),
                    relative_path=row.relative_path, created_at=row.created_at,
                    checksum=row.checksum,
                ))

            input_manifest = StageInputManifest(
                stage_id=stage_id, run_id=run_id,
                source_fingerprint=workspace.source_fingerprint,
                snapshot_id=run.preflight_id or f"run-{run_id}",
                plan=StageExecutionPlan(
                    stage_key=stage_id, source_version_family=stage.source_version_family or "",
                    target_version_family=stage.target_version_family or "",
                    toolchain_profile="npm-ci",
                    plan_version=workspace.policy_version,
                    plan_checksum=self._checksum({
                        "stage_key": stage_id,
                        "source_version_family": stage.source_version_family or "",
                        "target_version_family": stage.target_version_family or "",
                        "plan_version": workspace.policy_version,
                    }),
                ),
                manifest_checksum=self._checksum({"stage_id": stage_id, "fingerprint": workspace.source_fingerprint}),
            )
            copy_report = WorkspaceCopyReport(
                source_path=workspace.sandbox_path,
                destination_path=workspace.sandbox_path,  # post-copy; the original source is not stored in workspace model
                file_count=workspace.file_count,
                total_size_bytes=workspace.total_size_bytes,
                destination_fingerprint=workspace.workspace_fingerprint,
                completed_at=now.isoformat(),
            )

            builder = G07ApprovalPackageBuilder()
            package = builder.build(
                run_id=run_id, state_version=run.state_version, actor=request.actor,
                stage_id=stage_id, stage_key=stage_id,
                gate_version=self.GATE_VERSION, plan_version=workspace.policy_version,
                source_fingerprint=workspace.source_fingerprint,
                workspace_fingerprint=workspace.workspace_fingerprint,
                input_manifest=input_manifest, copy_report=copy_report,
                artifacts=artifacts,
            )

            # Apply decision rules
            result: G07ApprovalResult = G07ApprovalService().decide(package, request.decision, comment=request.comment)

            # Emit G07_CREATED before the decision event
            StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=run.state_version,
                idempotency_key=f"{request.idempotency_key}:g07_created",
                event_type=WorkflowEventType.G07_CREATED,
                actor=request.actor, reason="G07 approval package created",
                occurred_at=now,
                payload={"package_checksum": package.package_checksum, "stage_id": stage_id},
            ))

            # Determine decision event type
            if result.stale:
                event_type = WorkflowEventType.G07_STALE
            elif result.decision in {G07Decision.APPROVED, G07Decision.APPROVED_WITH_COMMENT}:
                event_type = WorkflowEventType.G07_APPROVED
            else:
                event_type = WorkflowEventType.G07_REJECTED

            transition = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=run.state_version,
                idempotency_key=request.idempotency_key, event_type=event_type,
                actor=request.actor, reason=result.reason or "G07 decision recorded",
                occurred_at=now,
                payload={"package_checksum": package.package_checksum, "decision": result.decision.value},
            ))

            # Create G07 record
            record = G07ApprovalModel(
                id=f"g07-{uuid4().hex[:12]}",
                run_id=run_id, stage_id=stage_id,
                gate_id=self.GATE_ID, gate_version=self.GATE_VERSION,
                idempotency_key=request.idempotency_key, actor=request.actor,
                status=result.decision.value, decision=result.decision.value,
                package_checksum=package.package_checksum,
                artifact_set_checksum=package.artifact_set_checksum,
                stage_key=stage_id, plan_version=workspace.policy_version,
                state_version=transition.next_state_version,
                event_sequence=transition.event_sequence,
                package=package.model_dump(mode="json"),
                artifact_ids=[item.artifact_id for item in artifacts],
                stale_reason=result.reason if result.stale else None,
                comment=request.comment,
                created_at=now, updated_at=now,
            )
            session.add(record)

            # Update stage status on approval
            if result.decision in {G07Decision.APPROVED, G07Decision.APPROVED_WITH_COMMENT}:
                stage.status = "sandbox_ready"

            # Emit SANDBOX_READY if approved
            if result.decision in {G07Decision.APPROVED, G07Decision.APPROVED_WITH_COMMENT}:
                StateTransitionService(session).apply_transition(TransitionRequest(
                    run_id=run_id, expected_state_version=transition.next_state_version,
                    idempotency_key=f"{request.idempotency_key}:sandbox_ready",
                    event_type=WorkflowEventType.STAGE_SANDBOX_READY, actor=request.actor,
                    reason="Stage sandbox ready - G07 approved", occurred_at=now,
                    payload={"stage_id": stage_id, "decision": result.decision.value, "workspace_alias": self.WORKSPACE_ALIAS},
                ))

            session.flush()
            return self._g07_dto(record)

    def _g07_dto(self, record: G07ApprovalModel, *, replay: bool = False) -> G07ReviewResponse:
        return G07ReviewResponse(
            run_id=record.run_id, stage_id=record.stage_id,
            gate_id=record.gate_id, gate_version=record.gate_version,
            status=record.status, decision=record.decision,
            package=record.package, state_version=record.state_version,
            event_sequence=record.event_sequence,
            idempotent_replay=replay, stale_reason=record.stale_reason,
            comment=record.comment,
        )

    def _dir_fingerprint(self, path: Path) -> str:
        """Compute a simple directory fingerprint."""
        try:
            entries = sorted(
                str(f.relative_to(path)) for f in path.rglob("*") if f.is_file()
            )
            payload = json.dumps(entries, sort_keys=True, separators=(",", ":"))
            return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
        except OSError:
            return "sha256:unavailable"

    @staticmethod
    def _checksum(value: object) -> str:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
