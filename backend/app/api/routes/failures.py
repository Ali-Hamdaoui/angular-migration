"""API routes for failure evidence capture, persistence, and retrieval."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.errors import error_response
from app.artifact_store.local_store import LocalFilesystemArtifactStore
from app.core.config import get_settings
from app.domain.contracts import ArtifactRefDto, ArtifactType, WorkflowEventType
from app.domain.failure import (
    FailureBuilderInput,
    FailureDiagnostic,
    FailureEvidence,
    FailureFingerprintService,
    OriginComparator,
)
from app.repositories.failure_repository import FailureRepository
from app.repositories.models.workflow import MigrationRunModel
from app.repositories.session import session_scope
from app.services.failure_evidence_builder import (
    DEFAULT_PARSER_REGISTRY,
    FailureEvidenceBuilder,
)
from app.state.transition_service import (
    StateTransitionService,
    TransitionError,
)

router = APIRouter(prefix="/runs", tags=["failures"])
_repo = FailureRepository()


# ---------------------------------------------------------------------------
# Request / response DTOs
# ---------------------------------------------------------------------------


class CaptureFailureEvidenceRequest(BaseModel):
    """Request body matching the shape of FailureBuilderInput."""

    run_id: str = Field(min_length=1, max_length=64)
    stage_id: str = Field(min_length=1, max_length=64)
    execution_id: str = Field(min_length=1, max_length=128)
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    workspace_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=128)
    baseline_artifact_ids: list[str] = Field(default_factory=list)
    expected_state_version: int = Field(default=1, ge=1)
    actor: str = "system"


class FailureDiagnosticDto(BaseModel):
    """Serialised diagnostic entry for API responses."""

    message: str
    code: str | None = None
    file_path: str | None = None
    line_number: int | None = None
    column: int | None = None
    severity: str = "error"
    parser_type: str
    parser_confidence: float = 1.0


class FailureEvidenceResponse(BaseModel):
    """Response model for a single failure evidence record."""

    failure_id: str
    run_id: str
    stage_id: str | None = None
    execution_id: str | None = None
    failure_fingerprint: str
    origin: str
    workspace_fingerprint: str
    status: str
    diagnostics: list[FailureDiagnosticDto] = Field(default_factory=list)
    raw_log_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    idempotent_replay: bool = False
    event_sequence: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_artifact_store(run_id: str) -> LocalFilesystemArtifactStore | None:
    """Resolve the artifact store for a run, or return None if unavailable."""
    with session_scope() as session:
        run = session.get(MigrationRunModel, run_id)
        if run is None or not run.artifact_root:
            return None
        root = Path(run.artifact_root).resolve()
    return LocalFilesystemArtifactStore(root, fixed_run_root=root)


def _build_evidence(
    run_id: str,
    input_data: FailureBuilderInput,
) -> FailureEvidence:
    """Run the FailureEvidenceBuilder pipeline with the default parser registry."""
    artifact_store = _build_artifact_store(run_id)
    builder = FailureEvidenceBuilder(
        parser_registry=DEFAULT_PARSER_REGISTRY,
        fingerprint_service=FailureFingerprintService(),
        origin_comparator=OriginComparator(),
        artifact_store=artifact_store,
    )
    return builder.build(input_data)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{run_id}/commands/{command_id}/failure-evidence", status_code=201, response_model=None)
def capture_failure_evidence(
    run_id: str,
    command_id: str,
    body: CaptureFailureEvidenceRequest,
    http_request: Request,
) -> JSONResponse | FailureEvidenceResponse:
    """Accept command output, run parsers, persist evidence, emit events.

    Validates the run exists, builds failure evidence through the
    FailureEvidenceBuilder pipeline, persists with idempotency protection,
    emits FAILURE_CAPTURED and FAILURE_DIAGNOSTICS_PARSED events, and
    returns the stored evidence.
    """
    with session_scope() as session:
        # 1. Validate the run exists
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            return error_response(
                http_request,
                status_code=404,
                error_code="RUN_NOT_FOUND",
                message=f"Run {run_id} does not exist.",
            )

        # 2. Build input for the evidence builder
        try:
            builder_input = FailureBuilderInput(
                run_id=body.run_id,
                stage_id=body.stage_id,
                execution_id=body.execution_id,
                exit_code=body.exit_code,
                stdout=body.stdout,
                stderr=body.stderr,
                workspace_fingerprint=body.workspace_fingerprint,
                idempotency_key=body.idempotency_key,
                baseline_artifact_ids=body.baseline_artifact_ids,
            )
        except ValueError as exc:
            return error_response(
                http_request,
                status_code=422,
                error_code="INVALID_INPUT",
                message=str(exc),
            )

        # 3. Build evidence
        try:
            evidence = _build_evidence(run_id, builder_input)
        except ValueError as exc:
            return error_response(
                http_request,
                status_code=422,
                error_code="BUILD_FAILED",
                message=f"Failure evidence builder failed: {exc}",
            )

        # 4. Persist failure with idempotency protection
        try:
            persisted = _repo.save_failure(
                session,
                evidence,
                body.idempotency_key,
                body.expected_state_version,
            )
        except Exception as exc:
            return error_response(
                http_request,
                status_code=409,
                error_code="PERSISTENCE_FAILED",
                message=f"Failed to persist failure evidence: {exc}",
            )

        # 5. Persist diagnostics
        try:
            _repo.save_diagnostics(session, evidence.failure_id, evidence.diagnostics)
        except Exception as exc:
            return error_response(
                http_request,
                status_code=500,
                error_code="DIAGNOSTIC_PERSIST_FAILED",
                message=f"Failed to persist diagnostics: {exc}",
            )

        # 6. Emit FAILURE_CAPTURED event via transition service
        transition_svc = StateTransitionService(session)
        event_sequence = 0
        try:
            result = transition_svc.append_audit_event(
                run_id=run_id,
                idempotency_key=f"{body.idempotency_key}:FAILURE_CAPTURED",
                event_type=WorkflowEventType.FAILURE_CAPTURED,
                actor=body.actor,
                reason=f"Failure evidence captured for execution {evidence.execution_id}",
                occurred_at=datetime.now(UTC),
                payload={
                    "failure_id": evidence.failure_id,
                    "failure_fingerprint": evidence.failure_fingerprint,
                    "origin": evidence.origin.value,
                    "diagnostic_count": len(evidence.diagnostics),
                    "command_id": command_id,
                },
            )
            event_sequence = result.event_sequence
        except TransitionError as exc:
            return error_response(
                http_request,
                status_code=409,
                error_code="TRANSITION_FAILED",
                message=f"Event emission failed: {exc}",
            )

        # 7. Emit FAILURE_DIAGNOSTICS_PARSED event (non-fatal if this fails)
        try:
            transition_svc.append_audit_event(
                run_id=run_id,
                idempotency_key=f"{body.idempotency_key}:FAILURE_DIAGNOSTICS_PARSED",
                event_type=WorkflowEventType.FAILURE_DIAGNOSTICS_PARSED,
                actor=body.actor,
                reason=f"Diagnostics parsed for failure {evidence.failure_id}",
                occurred_at=datetime.now(UTC),
                payload={
                    "failure_id": evidence.failure_id,
                    "parser_count": len(
                        {d.parser_type.value for d in evidence.diagnostics}
                    ),
                    "diagnostic_count": len(evidence.diagnostics),
                },
            )
        except TransitionError:
            pass

    # 8. Build response
    return FailureEvidenceResponse(
        failure_id=evidence.failure_id,
        run_id=evidence.run_id,
        stage_id=evidence.stage_id,
        execution_id=evidence.execution_id,
        failure_fingerprint=evidence.failure_fingerprint,
        origin=evidence.origin.value,
        workspace_fingerprint=evidence.workspace_fingerprint,
        status=evidence.status.value,
        diagnostics=[
            FailureDiagnosticDto(
                message=d.message,
                code=d.code,
                file_path=d.file_path,
                line_number=d.line_number,
                column=d.column,
                severity=d.severity,
                parser_type=d.parser_type.value,
                parser_confidence=d.parser_confidence,
            )
            for d in evidence.diagnostics
        ],
        raw_log_artifacts=[
            {
                "artifact_id": a.artifact_id,
                "run_id": a.run_id,
                "stage_id": a.stage_id,
                "artifact_type": a.artifact_type.value,
                "relative_path": a.relative_path,
                "created_at": a.created_at.isoformat(),
                "checksum": a.checksum,
            }
            for a in evidence.raw_log_artifacts
        ],
        idempotent_replay=False,
        event_sequence=event_sequence,
    )


@router.get("/failures/{failure_id}", response_model=None)
def get_failure_evidence(
    run_id: str,
    failure_id: str,
    http_request: Request,
):
    """Retrieve a stored failure evidence record with its diagnostics."""
    with session_scope() as session:
        persisted = _repo.get_failure(session, run_id, failure_id)
        if persisted is None:
            return error_response(
                http_request,
                status_code=404,
                error_code="FAILURE_NOT_FOUND",
                message=f"Failure {failure_id} not found in run {run_id}.",
            )

        diagnostics = _repo.get_diagnostics(session, failure_id)

    # Parse failure_json back
    parsed_evidence: dict[str, Any] = json.loads(persisted.failure_json)
    diag_list: list[dict[str, Any]] = parsed_evidence.get("diagnostics", [])

    return FailureEvidenceResponse(
        failure_id=persisted.id,
        run_id=persisted.run_id,
        stage_id=persisted.stage_id,
        execution_id=persisted.execution_id,
        failure_fingerprint=persisted.failure_fingerprint,
        origin=persisted.origin,
        workspace_fingerprint=persisted.workspace_fingerprint,
        status=persisted.status,
        diagnostics=[
            FailureDiagnosticDto(
                message=d.get("message", ""),
                code=d.get("code"),
                file_path=d.get("file_path"),
                line_number=d.get("line_number"),
                column=d.get("column"),
                severity=d.get("severity", "error"),
                parser_type=d.get("parser_type", "generic"),
                parser_confidence=d.get("parser_confidence", 0.0),
            )
            for d in diag_list
        ],
        raw_log_artifacts=[
            a
            for a in parsed_evidence.get("raw_log_artifacts", [])
        ],
    )
