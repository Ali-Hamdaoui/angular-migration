"""Governed G08 regeneration from preserved pre-update and transformed evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.artifact_store import (
    ArtifactNotFoundError,
    ArtifactStoreError,
    LocalFilesystemArtifactStore,
)
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.domain.transformation import G08LedgerRegenerationRequest
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    MigrationPlanModel,
    MigrationRunModel,
    StageCheckpointModel,
    StageGateDecisionModel,
    StageGatePackageModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    WorkflowEventModel,
)
from app.repositories.session import session_scope
from app.services.angular_transformation_evidence_service import (
    AngularTransformationEvidenceService,
)
from app.services.g08_pre_update_evidence_resolver import (
    G08PreUpdateEvidenceError,
    G08PreUpdateEvidenceResolver,
)
from app.services.stage_gate_service import StageGateService
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformer_stage_service import TransformerStageService
from app.state import StateTransitionService


class G08LedgerRegenerationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class G08LedgerRegenerationService:
    def __init__(self, *, scope=session_scope, now_provider=None) -> None:
        self._scope = scope
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._evidence = AngularTransformationEvidenceService()
        self._g08_pre_update = G08PreUpdateEvidenceResolver()
        self._stage = TransformerStageService(scope=scope)
        self._gates = StageGateService()

    def regenerate(self, run_id: str, payload: G08LedgerRegenerationRequest, actor: str) -> dict:
        replay = self._replay(run_id, payload, actor)
        if replay is not None:
            return replay
        with self._scope() as session:
            context = self._context(session, run_id, payload, actor)

        ledger = self._regenerate_ledger(context, payload.workspace_fingerprint)
        if not ledger["changed_files"] or ledger["unattributed_files"]:
            raise G08LedgerRegenerationError(
                "G08_LEDGER_REGENERATION_INVALID",
                "Regenerated migration evidence must contain attributed transformed-file changes.",
            )
        if StageSandboxCopier.fingerprint(Path(context["workspace_path"])) != payload.workspace_fingerprint:
            raise G08LedgerRegenerationError(
                "G08_WORKSPACE_CHANGED",
                "The transformed workspace changed while the ledger was being regenerated.",
            )

        root = Path(context["artifact_root"])
        store = LocalFilesystemArtifactStore(root.parent, fixed_run_root=root)
        now = self._now()
        ledger_artifact = store.write_text_artifact(
            run_id,
            f"04_workflow_state/stages/{context['stage_id']}/transformation/migration-ledger.json",
            json.dumps(ledger, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=context["stage_id"],
            created_by="g08-ledger-regeneration",
            created_at=now,
            input_hashes={
                "pre_update_checkpoint": context["checkpoint_fingerprint"],
                "transformed_workspace": payload.workspace_fingerprint,
                "version_evidence": payload.version_evidence_checksum,
            },
            policy_version="g08-ledger-regeneration-v1",
        )
        package_payload = {
            "gate_id": "G08",
            "run_id": run_id,
            "stage_id": context["stage_id"],
            "plan_version": context["plan_version"],
            "stage_plan_checksum": context["stage_plan_checksum"],
            "workspace_fingerprint": payload.workspace_fingerprint,
            "version_evidence_artifact_id": context["version_artifact_id"],
            "version_evidence_checksum": payload.version_evidence_checksum,
            "migration_ledger_artifact_id": ledger_artifact.ref.artifact_id,
            "migration_ledger_checksum": ledger_artifact.ref.checksum,
            "regenerated_from_gate_package_id": context["old_gate_id"],
            "superseded_gate_package_id": context["superseded_gate_id"],
            "pre_update_checkpoint_id": context["checkpoint_id"],
            "pre_update_checkpoint_fingerprint": context["checkpoint_fingerprint"],
        }
        gate_artifact = self._stage.write_gate_package(
            run_id=run_id,
            stage_id=context["stage_id"],
            artifact_root=context["artifact_root"],
            gate_id="G08",
            payload=package_payload,
        )

        with self._scope() as session:
            current = self._context(session, run_id, payload, actor)
            if StageSandboxCopier.fingerprint(Path(current["workspace_path"])) != payload.workspace_fingerprint:
                raise G08LedgerRegenerationError(
                    "G08_WORKSPACE_CHANGED",
                    "The transformed workspace changed before regenerated evidence could be committed.",
                )
            continuation = current["continuation"]
            superseded_gate = current["superseded_gate"]
            if superseded_gate is not None:
                superseded_gate.status = "stale"
                superseded_gate.stale_at = now
                StateTransitionService(session).append_audit_event(
                    run_id=run_id,
                    idempotency_key=f"{payload.idempotency_key}:stale:{superseded_gate.id}",
                    event_type=WorkflowEventType.G08_STALE,
                    actor=actor,
                    reason="G08 ledger package superseded after repository metadata exclusion defect",
                    occurred_at=now,
                    payload={
                        "gate_package_id": superseded_gate.id,
                        "package_checksum": superseded_gate.package_checksum,
                        "workspace_fingerprint": payload.workspace_fingerprint,
                    },
                )
            rejected_gate = current["old_gate"]
            rejected_gate.status = "stale"
            rejected_gate.stale_at = now
            StateTransitionService(session).append_audit_event(
                run_id=run_id,
                idempotency_key=f"{payload.idempotency_key}:stale:{rejected_gate.id}",
                event_type=WorkflowEventType.G08_STALE,
                actor=actor,
                reason="defective G08 ledger package superseded by governed regeneration",
                occurred_at=now,
                payload={
                    "gate_package_id": rejected_gate.id,
                    "package_checksum": rejected_gate.package_checksum,
                    "workspace_fingerprint": payload.workspace_fingerprint,
                },
            )
            for artifact in (ledger_artifact, gate_artifact):
                self._stage.register_artifact(session, artifact, continuation)
            gate = self._gates.create(
                session,
                continuation,
                gate_id="G08",
                package_artifact_id=gate_artifact.ref.artifact_id,
                package_checksum=gate_artifact.ref.checksum,
                artifact_set_checksum=self._stage.checksum(
                    {
                        current["version_artifact_id"]: payload.version_evidence_checksum,
                        ledger_artifact.ref.artifact_id: ledger_artifact.ref.checksum,
                        gate_artifact.ref.artifact_id: gate_artifact.ref.checksum,
                    }
                ),
                workspace_fingerprint=payload.workspace_fingerprint,
            )
            StateTransitionService(session).append_audit_event(
                run_id=run_id,
                idempotency_key=payload.idempotency_key,
                event_type=WorkflowEventType.G08_LEDGER_REGENERATED,
                actor=actor,
                reason="G08 migration ledger regenerated from genuine pre-update evidence",
                occurred_at=now,
                payload={
                    "request_checksum": self._request_checksum(run_id, payload, actor),
                    "gate_package_id": gate.id,
                    "rejected_gate_package_id": current["old_gate_id"],
                    "superseded_gate_package_id": current["superseded_gate_id"],
                    "ledger_artifact_id": ledger_artifact.ref.artifact_id,
                    "changed_file_count": ledger["changed_file_count"],
                    "workspace_fingerprint": payload.workspace_fingerprint,
                },
            )
            return self._response(gate, ledger_artifact.ref, ledger, replay=False)

    def _regenerate_ledger(self, context: dict, workspace_fingerprint: str) -> dict:
        """Rebuild only the ledger; transformation and version proof remain immutable."""
        return self._evidence.migration_ledger(
            context["baseline_path"],
            context["workspace_path"],
            angular_execution_id=context["angular_execution_id"],
            expected_pre_fingerprint=context["checkpoint_fingerprint"],
            expected_post_fingerprint=workspace_fingerprint,
        )

    def _context(self, session, run_id, payload, actor):
        run = session.get(MigrationRunModel, run_id)
        continuation = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id
            )
        )
        if run is None:
            raise G08LedgerRegenerationError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
        if run.actor and run.actor != actor:
            raise G08LedgerRegenerationError("RUN_NOT_AUTHORIZED", "Migration run is not owned by this actor.", 403)
        correction_mode = bool(payload.superseded_package_checksum)
        blocked_modification = (
            continuation is not None
            and continuation.status == "blocked"
            and continuation.current_node == "wait_g08"
            and continuation.last_error_code == "G08_REQUEST_MODIFICATION"
            and not correction_mode
        )
        pending_correction = (
            continuation is not None
            and continuation.status == "waiting_gate"
            and continuation.current_node == "wait_g08"
            and correction_mode
        )
        if (
            continuation is None
            or continuation.state_version != payload.expected_state_version
            or not (blocked_modification or pending_correction)
        ):
            raise G08LedgerRegenerationError(
                "G08_LEDGER_REGENERATION_NOT_ELIGIBLE",
                "Continuation is not at the exact requested G08 modification boundary.",
            )
        old_gate = session.scalar(
            select(StageGatePackageModel).where(
                StageGatePackageModel.run_id == run_id,
                StageGatePackageModel.stage_id == continuation.current_stage_id,
                StageGatePackageModel.gate_id == "G08",
                StageGatePackageModel.status == "rejected",
                StageGatePackageModel.package_checksum == payload.rejected_package_checksum,
            )
        )
        decision = session.scalar(
            select(StageGateDecisionModel).where(
                StageGateDecisionModel.gate_package_id == old_gate.id if old_gate else False,
                StageGateDecisionModel.decision == "request_modification",
            )
        )
        superseded_gate = None
        if pending_correction:
            superseded_gate = session.scalar(
                select(StageGatePackageModel).where(
                    StageGatePackageModel.run_id == run_id,
                    StageGatePackageModel.stage_id == continuation.current_stage_id,
                    StageGatePackageModel.gate_id == "G08",
                    StageGatePackageModel.status == "pending",
                    StageGatePackageModel.package_checksum
                    == payload.superseded_package_checksum,
                )
            )
            superseded_decision = session.scalar(
                select(StageGateDecisionModel).where(
                    StageGateDecisionModel.gate_package_id
                    == superseded_gate.id
                    if superseded_gate
                    else False,
                )
            )
            if superseded_gate is None or superseded_decision is not None:
                raise G08LedgerRegenerationError(
                    "G08_SUPERSESSION_BINDING_MISMATCH",
                    "The unapproved regenerated G08 package is missing, changed, or decided.",
                )
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        if (
            old_gate is None
            or decision is None
            or old_gate.workspace_fingerprint != payload.workspace_fingerprint
            or binding is None
            or StageSandboxCopier.fingerprint(Path(binding.workspace_path))
            != payload.workspace_fingerprint
        ):
            raise G08LedgerRegenerationError(
                "G08_REJECTED_PACKAGE_BINDING_MISMATCH",
                "Rejected G08 decision or transformed workspace binding is stale.",
            )
        package = self._artifact_json(session, run, old_gate.package_artifact_id, old_gate.package_checksum)
        version_id = package.get("version_evidence_artifact_id")
        ledger_id = package.get("migration_ledger_artifact_id")
        if (
            package.get("version_evidence_checksum") != payload.version_evidence_checksum
            or not isinstance(version_id, str)
            or not isinstance(ledger_id, str)
        ):
            raise G08LedgerRegenerationError(
                "G08_VERSION_EVIDENCE_BINDING_MISMATCH",
                "Rejected G08 does not contain the expected preserved version evidence.",
            )
        versions = self._artifact_json(session, run, version_id, payload.version_evidence_checksum)
        old_ledger = self._artifact_json(
            session, run, ledger_id, str(package.get("migration_ledger_checksum"))
        )
        if superseded_gate is not None:
            superseded_package = self._artifact_json(
                session,
                run,
                superseded_gate.package_artifact_id,
                superseded_gate.package_checksum,
            )
            superseded_ledger_id = superseded_package.get("migration_ledger_artifact_id")
            if (
                superseded_package.get("regenerated_from_gate_package_id") != old_gate.id
                or superseded_package.get("version_evidence_artifact_id") != version_id
                or superseded_package.get("version_evidence_checksum")
                != payload.version_evidence_checksum
                or not isinstance(superseded_ledger_id, str)
            ):
                raise G08LedgerRegenerationError(
                    "G08_SUPERSESSION_BINDING_MISMATCH",
                    "The unapproved regenerated G08 lineage does not match preserved evidence.",
                )
            superseded_ledger = self._artifact_json(
                session,
                run,
                superseded_ledger_id,
                str(superseded_package.get("migration_ledger_checksum")),
            )
            changed_files = superseded_ledger.get("changed_files") or []
            if not any(
                isinstance(item, dict)
                and (
                    item.get("path") == ".git"
                    or str(item.get("path") or "").startswith(".git/")
                )
                for item in changed_files
            ):
                raise G08LedgerRegenerationError(
                    "G08_SUPERSESSION_NOT_ELIGIBLE",
                    "Only an undecided G08 ledger containing repository metadata may be superseded.",
                )
        plan = session.get(MigrationPlanModel, continuation.plan_id)
        angular_step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "angular_update-0",
            )
        )
        execution = (
            session.get(CommandExecutionModel, angular_step.execution_id)
            if angular_step is not None and angular_step.execution_id
            else None
        )
        checkpoint = (
            session.get(StageCheckpointModel, execution.checkpoint_id)
            if execution is not None and execution.checkpoint_id
            else None
        )
        try:
            pre_update = self._g08_pre_update.resolve(
                session, run, continuation, checkpoint
            )
        except G08PreUpdateEvidenceError as error:
            raise G08LedgerRegenerationError(error.code, error.message) from error
        source_path = Path(pre_update.path)
        source_lineage_valid = (
            source_path.is_dir()
            and StageSandboxCopier.fingerprint(source_path) == pre_update.fingerprint
        )
        if (
            versions.get("status") != "verified"
            or old_ledger.get("changed_file_count") != 0
            or not source_lineage_valid
            or plan is None
        ):
            raise G08LedgerRegenerationError(
                "G08_PRE_UPDATE_EVIDENCE_UNAVAILABLE",
                "Genuine pre-update evidence or preserved target-version evidence is unavailable.",
            )
        return {
            "run": run,
            "continuation": continuation,
            "stage_id": continuation.current_stage_id,
            "workspace_path": binding.workspace_path,
            "artifact_root": run.artifact_root,
            "baseline_path": str(source_path.resolve(strict=True)),
            "checkpoint_id": pre_update.checkpoint_id,
            "checkpoint_fingerprint": pre_update.fingerprint,
            "angular_execution_id": execution.id,
            "version_artifact_id": version_id,
            "old_gate": old_gate,
            "old_gate_id": old_gate.id,
            "superseded_gate": superseded_gate,
            "superseded_gate_id": superseded_gate.id if superseded_gate else None,
            "plan_version": plan.version,
            "stage_plan_checksum": continuation.stage_plan_checksum,
        }

    @staticmethod
    def _artifact_json(session, run, artifact_id: str, checksum: str) -> dict:
        metadata = session.get(ArtifactMetadataModel, f"metadata-{artifact_id}")
        if (
            metadata is None
            or metadata.run_id != run.id
            or not metadata.immutable
            or metadata.checksum != checksum
        ):
            raise G08LedgerRegenerationError(
                "G08_ARTIFACT_BINDING_MISMATCH", "Required immutable G08 evidence is stale."
            )
        store = LocalFilesystemArtifactStore(
            Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
        )
        try:
            stored = store.read_artifact(run.id, metadata.relative_path)
            value = json.loads(stored.content)
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, json.JSONDecodeError) as error:
            raise G08LedgerRegenerationError(
                "G08_ARTIFACT_BINDING_MISMATCH", "Stored G08 evidence is unavailable or invalid."
            ) from error
        if stored.ref.checksum != checksum:
            raise G08LedgerRegenerationError(
                "G08_ARTIFACT_BINDING_MISMATCH", "Stored G08 evidence checksum changed."
            )
        if not isinstance(value, dict):
            raise G08LedgerRegenerationError(
                "G08_ARTIFACT_BINDING_MISMATCH", "Stored G08 evidence is invalid."
            )
        return value

    def _replay(self, run_id, payload, actor):
        with self._scope() as session:
            event = session.scalar(
                select(WorkflowEventModel).where(
                    WorkflowEventModel.run_id == run_id,
                    WorkflowEventModel.idempotency_key == payload.idempotency_key,
                    WorkflowEventModel.event_type == WorkflowEventType.G08_LEDGER_REGENERATED.value,
                )
            )
            if event is None:
                return None
            if (event.payload or {}).get("request_checksum") != self._request_checksum(run_id, payload, actor):
                raise G08LedgerRegenerationError(
                    "IDEMPOTENCY_PAYLOAD_MISMATCH", "Regeneration key was used with another payload."
                )
            gate = session.get(StageGatePackageModel, (event.payload or {})["gate_package_id"])
            metadata = session.get(
                ArtifactMetadataModel, f"metadata-{(event.payload or {})['ledger_artifact_id']}"
            )
            return self._response(gate, metadata, event.payload or {}, replay=True)

    @staticmethod
    def _response(gate, ledger_ref, ledger, *, replay):
        return {
            "run_id": gate.run_id,
            "stage_id": gate.stage_id,
            "gate_package_id": gate.id,
            "gate_version": gate.gate_version,
            "gate_status": gate.status,
            "package_artifact_id": gate.package_artifact_id,
            "package_checksum": gate.package_checksum,
            "artifact_set_checksum": gate.artifact_set_checksum,
            "workspace_fingerprint": gate.workspace_fingerprint,
            "expected_state_version": gate.expected_state_version,
            "ledger_artifact_id": getattr(ledger_ref, "artifact_id", None)
            or str(ledger_ref.id).removeprefix("metadata-"),
            "ledger_checksum": ledger_ref.checksum,
            "changed_file_count": ledger["changed_file_count"],
            "idempotent_replay": replay,
        }

    @staticmethod
    def _request_checksum(run_id, payload, actor):
        return "sha256:" + hashlib.sha256(
            json.dumps(
                {
                    "run_id": run_id,
                    "actor": actor,
                    **payload.model_dump(mode="json", exclude_none=True),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
