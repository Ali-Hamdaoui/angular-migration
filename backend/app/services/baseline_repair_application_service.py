"""Checksum-bound application of the proven pre-G03 baseline repair."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.api.baseline_repair_contracts import BaselineRepairResponse
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.repositories.models import ArtifactMetadataModel, BaselineAssessmentModel, BaselineQualificationModel, G03ApprovalModel, MigrationRunModel, SourceSnapshotModel, WorkflowEventModel
from app.repositories.session import session_scope
from app.services.patch_apply_service import PatchApplyService
from app.services.workspace_fingerprint import SOURCE_CONFIG_FINGERPRINT_PROFILE, workspace_fingerprint_v1
from app.services.workspace_integrity_service import WorkspaceIntegrityError, WorkspaceIntegrityService
from app.state.transition_service import StateTransitionService, TransitionRequest


RECIPE_ID = "BASELINE-TEST-001"
SPEC_PATH = "src/app/app.component.spec.ts"
SPEC_CONTENT = """import { AppComponent } from './app.component';

describe('AppComponent', () => {
  it('constructs the application root component', () => {
    expect(new AppComponent()).toBeTruthy();
  });
});
"""


class BaselineRepairApplicationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


class BaselineRepairApplicationService:
    def __init__(self, *, scope=session_scope, patches=None, now_provider=None):
        self._scope = scope
        self._patches = patches or PatchApplyService()
        self._now = now_provider or (lambda: datetime.now(UTC))

    def apply(self, run_id: str, request) -> BaselineRepairResponse:
        completion_key = request.idempotency_key + ":completed"
        with self._scope() as session:
            replay = session.scalar(select(WorkflowEventModel).where(
                WorkflowEventModel.run_id == run_id,
                WorkflowEventModel.idempotency_key == completion_key,
            ))
            if replay is not None:
                return self._response(replay.payload, replay=True)
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise BaselineRepairApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
            if run.state_version != request.expected_state_version:
                raise BaselineRepairApplicationError("STALE_STATE_VERSION", "The run state version is stale.")
            baseline = session.scalar(select(BaselineQualificationModel).where(
                BaselineQualificationModel.run_id == run_id,
            ).order_by(BaselineQualificationModel.created_at.desc()))
            assessment = session.scalar(select(BaselineAssessmentModel).where(
                BaselineAssessmentModel.run_id == run_id,
            ).order_by(BaselineAssessmentModel.updated_at.desc()))
            decision = session.scalar(select(G03ApprovalModel).where(
                G03ApprovalModel.run_id == run_id,
                G03ApprovalModel.status == "modification_requested",
            ).order_by(G03ApprovalModel.updated_at.desc()))
            if baseline is None or assessment is None or decision is None:
                raise BaselineRepairApplicationError("BASELINE_REPAIR_AUTHORIZATION_REQUIRED", "A current G03 request-changes decision is required.")
            if request.recipe_id != RECIPE_ID or request.recipe_id not in (decision.comment or ""):
                raise BaselineRepairApplicationError("BASELINE_REPAIR_RECIPE_NOT_APPROVED", "G03 did not authorize this exact baseline repair recipe.")
            if request.g03_package_checksum != assessment.package_checksum or decision.package_checksum != assessment.package_checksum:
                raise BaselineRepairApplicationError("BASELINE_REPAIR_PACKAGE_STALE", "The approved G03 package checksum changed.")
            if "BASELINE_REQUIRED_TEST_NOT_PROVEN" not in (assessment.blockers or []):
                raise BaselineRepairApplicationError("BASELINE_REPAIR_NOT_APPLICABLE", "The approved test-evidence blocker is not present.")
            workspace = Path(baseline.sandbox_path).resolve(strict=True)
            snapshot = session.get(SourceSnapshotModel, baseline.snapshot_id)
            if snapshot is None:
                raise BaselineRepairApplicationError("BASELINE_REPAIR_WORKSPACE_STALE", "The baseline binding no longer matches G03.")
            try:
                WorkspaceIntegrityService().verify(workspace, expected_fingerprint=assessment.sandbox_fingerprint)
            except WorkspaceIntegrityError:
                raise BaselineRepairApplicationError("BASELINE_REPAIR_WORKSPACE_STALE", "The baseline binding no longer matches G03.")
            snapshot_root = Path(snapshot.snapshot_path).resolve(strict=True)
            if self._approved_source_fingerprint(workspace) != self._approved_source_fingerprint(snapshot_root):
                raise BaselineRepairApplicationError("BASELINE_REPAIR_WORKSPACE_STALE", "The baseline source/config content changed after G02.")
            target = workspace / SPEC_PATH
            if target.exists():
                raise BaselineRepairApplicationError("BASELINE_REPAIR_TARGET_EXISTS", "The BASELINE-TEST-001 target already exists.")
            attempt_id = f"baseline-repair-{uuid4().hex[:12]}"
            proposal = self._proposal(run_id, attempt_id, assessment.package_checksum)
            store = LocalFilesystemArtifactStore(Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root))
            proposal_artifact = store.write_text_artifact(
                run_id, f"05_repairs/{attempt_id}/proposal.json",
                json.dumps(proposal, indent=2, sort_keys=True), ArtifactType.JSON,
                created_by="baseline-repair-service", created_at=self._now(),
                input_hashes={"g03_package": assessment.package_checksum},
                policy_version="baseline-repair-v1",
            )
            self._register(session, run_id, proposal_artifact)
            pre_fingerprint = SOURCE_CONFIG_FINGERPRINT_PROFILE.fingerprint(workspace)
            started = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=run.state_version,
                idempotency_key=request.idempotency_key + ":started",
                event_type=WorkflowEventType.REPAIR_APPLY_STARTED,
                actor=request.actor, reason="approved baseline repair application started",
                occurred_at=self._now(), payload={
                    "recipe_id": RECIPE_ID, "attempt_id": attempt_id,
                    "g03_package_checksum": assessment.package_checksum,
                    "proposal_artifact_id": proposal_artifact.ref.artifact_id,
                    "proposal_checksum": proposal_artifact.ref.checksum,
                    "pre_fingerprint": pre_fingerprint,
                },
            ))
            artifact_root = run.artifact_root

        try:
            prepared, applied, _ = self._patches.apply(
                proposal=proposal, workspace_path=str(workspace),
                expected_fingerprint=pre_fingerprint, run_id=run_id,
                stage_id=None, artifact_root=artifact_root, attempt_id=attempt_id,
                approved_proposal_checksum=proposal_artifact.ref.checksum,
                proposal_artifact_checksum=proposal_artifact.ref.checksum,
            )
            post_fingerprint = workspace_fingerprint_v1(workspace)
        except Exception as error:
            with self._scope() as session:
                run = session.get(MigrationRunModel, run_id)
                if run is not None:
                    StateTransitionService(session).apply_transition(TransitionRequest(
                        run_id=run_id, expected_state_version=run.state_version,
                        idempotency_key=request.idempotency_key + ":failed",
                        event_type=WorkflowEventType.REPAIR_APPLY_FAILED,
                        actor=request.actor, reason="baseline repair application failed",
                        occurred_at=self._now(), payload={"recipe_id": RECIPE_ID, "attempt_id": attempt_id, "error_code": type(error).__name__},
                    ))
            raise BaselineRepairApplicationError("BASELINE_REPAIR_APPLY_FAILED", str(error), 422) from error

        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            assessment = session.scalar(select(BaselineAssessmentModel).where(
                BaselineAssessmentModel.run_id == run_id,
                BaselineAssessmentModel.package_checksum == request.g03_package_checksum,
            ).order_by(BaselineAssessmentModel.updated_at.desc()))
            decision = session.scalar(select(G03ApprovalModel).where(
                G03ApprovalModel.run_id == run_id,
                G03ApprovalModel.package_checksum == request.g03_package_checksum,
            ).order_by(G03ApprovalModel.updated_at.desc()))
            for artifact in (prepared, applied):
                self._register(session, run_id, artifact)
            stale_reason = f"{RECIPE_ID} was applied; baseline validation, parity, and G03 must be regenerated."
            if assessment is not None:
                assessment.status, assessment.stale_reason, assessment.updated_at = "stale", stale_reason, self._now()
            if decision is not None:
                decision.status, decision.stale_reason, decision.updated_at = "stale", stale_reason, self._now()
            artifact_ids = [proposal_artifact.ref.artifact_id, prepared.ref.artifact_id, applied.ref.artifact_id]
            payload = {
                "run_id": run_id, "recipe_id": RECIPE_ID, "attempt_id": attempt_id,
                "status": "applied", "g03_package_checksum": request.g03_package_checksum,
                "proposal_checksum": proposal_artifact.ref.checksum,
                "pre_fingerprint": pre_fingerprint, "post_fingerprint": post_fingerprint,
                "artifact_ids": artifact_ids,
            }
            completed = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run_id, expected_state_version=run.state_version,
                idempotency_key=completion_key,
                event_type=WorkflowEventType.REPAIR_APPLY_COMPLETED,
                actor=request.actor, reason="approved baseline repair applied",
                occurred_at=self._now(), payload=payload,
            ))
            payload.update({"state_version": completed.next_state_version, "event_sequence": completed.event_sequence})
            event = session.get(WorkflowEventModel, completed.event_id)
            event.payload.update(payload)
            session.flush()
            return self._response(payload)

    @staticmethod
    def _proposal(run_id: str, attempt_id: str, package_checksum: str) -> dict:
        return {
            "schema_version": "baseline-repair-proposal-v1", "proposal_format": "operations",
            "run_id": run_id, "attempt_id": attempt_id, "recipe_id": RECIPE_ID,
            "g03_package_checksum": package_checksum,
            "operations": [{"operation": "create_text_file", "path": SPEC_PATH, "content": SPEC_CONTENT}],
            "unified_diff": None,
        }

    @staticmethod
    def _approved_source_fingerprint(root: Path) -> str:
        entries = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if path.name in {"source-manifest.json", "snapshot-fingerprint.json"}:
                continue
            if any(part.casefold() in {"node_modules", ".angular", "dist", "coverage", ".git"} for part in path.relative_to(root).parts):
                continue
            entries.append((relative, path.read_bytes()))
        return SOURCE_CONFIG_FINGERPRINT_PROFILE.fingerprint_manifest(entries)

    @staticmethod
    def _register(session, run_id, artifact):
        metadata_id = "metadata-" + artifact.ref.artifact_id
        if session.get(ArtifactMetadataModel, metadata_id) is None:
            session.add(ArtifactMetadataModel(
                id=metadata_id, run_id=run_id, stage_id=None,
                artifact_type=artifact.ref.artifact_type.value,
                relative_path=artifact.ref.relative_path, checksum=artifact.ref.checksum,
                created_at=artifact.ref.created_at,
            ))

    @staticmethod
    def _response(payload, replay=False):
        return BaselineRepairResponse(
            run_id=payload["run_id"], recipe_id=payload["recipe_id"],
            attempt_id=payload["attempt_id"], status=payload["status"],
            g03_package_checksum=payload["g03_package_checksum"],
            proposal_checksum=payload["proposal_checksum"],
            pre_fingerprint=payload["pre_fingerprint"], post_fingerprint=payload["post_fingerprint"],
            artifact_ids=payload["artifact_ids"], state_version=payload["state_version"],
            event_sequence=payload["event_sequence"], idempotent_replay=replay,
        )
