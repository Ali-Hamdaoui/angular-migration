from __future__ import annotations
import hashlib, json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select
from app.api.parity_baseline_contracts import ParityBaselineResponse
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.domain.parity_baseline import ParityBaselineBuilder
from app.repositories.models import ArtifactMetadataModel, G03ApprovalModel, MigrationRunModel
from app.repositories.parity_baseline_models import ParityBaselineEvidenceModel
from app.repositories.session import session_scope
from app.state.transition_service import StateTransitionService, TransitionRequest


class ParityBaselineEvidenceError(ValueError):
    def __init__(self, code, message, status_code=422):
        self.code, self.message, self.status_code = code, message, status_code
        super().__init__(message)


class ParityBaselineEvidenceApplicationService:
    def __init__(self, *, scope=session_scope, builder=None, now_provider=None):
        self.scope, self.builder, self.now = (
            scope,
            builder or ParityBaselineBuilder(),
            now_provider or (lambda: datetime.now(UTC)),
        )

    def capture(self, run_id, request):
        checksum = self._checksum(request)
        with self.scope() as s:
            old = s.scalar(
                select(ParityBaselineEvidenceModel).where(
                    ParityBaselineEvidenceModel.run_id == run_id,
                    ParityBaselineEvidenceModel.idempotency_key == request.idempotency_key,
                )
            )
            if old:
                if old.request_checksum != checksum:
                    raise ParityBaselineEvidenceError(
                        "IDEMPOTENCY_KEY_REUSED", "Idempotency key was used with a different payload.", 409
                    )
                return self.dto(old, True)
            run = self.validate(s, run_id, request)
            self.transition(s, run, request, WorkflowEventType.PARITY_BASELINE_STARTED, "parity baseline started", {})
            workspace = Path((run.workspace_aliases or {}).get("SOURCE_SNAPSHOT", ""))
        try:
            baseline = self.builder.build(workspace)
        except Exception:
            return self.block(run_id, request, checksum, None)
        try:
            with self.scope() as s:
                run = s.get(MigrationRunModel, run_id)
                store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
                stored = [
                    store.write_text_artifact(
                        run_id,
                        "02_analysis/" + d.name,
                        d.content,
                        ArtifactType.JSON,
                        created_by="parity-baseline",
                        created_at=self.now(),
                        policy_version="parity-baseline-v1",
                    )
                    for d in baseline.evidence_drafts
                ]
                ids = [x.ref.artifact_id for x in stored]
                checks = {x.ref.artifact_id: x.ref.checksum for x in stored}
                transition = self.transition(
                    s,
                    run,
                    request,
                    WorkflowEventType.PARITY_BASELINE_COMPLETED,
                    "parity baseline completed",
                    {"artifact_count": len(ids)},
                )
                row = ParityBaselineEvidenceModel(
                    id="parity-baseline-" + uuid4().hex[:12],
                    run_id=run_id,
                    idempotency_key=request.idempotency_key,
                    request_checksum=checksum,
                    actor=request.actor,
                    status="completed",
                    payload=baseline.model_dump(mode="json", exclude={"evidence_drafts"}),
                    artifact_ids=ids,
                    artifact_checksums=checks,
                    prerequisite_artifact_ids=request.prerequisite_artifact_ids,
                    error_code=None,
                    state_version=transition.next_state_version,
                    event_sequence=transition.event_sequence,
                    created_at=self.now(),
                    updated_at=self.now(),
                )
                s.add(row)
                for x in stored:
                    s.add(
                        ArtifactMetadataModel(
                            id="metadata-" + x.ref.artifact_id,
                            run_id=run_id,
                            stage_id=None,
                            artifact_type=x.ref.artifact_type.value,
                            relative_path=x.ref.relative_path,
                            checksum=x.ref.checksum,
                            created_at=x.ref.created_at,
                        )
                    )
                s.flush()
                return self.dto(row)
        except ParityBaselineEvidenceError:
            raise
        except Exception:
            return self.block(run_id, request, checksum, baseline)

    def get(self, run_id):
        with self.scope() as s:
            row = s.scalar(
                select(ParityBaselineEvidenceModel)
                .where(ParityBaselineEvidenceModel.run_id == run_id)
                .order_by(ParityBaselineEvidenceModel.created_at.desc())
            )
            return self.dto(row) if row else None

    def block(self, run_id, request, checksum, baseline):
        with self.scope() as s:
            run = s.get(MigrationRunModel, run_id)
            t = self.transition(
                s,
                run,
                request,
                WorkflowEventType.PARITY_BASELINE_BLOCKED,
                "parity baseline dependency failed",
                {"error_code": "PARITY_BASELINE_DEPENDENCY_FAILED"},
            )
            row = ParityBaselineEvidenceModel(
                id="parity-baseline-" + uuid4().hex[:12],
                run_id=run_id,
                idempotency_key=request.idempotency_key,
                request_checksum=checksum,
                actor=request.actor,
                status="blocked",
                payload=baseline.model_dump(mode="json", exclude={"evidence_drafts"}) if baseline else {},
                artifact_ids=[],
                artifact_checksums={},
                prerequisite_artifact_ids=request.prerequisite_artifact_ids,
                error_code="PARITY_BASELINE_DEPENDENCY_FAILED",
                state_version=t.next_state_version,
                event_sequence=t.event_sequence,
                created_at=self.now(),
                updated_at=self.now(),
            )
            s.add(row)
            s.flush()
            return self.dto(row)

    def validate(self, s, run_id, r):
        run = s.get(MigrationRunModel, run_id)
        if not run:
            raise ParityBaselineEvidenceError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
        if run.state_version != r.expected_state_version:
            raise ParityBaselineEvidenceError("STALE_STATE_VERSION", "The run state version is stale.", 409)
        if (
            s.scalar(
                select(G03ApprovalModel).where(G03ApprovalModel.run_id == run_id, G03ApprovalModel.status == "approved")
            )
            is None
        ):
            raise ParityBaselineEvidenceError(
                "G03_APPROVAL_REQUIRED", "An approved G03 baseline boundary is required.", 409
            )
        meta = {
            x.id.removeprefix("metadata-"): x
            for x in s.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id))
        }
        if any(x not in meta for x in r.prerequisite_artifact_ids):
            raise ParityBaselineEvidenceError(
                "PREREQUISITE_ARTIFACT_NOT_FOUND", "A prerequisite artifact is not registered.", 409
            )
        if any(meta[x].checksum != r.prerequisite_artifact_checksums.get(x) for x in r.prerequisite_artifact_ids):
            raise ParityBaselineEvidenceError(
                "PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH", "A prerequisite checksum does not match.", 409
            )
        return run

    def transition(self, s, run, r, event, reason, payload):
        return StateTransitionService(s).apply_transition(
            TransitionRequest(
                run_id=run.id,
                expected_state_version=run.state_version,
                idempotency_key=r.idempotency_key + ":" + event.value,
                event_type=event,
                actor=r.actor,
                reason=reason,
                occurred_at=self.now(),
                payload=payload,
            )
        )

    @staticmethod
    def _checksum(r):
        return (
            "sha256:"
            + hashlib.sha256(
                json.dumps(r.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        )

    @staticmethod
    def dto(row, replay=False):
        return ParityBaselineResponse(
            run_id=row.run_id,
            evidence_id=row.id,
            status=row.status,
            payload=row.payload,
            artifact_ids=row.artifact_ids,
            artifact_checksums=row.artifact_checksums,
            prerequisite_artifact_ids=row.prerequisite_artifact_ids,
            error_code=row.error_code,
            state_version=row.state_version,
            event_sequence=row.event_sequence,
            idempotent_replay=replay,
        )
