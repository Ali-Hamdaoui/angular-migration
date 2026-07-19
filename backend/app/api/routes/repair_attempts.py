"""API routes for the repair-attempt proposer, reviewer, and revision surface.

Endpoints:
  POST /runs/{run_id}/repair-attempts/{attempt_id}/proposer
  GET  /runs/{run_id}/repair-attempts/{attempt_id}/proposer
  POST /runs/{run_id}/repair-attempts/{attempt_id}/reviewer
  POST /runs/{run_id}/repair-attempts/{attempt_id}/revisions
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.api.authentication import authenticated_actor
from app.api.repair_attempt_contracts import (
    ProposerCandidateDto,
    ProposerDiagnosisDto,
    ProposerRequestDto,
    ProposerResponseDto,
    ReviewDecisionDto,
    ReviewerRequestDto,
    ReviewResponseDto,
    RevisionRequestDto,
    RevisionResponseDto,
)
from app.artifact_store import LocalFilesystemArtifactStore
from app.core.config import Settings, get_settings
from app.domain.proposer import (
    ProposerArtifactInput,
    ProposerCandidate,
    ProposerRequest,
    ProposerStatus,
)
from app.domain.reviewer import (
    ProposerArtifactInput as ReviewerArtifactInput,
    ReviewRequest,
    ReviewerDecision,
)
from app.llm_gateway import AzureOpenAILLMGateway, MockLlmGateway, PromptSchemaRegistry
from app.repositories.models import ProposerResultModel
from app.repositories.session import session_scope
from app.services.proposer_application_service import (
    ProposerApplicationError,
    ProposerArtifact,
    ProposerArtifactReader,
    ProposerService,
)
from app.services.reviewer_application_service import (
    ReviewerApplicationError,
    ReviewerArtifact,
    ReviewerArtifactReader,
    ReviewerService,
)

router = APIRouter(prefix="/runs", tags=["repair-attempts"])


# ── Dependency-injection factories ───────────────────────────────────────────


def _build_gateway(settings: Settings) -> Any:
    """Construct the LLM gateway from application settings.

    Returns a real gateway when LLM is enabled, or a mock gateway for
    development / testing environments.
    """
    if settings.llm_enabled:
        registry = PromptSchemaRegistry(
            version="repair-agent-gateway-v1"
        )
        return AzureOpenAILLMGateway(settings=settings, registry=registry)
    return MockLlmGateway(settings=settings)


def _build_proposer_reader(settings: Settings) -> ProposerArtifactReader:
    """Wrap the filesystem artifact store as a ProposerArtifactReader."""
    store = LocalFilesystemArtifactStore(
        artifact_root=Path(settings.artifact_root or "")
    )

    def reader(artifact_id: str) -> ProposerArtifact:
        stored = store.read_artifact_by_id(artifact_id)
        return ProposerArtifact(
            artifact_id=stored.ref.artifact_id,
            checksum=stored.ref.checksum,
            content=stored.content,
        )

    return reader


def _build_reviewer_reader(settings: Settings) -> ReviewerArtifactReader:
    """Wrap the filesystem artifact store as a ReviewerArtifactReader."""
    store = LocalFilesystemArtifactStore(
        artifact_root=Path(settings.artifact_root or "")
    )

    def reader(artifact_id: str) -> ReviewerArtifact:
        stored = store.read_artifact_by_id(artifact_id)
        return ReviewerArtifact(
            artifact_id=stored.ref.artifact_id,
            checksum=stored.ref.checksum,
            content=stored.content,
        )

    return reader


def get_proposer_service(
    settings: Settings = Depends(get_settings),
) -> ProposerService:
    """Factory for the Repair Proposer service with current settings."""
    return ProposerService(
        gateway=_build_gateway(settings),
        artifact_reader=_build_proposer_reader(settings),
    )


def get_reviewer_service(
    settings: Settings = Depends(get_settings),
) -> ReviewerService:
    """Factory for the Repair Reviewer service with current settings."""
    return ReviewerService(
        gateway=_build_gateway(settings),
        artifact_reader=_build_reviewer_reader(settings),
    )


# ── Proposer endpoints ───────────────────────────────────────────────────────


def _proposer_result_model_to_dto(
    run_id: str,
    repair_attempt_id: str,
    record: ProposerResultModel,
) -> ProposerResponseDto:
    """Map a persisted ProposerResultModel to the API response DTO."""
    diagnosis_raw = record.diagnosis or {}
    candidate_raw = record.candidate

    diagnosis = ProposerDiagnosisDto(
        root_cause=diagnosis_raw.get("root_cause", ""),
        fix_strategy=diagnosis_raw.get("fix_strategy", ""),
        evidence_references=diagnosis_raw.get("evidence_references", []),
        confidence=diagnosis_raw.get("confidence", ""),
        deterministic_input_checksum=diagnosis_raw.get(
            "deterministic_input_checksum", ""
        ),
    )

    candidate = None
    if candidate_raw:
        candidate = ProposerCandidateDto(
            diff_content=candidate_raw.get("diff_content", ""),
            diff_checksum=candidate_raw.get("diff_checksum", ""),
            changed_files=candidate_raw.get("changed_files", []),
            risk_notes=candidate_raw.get("risk_notes", []),
            validation_notes=candidate_raw.get("validation_notes", []),
        )

    return ProposerResponseDto(
        run_id=run_id,
        repair_attempt_id=repair_attempt_id,
        status=ProposerStatus(record.status),
        proposer_invocation_id=record.proposer_invocation_id,
        diagnosis=diagnosis,
        candidate=candidate,
        model_provenance=record.model_provenance,
        usage=record.usage,
        prompt_version=record.prompt_version,
        schema_version=record.schema_version,
        revision_count=record.revision_count,
        artifact_set_checksum=record.artifact_set_checksum,
        proposer_output_checksum=record.proposer_output_checksum,
        workspace_fingerprint=record.workspace_fingerprint,
    )


@router.get(
    "/{run_id}/repair-attempts/{attempt_id}/proposer",
    response_model=ProposerResponseDto,
)
def get_proposer_result(
    run_id: str,
    attempt_id: str,
    request: Request,
    actor: str = Depends(authenticated_actor),
) -> ProposerResponseDto:
    """Retrieve the latest proposer result for a repair attempt."""
    with session_scope() as session:
        record = session.scalar(
            select(ProposerResultModel)
            .where(ProposerResultModel.run_id == run_id)
            .where(ProposerResultModel.repair_attempt_id == attempt_id)
            .order_by(ProposerResultModel.created_at.desc())
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Proposer result not found")

        return _proposer_result_model_to_dto(run_id, attempt_id, record)


@router.post(
    "/{run_id}/repair-attempts/{attempt_id}/proposer",
    response_model=ProposerResponseDto,
    status_code=201,
)
def generate_proposer(
    run_id: str,
    attempt_id: str,
    payload: ProposerRequestDto,
    request: Request,
    actor: str = Depends(authenticated_actor),
    service: ProposerService = Depends(get_proposer_service),
) -> ProposerResponseDto:
    """Invoke the Repair Proposer for a failure evidence + context pack pair."""
    try:
        effective_actor = payload.actor or actor
        correlation_id = payload.correlation_id or request.headers.get(
            "x-correlation-id"
        ) or str(uuid4())

        domain_request = ProposerRequest(
            run_id=run_id,
            repair_attempt_id=attempt_id,
            expected_state_version=payload.expected_state_version,
            idempotency_key=payload.idempotency_key,
            actor=effective_actor,
            failure_artifact=ProposerArtifactInput(
                artifact_id=payload.failure_artifact_id,
                checksum=payload.failure_checksum,
            ),
            context_pack_artifact=ProposerArtifactInput(
                artifact_id=payload.context_pack_artifact_id,
                checksum=payload.context_checksum,
            ),
            workspace_fingerprint=payload.workspace_fingerprint,
            correlation_id=correlation_id,
        )

        result = service.generate(domain_request)

        diagnosis = ProposerDiagnosisDto(
            root_cause=result.diagnosis.root_cause,
            fix_strategy=result.diagnosis.fix_strategy,
            evidence_references=result.diagnosis.evidence_references,
            confidence=result.diagnosis.confidence,
            deterministic_input_checksum=result.diagnosis.deterministic_input_checksum,
        )

        candidate = None
        if result.candidate is not None:
            candidate = ProposerCandidateDto(
                diff_content=result.candidate.diff_content,
                diff_checksum=result.candidate.diff_checksum,
                changed_files=result.candidate.changed_files,
                risk_notes=result.candidate.risk_notes,
                validation_notes=result.candidate.validation_notes,
            )

        return ProposerResponseDto(
            run_id=run_id,
            repair_attempt_id=attempt_id,
            status=result.status,
            proposer_invocation_id=result.proposer_invocation_id,
            diagnosis=diagnosis,
            candidate=candidate,
            model_provenance=result.model_provenance,
            usage=result.usage,
            prompt_version=result.prompt_version,
            schema_version=result.schema_version,
            revision_count=result.revision_count,
            artifact_set_checksum=result.artifact_set_checksum,
            proposer_output_checksum=result.proposer_output_checksum,
            workspace_fingerprint=result.workspace_fingerprint,
        )
    except ProposerApplicationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"error_code": error.code, "message": error.message},
        ) from error


# ── Reviewer endpoint ────────────────────────────────────────────────────────


@router.post(
    "/{run_id}/repair-attempts/{attempt_id}/reviewer",
    response_model=ReviewResponseDto,
    status_code=201,
)
def review_proposer_output(
    run_id: str,
    attempt_id: str,
    payload: ReviewerRequestDto,
    request: Request,
    actor: str = Depends(authenticated_actor),
    service: ReviewerService = Depends(get_reviewer_service),
) -> ReviewResponseDto:
    """Invoke the Repair Reviewer to evaluate a proposer candidate."""
    try:
        effective_actor = payload.actor or actor
        correlation_id = payload.correlation_id or request.headers.get(
            "x-correlation-id"
        ) or str(uuid4())

        # Build the ProposerCandidate from the review request fields
        candidate = ProposerCandidate(
            diff_content=payload.proposer_candidate_diff,
            diff_checksum=payload.proposer_candidate_checksum,
            changed_files=payload.proposer_candidate_files,
            risk_notes=payload.proposer_candidate_risks,
            validation_notes=payload.proposer_candidate_validations,
        )

        # Build context artifact inputs
        context_artifacts = []
        for aid in payload.context_artifact_ids:
            checksum = payload.context_artifact_checksums.get(aid, "")
            context_artifacts.append(
                ReviewerArtifactInput(artifact_id=aid, checksum=checksum)
            )

        domain_request = ReviewRequest(
            run_id=run_id,
            repair_attempt_id=attempt_id,
            proposal_id=payload.proposal_id,
            expected_state_version=payload.expected_state_version,
            idempotency_key=payload.idempotency_key,
            actor=effective_actor,
            proposer_candidate=candidate,
            context_artifacts=context_artifacts,
            workspace_fingerprint=payload.workspace_fingerprint,
            correlation_id=correlation_id,
            artifact_set_checksum=payload.artifact_set_checksum,
        )

        result = service.generate(domain_request)

        return _build_review_response(run_id, attempt_id, result)

    except ReviewerApplicationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"error_code": error.code, "message": error.message},
        ) from error


# ── Revision endpoint ────────────────────────────────────────────────────────


@router.post(
    "/{run_id}/repair-attempts/{attempt_id}/revisions",
    response_model=RevisionResponseDto,
    status_code=201,
)
def revise_proposer_output(
    run_id: str,
    attempt_id: str,
    payload: RevisionRequestDto,
    request: Request,
    actor: str = Depends(authenticated_actor),
    service: ReviewerService = Depends(get_reviewer_service),
) -> RevisionResponseDto:
    """Submit revision instructions for the Repair Reviewer to re-evaluate."""
    try:
        effective_actor = payload.actor or actor
        correlation_id = payload.correlation_id or request.headers.get(
            "x-correlation-id"
        ) or str(uuid4())

        # Build context artifact inputs
        context_artifacts = []
        for aid in payload.context_artifact_ids:
            checksum = payload.context_artifact_checksums.get(aid, "")
            context_artifacts.append(
                ReviewerArtifactInput(artifact_id=aid, checksum=checksum)
            )

        # Since the ReviewerService.generate() auto-revises internally, we
        # send a ReviewRequest that includes the revision instructions as
        # extra context artifacts.  The service will process them within its
        # bounded revision cycle.
        revision_ctx = ReviewerArtifactInput(
            artifact_id=f"revision-ctx-{uuid4().hex[:8]}",
            checksum=payload.workspace_fingerprint,
        )

        domain_request = ReviewRequest(
            run_id=run_id,
            repair_attempt_id=attempt_id,
            proposal_id=payload.proposal_id,
            expected_state_version=payload.expected_state_version,
            idempotency_key=f"{payload.idempotency_key}:revise",
            actor=effective_actor,
            proposer_candidate=ProposerCandidate(
                diff_content="",
                diff_checksum=payload.workspace_fingerprint,
                changed_files=[],
                risk_notes=payload.revision_instructions,
                validation_notes=[],
            ),
            context_artifacts=context_artifacts + [revision_ctx],
            workspace_fingerprint=payload.workspace_fingerprint,
            correlation_id=correlation_id,
            artifact_set_checksum=revision_ctx.checksum,
        )

        result = service.generate(domain_request)

        review_response = _build_review_response(run_id, attempt_id, result)

        return RevisionResponseDto(
            **review_response.model_dump(mode="json"),
            revision_cycle_complete=(
                result.revision_count == 0
                or result.decision
                in {ReviewerDecision.ACCEPT, ReviewerDecision.REJECT}
            ),
        )

    except ReviewerApplicationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"error_code": error.code, "message": error.message},
        ) from error


# ── Shared helpers ───────────────────────────────────────────────────────────


def _build_review_response(
    run_id: str,
    attempt_id: str,
    result: Any,
) -> ReviewResponseDto:
    """Map a domain ReviewResult to the API ReviewResponseDto."""
    rd = result.review_decision
    decision_dto = ReviewDecisionDto(
        review_id=rd.review_id,
        proposal_id=rd.proposal_id,
        reviewer_invocation_id=rd.reviewer_invocation_id,
        decision=rd.decision.value
        if hasattr(rd.decision, "value")
        else str(rd.decision),
        proposal_diff_checksum=rd.proposal_diff_checksum,
        review_checksum=rd.review_checksum,
        critique=rd.critique,
        revision_instructions=rd.revision_instructions,
        requested_context=rd.requested_context,
    )

    return ReviewResponseDto(
        run_id=run_id,
        repair_attempt_id=attempt_id,
        proposal_id=result.proposal_id,
        decision=result.decision.value
        if hasattr(result.decision, "value")
        else str(result.decision),
        review_decision=decision_dto,
        review_output_checksum=result.review_output_checksum,
        model_provenance=result.model_provenance,
        usage=result.usage,
        prompt_version=result.prompt_version,
        schema_version=result.schema_version,
        revision_count=result.revision_count,
        workspace_fingerprint=result.workspace_fingerprint,
    )
