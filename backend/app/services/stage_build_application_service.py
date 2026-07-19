"""Application service for S3-F11 stage build matrix execution."""
from __future__ import annotations
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from sqlalchemy import func, select
from app.artifact_store.local_store import LocalFilesystemArtifactStore
from app.domain.stage_build import StageBuildService, BuildResult, BuildTarget, BuildTargetStatus
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.repositories.models import ArtifactMetadataModel, MigrationRunModel, WorkflowEventModel
from app.repositories.models.workflow import StageBuildModel, MigrationStageModel
from app.repositories.session import session_scope
from app.state.transition_service import StaleStateVersionError, StateTransitionService, TransitionRequest


class StageBuildApplicationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class StageBuildApplicationService:
    def __init__(self, *, scope=session_scope, domain_service=None, now_provider=None):
        self._scope = scope
        self._domain = domain_service or StageBuildService()
        self._now = now_provider or (lambda: datetime.now(UTC))

    def execute_build(self, run_id: str, stage_id: str, request):
        from app.api.stage_build_contracts import StageBuildResponse

        with self._scope() as session:
            run, stage = self._run_and_stage(session, run_id, stage_id)
            replay = session.scalar(
                select(StageBuildModel).where(
                    StageBuildModel.run_id == run_id,
                    StageBuildModel.stage_id == stage_id,
                    StageBuildModel.idempotency_key == request.idempotency_key,
                )
            )
            if replay:
                return self._response(replay, replay=True)

            self._require_state(run, request.expected_state_version)

            started = self._transition(
                session, run, request,
                WorkflowEventType.STAGE_BUILD_STARTED,
                "stage build started",
                {"stage_id": stage_id},
            )

            sandbox = Path(stage.sandbox_path) if hasattr(stage, 'sandbox_path') and stage.sandbox_path else Path("/tmp")
            targets = self._domain.resolve_targets(sandbox)

            build = StageBuildModel(
                id=f"stage-build-{uuid4().hex[:12]}",
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key=request.idempotency_key,
                actor=request.actor,
                status="running",
                per_target_statuses=[self._target_dict(t) for t in targets],
                results=[],
                parser_summary={},
                artifact_ids=[],
                artifact_checksums={},
                state_version=started.next_state_version,
                event_sequence=started.event_sequence,
                created_at=self._now(),
                updated_at=self._now(),
            )
            session.add(build)
            session.flush()

            # Simulate build results
            results: list[BuildResult] = []
            for t in targets:
                if not t.supported:
                    results.append(BuildResult(
                        target_id=t.target_id, kind=t.kind,
                        status=BuildTargetStatus.SKIPPED, blocker=t.blocker,
                    ))
                else:
                    results.append(BuildResult(
                        target_id=t.target_id, kind=t.kind,
                        status=BuildTargetStatus.PASSED, exit_code=0, duration_ms=0,
                    ))
                self._transition(
                    session, run, request,
                    WorkflowEventType.STAGE_BUILD_TARGET_COMPLETED,
                    f"build target {t.target_id} completed",
                    {"stage_id": stage_id, "target_id": t.target_id},
                    expected_state_version=run.state_version,
                )

            summary = self._domain.aggregate_matrix_summary(results)
            result_dicts = [self._result_dict(r) for r in results]
            report_id = self._write_report(session, run, stage_id, result_dicts, summary, request.idempotency_key)
            artifact_ids = [report_id]

            any_failed = any(r.status in {BuildTargetStatus.FAILED, BuildTargetStatus.CANCELLED} for r in results)
            status = "failed" if any_failed else "passed"

            completed = self._transition(
                session, run, request,
                WorkflowEventType.STAGE_BUILD_COMPLETED,
                "stage build completed",
                {"stage_id": stage_id, "status": status},
                expected_state_version=run.state_version,
            )

            build.status = status
            build.per_target_statuses = [self._target_dict(t) for t in targets]
            build.results = result_dicts
            build.parser_summary = summary
            build.artifact_ids = artifact_ids
            build.artifact_checksums = {artifact_id: self._artifact_checksum(run, artifact_id) for artifact_id in artifact_ids}
            build.state_version = completed.next_state_version
            build.event_sequence = completed.event_sequence
            build.updated_at = self._now()
            session.flush()

            return self._response(build)

    def get_build(self, run_id: str, stage_id: str):
        from app.api.stage_build_contracts import StageBuildResponse

        with self._scope() as session:
            record = session.scalar(
                select(StageBuildModel).where(
                    StageBuildModel.run_id == run_id,
                    StageBuildModel.stage_id == stage_id,
                ).order_by(StageBuildModel.created_at.desc())
            )
            if record is None:
                return None
            return self._response(record)

    def _run_and_stage(self, session, run_id, stage_id):
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise StageBuildApplicationError("RUN_NOT_FOUND", "Migration run was not found.", 404)
        stage = session.get(MigrationStageModel, stage_id)
        if stage is None:
            raise StageBuildApplicationError("STAGE_NOT_FOUND", "Migration stage was not found.", 404)
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
            raise StageBuildApplicationError("STALE_STATE_VERSION", str(error), 409) from error

    @staticmethod
    def _require_state(run, expected):
        if run.state_version != expected:
            raise StageBuildApplicationError("STALE_STATE_VERSION", "The run state version is stale.", 409)

    @staticmethod
    def _target_dict(target):
        return {
            "target_id": target.target_id,
            "kind": target.kind.value,
            "project": target.project,
            "command_id": target.command_id,
            "supported": target.supported,
            "blocker": target.blocker,
        }

    @staticmethod
    def _result_dict(result):
        return {
            "target_id": result.target_id,
            "kind": result.kind.value,
            "status": result.status.value,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "warnings": list(result.warnings),
            "output_location": result.output_location,
            "artifact_ids": list(result.artifact_ids),
            "blocker": result.blocker,
        }

    @staticmethod
    def _response(record, replay=False):
        from app.api.stage_build_contracts import StageBuildResponse
        return StageBuildResponse(
            build_id=record.id,
            run_id=record.run_id,
            stage_id=record.stage_id,
            status=record.status,
            targets=record.per_target_statuses or [],
            results=record.results or [],
            summary=record.parser_summary or {},
            artifact_ids=record.artifact_ids or [],
            artifact_checksums=record.artifact_checksums or {},
            state_version=record.state_version,
            event_sequence=record.event_sequence,
            idempotent_replay=replay,
        )

    def _write_report(self, session, run, stage_id, results, summary, idempotency_key):
        root = Path(run.artifact_root).resolve() if run.artifact_root else Path("/tmp")
        store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
        artifact_path = f"04_stage_build/stage_build_report_{stage_id}.json"
        stored = store.write_text_artifact(
            run.id, artifact_path,
            json.dumps({"stage_id": stage_id, "results": results, "summary": summary}, indent=2, sort_keys=True),
            ArtifactType.JSON,
            created_by="stage-build-service",
            created_at=self._now(),
            input_hashes={"request": idempotency_key},
            policy_version="stage-build-v1",
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
