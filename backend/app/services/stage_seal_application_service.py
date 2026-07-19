"""Application service for S3-F14 stage seal (G12) and copy-forward."""
from __future__ import annotations
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from sqlalchemy import func, select
from app.artifact_store.local_store import LocalFilesystemArtifactStore
from app.domain.stage_seal import StageSealService, G12Decision, OutputFingerprint
from app.domain.stage_copy_forward import StageCopyForwardService, CopyForwardManifest, CopyForwardStatus
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.repositories.models import ArtifactMetadataModel, MigrationRunModel, WorkflowEventModel
from app.repositories.models.workflow import (
    StageSealModel, ApprovalGateModel, StageCopyForwardRecord,
    OutputFingerprintModel, MigrationStageModel,
)
from app.repositories.session import session_scope
from app.state.transition_service import StaleStateVersionError, StateTransitionService, TransitionRequest


class StageSealApplicationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class StageSealApplicationService:
    def __init__(self, *, scope=session_scope, seal_service=None, copy_service=None, now_provider=None):
        self._scope = scope
        self._seal_service = seal_service or StageSealService()
        self._copy_service = copy_service or StageCopyForwardService()
        self._now = now_provider or (lambda: datetime.now(UTC))

    def seal_stage(self, run_id: str, stage_id: str, request):
        from app.api.stage_seal_contracts import StageSealResponse

        with self._scope() as session:
            run, stage = self._run_and_stage(session, run_id, stage_id)
            replay = session.scalar(
                select(StageSealModel).where(
                    StageSealModel.run_id == run_id,
                    StageSealModel.stage_id == stage_id,
                    StageSealModel.idempotency_key == request.idempotency_key,
                )
            )
            if replay:
                return self._seal_response(replay, replay=True)

            self._require_state(run, request.expected_state_version)

            # Cleanup started
            self._transition(
                session, run, request,
                WorkflowEventType.STAGE_CLEANUP_STARTED,
                "stage cleanup started",
                {"stage_id": stage_id},
            )

            # Compute fingerprint
            fingerprint_id = f"fp-{uuid4().hex[:12]}"
            fingerprint = self._seal_service.compute_fingerprint(
                fingerprint_id=fingerprint_id,
                run_id=run_id,
                stage_id=stage_id,
                output_path=f"stages/{stage_id}/output",
                files=[],
            )
            fp_record = OutputFingerprintModel(
                id=fingerprint_id,
                run_id=run_id,
                stage_id=stage_id,
                relative_path=fingerprint.relative_path,
                size_bytes=fingerprint.size_bytes,
                checksum=fingerprint.checksum,
                file_count=fingerprint.file_count,
                created_at=self._now(),
            )
            session.add(fp_record)

            # Plan cleanup
            cleanup = self._seal_service.plan_cleanup(fingerprint, [])

            # Cleanup completed
            self._transition(
                session, run, request,
                WorkflowEventType.STAGE_CLEANUP_COMPLETED,
                "stage cleanup completed",
                {"stage_id": stage_id, "paths_cleaned": len(cleanup.paths_cleaned), "bytes_freed": cleanup.total_bytes_freed},
                expected_state_version=run.state_version,
            )

            seal = StageSealModel(
                id=f"stage-seal-{uuid4().hex[:12]}",
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key=request.idempotency_key,
                actor=request.actor,
                status="sealed",
                output_fingerprint={"fingerprint_id": fingerprint_id, "checksum": fingerprint.checksum, "file_count": fingerprint.file_count, "size_bytes": fingerprint.size_bytes, "relative_path": fingerprint.relative_path},
                completeness_report={"paths_cleaned": list(cleanup.paths_cleaned), "total_bytes_freed": cleanup.total_bytes_freed, "errors": list(cleanup.errors)},
                artifact_ids=[],
                artifact_checksums={},
                state_version=run.state_version,
                event_sequence=self._latest_sequence(session, run_id),
                created_at=self._now(),
                updated_at=self._now(),
            )
            session.add(seal)
            session.flush()

            report_id = self._write_seal_report(session, run, stage_id, seal, request.idempotency_key)
            seal.artifact_ids = [report_id]
            seal.artifact_checksums = {report_id: self._artifact_checksum(run, report_id)}
            seal.state_version = run.state_version
            seal.event_sequence = self._latest_sequence(session, run_id)
            seal.updated_at = self._now()
            session.flush()

            return self._seal_response(seal)

    def create_g12_gate(self, run_id: str, stage_id: str, request):
        from app.api.stage_seal_contracts import G12GateResponse

        with self._scope() as session:
            run, stage = self._run_and_stage(session, run_id, stage_id)
            self._require_state(run, request.expected_state_version)

            gate_id = f"g12-{uuid4().hex[:12]}"
            gate = ApprovalGateModel(
                id=gate_id,
                run_id=run_id,
                stage_id=stage_id,
                gate_type="G12",
                status="pending",
                decision=None,
                actor=request.actor,
                comment=None,
                state_version=run.state_version,
                event_sequence=self._latest_sequence(session, run_id),
                created_at=self._now(),
                updated_at=self._now(),
            )
            session.add(gate)
            session.flush()

            self._transition(
                session, run, request,
                WorkflowEventType.G12_CREATED,
                "G12 seal gate created",
                {"stage_id": stage_id, "gate_id": gate_id},
            )

            return G12GateResponse(
                gate_id=gate_id,
                run_id=run_id,
                stage_id=stage_id,
                status="pending",
                decision="pending",
                state_version=run.state_version,
                event_sequence=gate.event_sequence,
            )

    def approve_g12(self, run_id: str, stage_id: str, request):
        return self._decide_g12(run_id, stage_id, request, WorkflowEventType.G12_APPROVED)

    def reject_g12(self, run_id: str, stage_id: str, request):
        return self._decide_g12(run_id, stage_id, request, WorkflowEventType.G12_REJECTED)

    def _decide_g12(self, run_id: str, stage_id: str, request, event_type):
        from app.api.stage_seal_contracts import G12GateResponse

        with self._scope() as session:
            run, stage = self._run_and_stage(session, run_id, stage_id)
            gate = session.scalar(
                select(ApprovalGateModel).where(
                    ApprovalGateModel.id == request.gate_id,
                    ApprovalGateModel.run_id == run_id,
                )
            )
            if gate is None:
                raise StageSealApplicationError("GATE_NOT_FOUND", "Gate was not found.", 404)

            gate.status = "decided"
            gate.decision = request.decision
            gate.comment = request.rationale
            gate.updated_at = self._now()
            session.flush()

            self._transition(
                session, run, request,
                event_type,
                f"G12 gate {gate.id} decision: {request.decision}",
                {"stage_id": stage_id, "gate_id": gate.id, "decision": request.decision},
            )

            return G12GateResponse(
                gate_id=gate.id,
                run_id=run_id,
                stage_id=stage_id,
                status=gate.status,
                decision=request.decision,
                state_version=run.state_version,
                event_sequence=self._latest_sequence(session, run_id),
            )

    def get_g12_gate(self, run_id: str, stage_id: str):
        from app.api.stage_seal_contracts import G12GateResponse

        with self._scope() as session:
            gate = session.scalar(
                select(ApprovalGateModel).where(
                    ApprovalGateModel.run_id == run_id,
                    ApprovalGateModel.stage_id == stage_id,
                    ApprovalGateModel.gate_type == "G12",
                ).order_by(ApprovalGateModel.created_at.desc())
            )
            if gate is None:
                return None
            return G12GateResponse(
                gate_id=gate.id,
                run_id=run_id,
                stage_id=stage_id,
                status=gate.status,
                decision=gate.decision or "pending",
                state_version=gate.state_version,
                event_sequence=gate.event_sequence,
            )

    def copy_forward(self, run_id: str, source_stage_id: str, target_stage_id: str, request):
        from app.api.stage_seal_contracts import StageSealResponse

        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise StageSealApplicationError("RUN_NOT_FOUND", "Migration run was not found.", 404)
            self._require_state(run, request.expected_state_version)

            manifest_id = f"cf-{uuid4().hex[:12]}"
            manifest = self._copy_service.resolve_copy_manifest(
                manifest_id=manifest_id,
                run_id=run_id,
                source_stage_id=source_stage_id,
                target_stage_id=target_stage_id,
                source_sandbox="/tmp",
                target_sandbox="/tmp",
            )

            self._transition(
                session, run, request,
                WorkflowEventType.COPY_FORWARD_STARTED,
                "copy-forward started",
                {"source_stage_id": source_stage_id, "target_stage_id": target_stage_id},
            )

            cf_record = StageCopyForwardRecord(
                id=manifest_id,
                run_id=run_id,
                source_stage_id=source_stage_id,
                target_stage_id=target_stage_id,
                manifest=manifest,
                status="completed",
                artifact_ids=[],
                state_version=run.state_version,
                event_sequence=self._latest_sequence(session, run_id),
                created_at=self._now(),
                updated_at=self._now(),
            )
            session.add(cf_record)
            session.flush()

            self._transition(
                session, run, request,
                WorkflowEventType.COPY_FORWARD_COMPLETED,
                "copy-forward completed",
                {"source_stage_id": source_stage_id, "target_stage_id": target_stage_id},
                expected_state_version=run.state_version,
            )

            return self._seal_response(cf_record)

    def get_seal(self, run_id: str, stage_id: str):
        from app.api.stage_seal_contracts import StageSealResponse

        with self._scope() as session:
            record = session.scalar(
                select(StageSealModel).where(
                    StageSealModel.run_id == run_id,
                    StageSealModel.stage_id == stage_id,
                ).order_by(StageSealModel.created_at.desc())
            )
            if record is None:
                return None
            return self._seal_response(record)

    def _run_and_stage(self, session, run_id, stage_id):
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise StageSealApplicationError("RUN_NOT_FOUND", "Migration run was not found.", 404)
        stage = session.get(MigrationStageModel, stage_id)
        if stage is None:
            raise StageSealApplicationError("STAGE_NOT_FOUND", "Migration stage was not found.", 404)
        return run, stage

    def _transition(self, session, run, request, event_type, reason, payload, expected_state_version=None):
        try:
            return StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run.id,
                    expected_state_version=run.state_version if expected_state_version is None else expected_state_version,
                    idempotency_key=f"{request.idempotency_key}:{event_type.value}",
                    event_type=event_type,
                    actor=request.actor,
                    reason=reason,
                    occurred_at=self._now(),
                    payload=payload,
                )
            )
        except StaleStateVersionError as error:
            raise StageSealApplicationError("STALE_STATE_VERSION", str(error), 409) from error

    @staticmethod
    def _require_state(run, expected):
        if run.state_version != expected:
            raise StageSealApplicationError("STALE_STATE_VERSION", "The run state version is stale.", 409)

    @staticmethod
    def _latest_sequence(session, run_id):
        return int(session.scalar(select(func.max(WorkflowEventModel.sequence)).where(WorkflowEventModel.run_id == run_id)) or 0)

    @staticmethod
    def _seal_response(record, replay=False):
        from app.api.stage_seal_contracts import StageSealResponse
        return StageSealResponse(
            seal_id=record.id,
            run_id=record.run_id,
            stage_id=record.stage_id,
            status=record.status,
            fingerprint=record.fingerprint if hasattr(record, 'fingerprint') else None,
            cleanup_result=record.cleanup_result if hasattr(record, 'cleanup_result') else None,
            artifact_ids=record.artifact_ids or [],
            artifact_checksums=record.artifact_checksums or {},
            state_version=record.state_version,
            event_sequence=record.event_sequence,
            idempotent_replay=replay,
        )

    def _write_seal_report(self, session, run, stage_id, seal, idempotency_key):
        root = Path(run.artifact_root).resolve() if run.artifact_root else Path("/tmp")
        store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
        artifact_path = f"04_stage_seal/stage_seal_report_{stage_id}.json"
        stored = store.write_text_artifact(
            run.id, artifact_path,
            json.dumps({
                "stage_id": stage_id,
                "status": seal.status,
                "fingerprint": seal.fingerprint,
                "cleanup_result": seal.cleanup_result,
            }, indent=2, sort_keys=True),
            ArtifactType.JSON,
            created_by="stage-seal-service",
            created_at=self._now(),
            input_hashes={"request": idempotency_key},
            policy_version="stage-seal-v1",
        )
        self._register_artifact(session, run, stored.ref.artifact_id)
        return stored.ref.artifact_id

    @staticmethod
    def _artifact_checksum(run, artifact_id):
        from app.artifact_store.local_store import LocalFilesystemArtifactStore
        root = Path(run.artifact_root).resolve() if run.artifact_root else Path("/tmp")
        return LocalFilesystemArtifactStore(root, fixed_run_root=root).read_artifact_by_id(artifact_id).ref.checksum

    @staticmethod
    def _register_artifact(session, run, artifact_id):
        if session.get(ArtifactMetadataModel, f"metadata-{artifact_id}") is None:
            from app.artifact_store.local_store import LocalFilesystemArtifactStore
            root = Path(run.artifact_root).resolve() if run.artifact_root else Path("/tmp")
            store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
            stored = store.read_artifact_by_id(artifact_id)
            session.add(ArtifactMetadataModel(
                id=f"metadata-{artifact_id}",
                run_id=run.id,
                stage_id=None,
                artifact_type=stored.ref.artifact_type.value,
                relative_path=stored.ref.relative_path,
                checksum=stored.ref.checksum,
                created_at=stored.ref.created_at,
            ))
