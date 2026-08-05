"""Governed repair proposal/review and deterministic semantic validation."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from difflib import unified_diff
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.artifact_store import (
    ArtifactNotFoundError,
    ArtifactStoreError,
    LocalFilesystemArtifactStore,
    StoredArtifact,
)
from app.core.config import get_settings
from app.domain.command import TRANSFORMATION_COMMAND_CATALOGUE
from app.domain.contracts import AgentKind, ArtifactType, WorkflowEventType
from app.domain.planning import (
    CommandTemplateReference,
    SUPPORTED_VALIDATION_TARGETS,
    ValidationTarget,
)
from app.llm_gateway import (
    AzureGatewayError,
    AzureOpenAILLMGateway,
    LlmContextSegment,
    LlmFailureCode,
    LlmRequest,
    LlmRole,
    LlmTaskType,
    PromptRegistry,
    PromptSchemaRegistry,
)
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    LlmInvocationModel,
    MigrationRunModel,
    RepairAttemptModel,
    RepairFingerprintRecoveryModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageGatePackageModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    UsageCostRecordModel,
    WorkflowEventModel,
)
from app.services.causal_review import CausalRejection, REVIEWER_CAUSAL_POLICY, causal_rejection
from app.services.dependency_closure_service import (
    installed_dependency_version,
    is_exact_version,
    validate_dependency_transition_evidence,
    verify_dependency_transition_state,
)
from app.services.failure_evidence_service import FailureEvidenceService, validate_context_pack
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformation_continuation_service import append_continuation_event
from app.services.workspace_fingerprint import (
    STAGE_FINGERPRINT_PROFILE,
    SUPPORTED_LEGACY_FINGERPRINT_PROFILES,
)


class RequiredPeerRange(BaseModel):
    model_config = ConfigDict(extra='forbid')

    package: str
    version_range: str


class RequiredPeerRangeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: str | None = None
    version_range: str | None = None


class BlockingDependencyCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    package: str
    installed_version: str | None
    required_peer_ranges: list[RequiredPeerRange] = Field(max_length=32)


class BlockingDependencyCandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: str | None = None
    installed_version: str | None = None
    required_peer_ranges: list[RequiredPeerRangeCandidate] | None = Field(
        default=None, max_length=32
    )


class TargetStateCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    package: str
    target_version: str
    angular_major: int


class TargetStateCandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: str | None = None
    target_version: str | None = None
    angular_major: int | None = None


class ProvenanceEntry(BaseModel):
    model_config = ConfigDict(extra='forbid')

    key: str
    value: str


def _normalize_provenance(value: object) -> list[dict[str, str]]:
    entries = value if isinstance(value, list) else []
    if all(
        isinstance(entry, dict) and set(entry) == {'key', 'value'}
        for entry in entries
    ):
        return entries
    return [
        {'key': key, 'value': str(entry_value)}
        for entry in entries
        if isinstance(entry, dict)
        for key, entry_value in entry.items()
    ]


class RepairApplicationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RepairLlmError(RepairApplicationError):
    """Translated gateway failure; safe, bounded, and durable for graph routing."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        provider_status: int | None,
        provider_request_id: str | None,
        failure_stage: str | None,
        failure_subtype: str | None,
    ) -> None:
        super().__init__(code, message)
        self.retryable = retryable
        self.provider_status = provider_status
        self.provider_request_id = provider_request_id
        self.failure_stage = failure_stage
        self.failure_subtype = failure_subtype


logger = logging.getLogger(__name__)


_GATEWAY_FAILURE_CODES = {
    LlmFailureCode.TRANSPORT: "LLM_TRANSPORT_FAILED",
    LlmFailureCode.PROTOCOL: "LLM_PROTOCOL_FAILED",
    LlmFailureCode.SCHEMA: "LLM_SCHEMA_VALIDATION_FAILED",
    LlmFailureCode.SEMANTIC: "LLM_SCHEMA_VALIDATION_FAILED",
    LlmFailureCode.DEPLOYMENT: "LLM_DEPLOYMENT_INVALID",
    LlmFailureCode.CAPABILITY: "LLM_CAPABILITY_INVALID",
    LlmFailureCode.QUOTA: "LLM_QUOTA_EXCEEDED",
    LlmFailureCode.CONTENT_FILTER: "LLM_CONTENT_FILTERED",
    LlmFailureCode.EMPTY_OUTPUT: "LLM_EMPTY_OUTPUT",
    LlmFailureCode.BUDGET: "LLM_BUDGET_EXCEEDED",
    LlmFailureCode.CANCELLATION: "LLM_CANCELLED",
}

_DEPENDENCY_SECTIONS = frozenset(
    {"dependencies", "devDependencies", "peerDependencies", "optionalDependencies"}
)
_DEPENDENCY_TRANSITION_TARGET_SECTIONS = ("dependencies", "devDependencies")
_DEPENDENCY_TRANSITION_VALID_REPAIR_KINDS = frozenset({"dependency_transition"})
_DEPENDENCY_TRANSITION_VALID_FAILURE_TYPES = frozenset({"peer_dependency_conflict"})
_DEPENDENCY_TRANSITION_VALID_STRATEGIES = frozenset({"detach_update_reattach"})
_SEMANTIC_RETRY_CODES = frozenset(
    {
        "REPAIR_REPLACEMENT_MISSING",
        "REPAIR_REPLACEMENT_AMBIGUOUS",
        "REPAIR_PREIMAGE_STALE",
        "REPAIR_CAUSAL_REJECTION",
        "REPAIR_DEPENDENCY_INTENT_INVALID",
        "REPAIR_PATH_INVALID",
    }
)
_PROPOSER_GROUNDING_INSTRUCTIONS = (
    "CURRENT_WORKSPACE_FILES are the only valid preimage authority. "
    "PREVIOUS_PROPOSAL is reference-only and has not been applied. "
    "Generate the revised proposal directly from the current authoritative workspace state. "
    "Never use previous_proposal.new_text as old_text unless that exact value exists in "
    "CURRENT_WORKSPACE_FILES."
)
_SEMANTIC_RETRY_FEEDBACK = (
    "The candidate does not match the current authoritative workspace. "
    "The previous proposal was not applied. "
    "Regenerate using the exact current file content."
)
_UNIFIED_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _version_major(value: object) -> int | None:
    match = re.match(r"\s*[~^]?\s*(\d+)", str(value or ""))
    return int(match.group(1)) if match else None


def _render_dependency_transition_intent(operation: dict[str, object]) -> str:
    blocking = operation.get("blocking_dependency") or {}
    target = operation.get("target_state") or {}
    package = str(blocking.get("package") or "")
    target_version = str(target.get("target_version") or "")
    major = target.get("angular_major") or "?"
    checkpoint_id = str(operation.get("checkpoint_id") or "")
    lines = [
        "schema_version: transformer-repair-v2",
        "repair_kind: dependency_transition",
        f"strategy: {str(operation.get('strategy') or 'detach_update_reattach')}",
        f"failure_type: {str(operation.get('failure_type') or 'peer_dependency_conflict')}",
        f"blocking_dependency: {package}",
        f"target_state: angular {major} / {package}@{target_version}",
        f"checkpoint_id: {checkpoint_id}",
        (
            f"executed_commands: npm uninstall {package} → "
            f"ng update @angular/cli@{major} @angular/core@{major} --allow-dirty → "
            f"npm install --save-dev --save-exact {package}@{target_version} → npm ci"
        ),
    ]
    return "\n".join(lines) + "\n"


def _unified_diff_header_path(line: str, path_prefix: str) -> str:
    return line[4:].split("\t", 1)[0].strip().removeprefix(path_prefix)


def _bounded_text(value: object, limit: int = 240) -> str | None:
    if value is None:
        return None
    return str(value).replace("\r", " ").replace("\n", " ")[:limit]


def _normalized_newlines(text: str) -> str:
    """Normalize CRLF/CR/LF to LF so line endings never block text matching."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _dominant_newline(text: str) -> str:
    """Return the dominant line ending of raw file text (CRLF or LF).

    CRLF wins when CRLF line endings outnumber LF-only line endings;
    otherwise LF. ``text`` must be read without universal-newline
    translation (``open(..., newline="")``) so CRLF survives into it;
    otherwise the dominant style is undetectable.
    """
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def replace_text_once(target_text: str, old_text: str, new_text: str) -> str:
    """Deterministic single-preimage text replacement for repair render/apply.

    Shared by the safe-diff renderer, proposal validation, and the apply
    preparer so the diff the operator approves and the mutation the apply
    performs can never disagree. Matching is newline-insensitive: the target
    and the preimage are compared after canonicalizing ``\\r\\n`` (and legacy
    ``\\r``) to ``\\n``, so a CRLF preimage matches an LF file and vice versa,
    and a literal ``\\r\\n`` preimage matches a CRLF file exactly once. The
    output re-emits the target's dominant newline style (CRLF when CRLF line
    endings outnumber LF-only line endings, else LF) so the file's original
    line-ending convention survives the rewrite. Callers must pass
    ``target_text`` read without universal-newline translation
    (``open(..., "r", encoding="utf-8", newline="")``); otherwise CRLF is
    translated away before it can be detected and a CRLF file would be
    flattened to LF. Requires exactly one unique preimage: missing
    (count==0) and ambiguous (count>1) preimages, empty preimages, and
    no-op replacements all fail closed.
    """
    if not old_text:
        raise RepairApplicationError(
            "REPAIR_REPLACEMENT_INVALID", "Replacement preimage must not be empty"
        )
    normalized_target = _normalized_newlines(target_text)
    normalized_old = _normalized_newlines(old_text)
    if normalized_old == _normalized_newlines(new_text):
        raise RepairApplicationError(
            "REPAIR_REPLACEMENT_NOOP", "Replacement preimage and replacement text are identical"
        )
    count = normalized_target.count(normalized_old)
    if count == 0:
        raise RepairApplicationError(
            "REPAIR_REPLACEMENT_MISSING",
            "Replacement preimage must occur exactly once; found zero matches",
        )
    if count > 1:
        raise RepairApplicationError(
            "REPAIR_REPLACEMENT_AMBIGUOUS",
            "Replacement preimage must occur exactly once; found multiple matches",
        )
    normalized_after = normalized_target.replace(normalized_old, _normalized_newlines(new_text), 1)
    if normalized_after == normalized_target:
        raise RepairApplicationError(
            "REPAIR_REPLACEMENT_NOOP", "Replacement produced no change"
        )
    if _dominant_newline(target_text) == "\r\n":
        return normalized_after.replace("\n", "\r\n")
    return normalized_after


def _legacy_recovery_error(
    reason: str,
    *,
    code: str = "REPAIR_WORKSPACE_STALE",
    details: dict[str, object] | None = None,
    cause: BaseException | None = None,
) -> RepairApplicationError:
    payload = {"reason": reason, "transaction_rollback": True, **(details or {})}
    message = "Legacy fingerprint recovery diagnostic: " + json.dumps(
        payload, sort_keys=True, default=str
    )
    logger.warning("legacy fingerprint recovery blocked", extra={"diagnostic": payload})
    error = RepairApplicationError(code, message)
    error.diagnostic = payload
    if cause is not None:
        error.__cause__ = cause
    return error

def _context_invocation_key(context: dict[str, object], role) -> str:
    return str(context.get("invocation_key") or _invocation_key(str(context["attempt_id"]), role))



def _integrity_diagnostic(error: IntegrityError) -> dict[str, object]:
    original = error.orig
    return {
        "exception_type": type(error).__name__,
        "original_exception_type": type(original).__name__,
        "constraint_name": _bounded_text(getattr(getattr(original, "diag", None), "constraint_name", None)),
        "sqlite_error_name": _bounded_text(getattr(original, "sqlite_errorname", None)),
        "original_message": _bounded_text(original),
    }


def _invocation_key(attempt_id: str, role) -> str:
    if isinstance(role, LlmRole):
        role = role.value.removeprefix("repair_")
    return f"{attempt_id}:{role}"


def _review_validation_message(error: ValidationError) -> str:
    first = error.errors()[0] if error.errors() else {}
    loc = ".".join(str(part) for part in first.get("loc", ()))
    return (
        _bounded_text(f"{loc} {first.get('type', '')}".strip())
        or "Repair review failed schema validation"
    )


def _repair_llm_error(code, message, exc: AzureGatewayError, *, retryable: bool) -> RepairLlmError:
    error = RepairLlmError(
        code,
        message,
        retryable=retryable,
        provider_status=exc.provider_status,
        provider_request_id=exc.provider_request_id,
        failure_stage=exc.failure_stage,
        failure_subtype=exc.failure_subtype,
    )
    error.__cause__ = exc
    return error


def _translate_gateway_failure(exc: AzureGatewayError) -> RepairLlmError:
    message = str(exc)
    if exc.code == LlmFailureCode.AUTHORIZATION and "Prompt policy is not registered" in message:
        return _repair_llm_error("LLM_PROMPT_POLICY_MISSING", message, exc, retryable=False)
    if exc.code == LlmFailureCode.SCHEMA and "Response schema is not registered" in message:
        return _repair_llm_error("LLM_SCHEMA_POLICY_MISSING", message, exc, retryable=False)
    if exc.code == LlmFailureCode.CONFIGURATION:
        return _repair_llm_error("LLM_CONFIGURATION_INVALID", message, exc, retryable=False)
    if exc.code == LlmFailureCode.INVALID_REQUEST or exc.provider_status == 400:
        return _repair_llm_error("LLM_PROVIDER_BAD_REQUEST", message, exc, retryable=False)
    if (
        exc.code in {LlmFailureCode.AUTHENTICATION, LlmFailureCode.AUTHORIZATION}
        or exc.provider_status in {401, 403}
    ):
        return _repair_llm_error("LLM_PROVIDER_AUTH", message, exc, retryable=False)
    if exc.code == LlmFailureCode.TIMEOUT or exc.provider_status == 408:
        return _repair_llm_error("LLM_PROVIDER_TIMEOUT", message, exc, retryable=True)
    if exc.code == LlmFailureCode.RATE_LIMIT or exc.provider_status == 429:
        return _repair_llm_error("LLM_PROVIDER_RATE_LIMIT", message, exc, retryable=True)
    if exc.code == LlmFailureCode.SERVER or (exc.provider_status or 0) >= 500:
        return _repair_llm_error("LLM_PROVIDER_UNAVAILABLE", message, exc, retryable=True)
    return _repair_llm_error(
        _GATEWAY_FAILURE_CODES.get(exc.code, "LLM_GATEWAY_FAILED"),
        message,
        exc,
        retryable=exc.retryable,
    )


class RepairOperationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal[
        "replace_text",
        "create_text_file",
        "delete_text_file",
        "dependency_change",
        "dependency_transition",
    ]
    path: str
    old_text: str | None = None
    new_text: str | None = None
    content: str | None = None
    section: str | None = Field(default=None, min_length=1, max_length=64)
    package: str | None = Field(default=None, min_length=1, max_length=256)
    new_version: str | None = Field(default=None, min_length=1, max_length=256)
    repair_kind: str | None = Field(default=None, min_length=1, max_length=64)
    failure_type: str | None = Field(default=None, min_length=1, max_length=64)
    strategy: str | None = Field(default=None, min_length=1, max_length=64)
    checkpoint_id: str | None = Field(default=None, max_length=128)
    schema_version: str | None = Field(default=None, min_length=1, max_length=64)
    blocking_dependency: BlockingDependencyCandidateInput | None = None
    target_state: TargetStateCandidateInput | None = None
    provenance: list[ProvenanceEntry] = Field(default_factory=list, max_length=32)


class RepairOperation(RepairOperationCandidate):
    preimage_sha256: str | None = None


class RepairProposalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_format: Literal["operations", "unified_diff"]
    operations: list[RepairOperationCandidate] = Field(max_length=32)
    unified_diff: str | None = Field(default=None, max_length=100_000)
    rationale: list[str] = Field(min_length=1, max_length=16)
    risk_level: Literal["low", "medium", "high"]
    validation_targets: list[ValidationTarget] = Field(min_length=1, max_length=16)
    limitations: list[str] = Field(max_length=16)


class RepairProposal(RepairProposalCandidate):
    failure_evidence_checksum: str
    context_pack_checksum: str
    operations: list[RepairOperation] = Field(max_length=32)
    touched_files: list[str] = Field(min_length=1, max_length=32)


class RepairReviewCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accept", "request_changes", "reject"]
    findings: list[str] = Field(max_length=32)
    policy_checks: list[str] = Field(min_length=1, max_length=32)
    risk_assessment: str = Field(min_length=1, max_length=2000)
    required_validation_targets: list[ValidationTarget] = Field(min_length=1, max_length=16)
    limitations: list[str] = Field(max_length=16)


class RepairReview(RepairReviewCandidate):
    proposal_checksum: str


class RepairApplicationService:
    proposer_schema = "repair_proposer_candidate_v2"
    reviewer_schema = "repair_reviewer_candidate_v2"
    supported_validation_targets = SUPPORTED_VALIDATION_TARGETS
    forbidden_parts = {
        ".git",
        "node_modules",
        "dist",
        "build",
        "artifacts",
        ".env",
        "package-lock.json",
        "npm-shrinkwrap.json",
    }

    def __init__(self, *, scope, gateway=None, now_provider=None) -> None:
        self._scope = scope
        self._gateway = gateway
        self._now = now_provider or (lambda: datetime.now(UTC))

    def propose(self, attempt_id: str) -> dict[str, object]:
        self.recover_legacy_fingerprint_authority(attempt_id)
        self._recover_legacy_context_pack(attempt_id)
        semantic_retry_count = 0
        retry_of_invocation_key = None
        while True:
            context = self._attempt_context(attempt_id)
            if not semantic_retry_count and context.get("proposer_invocation_id"):
                context["invocation_key"] = str(context["proposer_invocation_id"])
                if ":semantic-retry-" in context["invocation_key"]:
                    semantic_retry_count = 1
            if semantic_retry_count:
                context["semantic_retry_count"] = semantic_retry_count
                context["retry_of_invocation_key"] = retry_of_invocation_key
                context["invocation_key"] = (
                    f"{attempt_id}:proposer:semantic-retry-{semantic_retry_count}"
                )
                context["segments"].append(_SEMANTIC_RETRY_FEEDBACK)
            recovered = self._recover_completed(
                context,
                role="proposer",
                schema_name=self.proposer_schema,
                task_type=LlmTaskType.REPAIR_DIAGNOSIS,
                schema=RepairProposalCandidate,
            )
            if recovered is not None:
                return recovered
            context = self._start_invocation(
                context,
                role=LlmRole.REPAIR_PROPOSER,
                task_type=LlmTaskType.REPAIR_DIAGNOSIS,
                schema_name=self.proposer_schema,
                schema=RepairProposalCandidate,
            )
            if "_recovered_result" in context:
                return context["_recovered_result"]
            try:
                output, response = self._call(
                    context,
                    role=LlmRole.REPAIR_PROPOSER,
                    task=LlmTaskType.REPAIR_DIAGNOSIS,
                    schema_name=self.proposer_schema,
                    schema=RepairProposalCandidate,
                    policy=(
                        "Author one minimal repair candidate from untrusted evidence. Never emit commands, "
                        "lockfile edits, path escapes, secrets, or policy bypasses. "
                        "For Angular peer-dependency-conflict failures (failure_type "
                        "\"peer_dependency_conflict\"), emit exactly one \"dependency_transition\" "
                        "operation (schema_version \"transformer-repair-v2\", repair_kind "
                        "\"dependency_transition\", strategy \"detach_update_reattach\", path "
                        "\"package.json\"). Provide only rationale, risk_level, strategy, "
                        "limitations, and validation_targets; omit checkpoint_id, package identity, "
                        "installed_version, peer ranges, target package, and target exact version. "
                        "The backend binds those fields. Never emit file operations, READMEs, "
                        "comments, or --force for such failures. "
                        + _PROPOSER_GROUNDING_INSTRUCTIONS
                    ),
                )
            except RepairLlmError:
                raise
            except RepairApplicationError as error:
                self._persist_failure(
                    context, LlmRole.REPAIR_PROPOSER, error, failure_stage_override="local"
                )
                raise
            try:
                context = self._assert_fresh_authority(context, role="proposer")
                proposal = self.validate_proposal(self._bind_proposal_candidate(output, context), context)
            except RepairApplicationError as error:
                self._persist_failure(
                    context,
                    LlmRole.REPAIR_PROPOSER,
                    error,
                    failure_stage_override="repair_semantics",
                    response=response,
                    rejected_candidate=output,
                )
                if error.code in _SEMANTIC_RETRY_CODES and semantic_retry_count == 0:
                    retry_of_invocation_key = _context_invocation_key(context, LlmRole.REPAIR_PROPOSER)
                    semantic_retry_count = 1
                    continue
                raise
            stored = self._write(context, "proposal", proposal)
            try:
                safe_diff = self._write_safe_diff(context, proposal, stored.ref.checksum)
            except (ArtifactStoreError, OSError, UnicodeError) as cause:
                self._remove_uncommitted_artifact(stored)
                error = RepairApplicationError(
                    "REPAIR_DIFF_ARTIFACT_FAILED", "Safe repair diff could not be persisted"
                )
                self._persist_failure(
                    context,
                    LlmRole.REPAIR_PROPOSER,
                    error,
                    failure_stage_override="artifact_persistence",
                    response=response,
                )
                raise error from cause
            try:
                self._persist_call(
                    context,
                    response,
                    stored,
                    role="proposer",
                    schema_name=self.proposer_schema,
                    summary=proposal,
                    additional_stored=(safe_diff,),
                )
            except RepairApplicationError as error:
                self._remove_uncommitted_artifact(stored)
                self._remove_uncommitted_artifact(safe_diff)
                self._persist_failure(
                    context,
                    LlmRole.REPAIR_PROPOSER,
                    error,
                    failure_stage_override="authority_check",
                    response=response,
                )
                raise
            return proposal

    def review(self, attempt_id: str) -> dict[str, object]:
        self.recover_legacy_fingerprint_authority(attempt_id)
        context = self._attempt_context(attempt_id, include_proposal=True)
        if context.get("parent_attempt_id"):
            independent_context = json.loads(str(context["segments"][1]))
            independent_context.pop("human_revision", None)
            context["segments"][1] = json.dumps(
                independent_context, sort_keys=True, indent=2
            )
        recovered = self._recover_completed(
            context,
            role="reviewer",
            schema_name=self.reviewer_schema,
            task_type=LlmTaskType.REPAIR_REVIEW,
            schema=RepairReviewCandidate,
        )
        if recovered is not None:
            return recovered
        context = self._start_invocation(
            context,
            role=LlmRole.REPAIR_REVIEWER,
            task_type=LlmTaskType.REPAIR_REVIEW,
            schema_name=self.reviewer_schema,
            schema=RepairReviewCandidate,
        )
        if "_recovered_result" in context:
            return context["_recovered_result"]
        try:
            output, response = self._call(
                context,
                role=LlmRole.REPAIR_REVIEWER,
                task=LlmTaskType.REPAIR_REVIEW,
                schema_name=self.reviewer_schema,
                schema=RepairReviewCandidate,
                policy=(
                    "Review the supplied proposal against policy. Never author operations, a diff, "
                    "replacement code, commands, or a different proposal.\n" + REVIEWER_CAUSAL_POLICY
                ),
            )
        except RepairLlmError:
            raise
        except RepairApplicationError as error:
            self._persist_failure(
                context, LlmRole.REPAIR_REVIEWER, error, failure_stage_override="local"
            )
            raise
        try:
            context = self._assert_fresh_authority(context, role="reviewer", include_proposal=True)
            review = self._bind_review_candidate(output, context)
        except (RepairApplicationError, ValidationError) as error:
            semantic_error = (
                error
                if isinstance(error, RepairApplicationError)
                else RepairApplicationError(
                    "REPAIR_REVIEW_INVALID", _review_validation_message(error)
                )
            )
            self._persist_failure(
                context,
                LlmRole.REPAIR_REVIEWER,
                semantic_error,
                failure_stage_override="repair_semantics",
                response=response,
            )
            raise semantic_error
        if review["proposal_checksum"] != context["proposal_checksum"]:
            error = RepairApplicationError("REPAIR_REVIEW_STALE", "Reviewer bound a different proposal")
            self._persist_failure(
                context,
                LlmRole.REPAIR_REVIEWER,
                error,
                failure_stage_override="repair_semantics",
                response=response,
            )
            raise error
        stored = self._write(context, "review", review)
        try:
            self._persist_call(
                context,
                response,
                stored,
                role="reviewer",
                schema_name=self.reviewer_schema,
                summary=review,
            )
        except RepairApplicationError as error:
            self._remove_uncommitted_artifact(stored)
            self._persist_failure(
                context, LlmRole.REPAIR_REVIEWER, error,
                failure_stage_override="authority_check", response=response,
            )
            raise
        return review

    def request_revision(
        self,
        *,
        attempt_id: str,
        proposal_id: str,
        base_checksum: str,
        instruction: str,
        idempotency_key: str,
        actor: str,
    ) -> dict[str, object]:
        request_checksum = self._request_checksum(
            {
                "attempt_id": attempt_id,
                "proposal_id": proposal_id,
                "base_checksum": base_checksum,
                "instruction": instruction,
                "actor": actor,
            }
        )
        replay = self._revision_replay(attempt_id, idempotency_key, request_checksum)
        if replay is not None:
            return replay
        context = self._attempt_context(
            attempt_id, include_proposal=True, include_review=True
        )
        if (
            context["proposal_artifact_id"] != proposal_id
            or context["proposal_checksum"] != base_checksum
        ):
            raise RepairApplicationError(
                "REPAIR_PROPOSAL_STALE", "Repair proposal binding changed"
            )
        try:
            proposal = RepairProposal.model_validate_json(
                str(context["segments"][2])
            ).model_dump(mode="json")
            review = RepairReview.model_validate_json(
                str(context["segments"][3])
            ).model_dump(mode="json")
        except ValidationError as error:
            raise RepairApplicationError(
                "REPAIR_ARTIFACT_RECOVERY_FAILED",
                "Repair proposal or review artifact is invalid",
            ) from error
        if review["proposal_checksum"] != base_checksum:
            raise RepairApplicationError(
                "REPAIR_REVIEW_STALE", "Repair review proposal binding changed"
            )
        if review.get("decision") not in {"accept", "request_changes"}:
            raise RepairApplicationError(
                "REPAIR_REVISION_NOT_ALLOWED",
                "Only an accepted or request-changes review can be revised",
            )
        child_id = f"repair-{context['stage_id']}-{int(context['attempt_number']) + 1}"
        revision_context = json.loads(str(context["segments"][1]))
        revision_context["human_revision"] = {
            "instruction": instruction,
            "parent_attempt_id": attempt_id,
            "parent_proposal_id": proposal_id,
            "parent_proposal_checksum": base_checksum,
            "previous_proposal": proposal,
            "reviewer_output": review,
            "grounding_instructions": _PROPOSER_GROUNDING_INSTRUCTIONS,
        }
        stored = self._write_revision_context(
            context,
            child_id=child_id,
            payload=revision_context,
            instruction=instruction,
        )
        try:
            with self._scope() as session:
                attempt = session.get(RepairAttemptModel, attempt_id)
                continuation = session.scalar(
                    select(TransformationContinuationModel).where(
                        TransformationContinuationModel.run_id == context["run_id"],
                    )
                )
                existing = self._revision_event(session, continuation, idempotency_key)
                if existing is not None:
                    if (existing.payload or {}).get("request_checksum") != request_checksum:
                        raise RepairApplicationError(
                            "IDEMPOTENCY_PAYLOAD_MISMATCH",
                            "Revision key has a different payload",
                        )
                    self._remove_uncommitted_artifact(stored)
                    return self._revision_result(session, existing)
                latest = session.scalar(
                    select(RepairAttemptModel)
                    .where(
                        RepairAttemptModel.run_id == context["run_id"],
                        RepairAttemptModel.stage_id == context["stage_id"],
                    )
                    .order_by(RepairAttemptModel.attempt_number.desc())
                    .limit(1)
                )
                if attempt is None or continuation is None or latest is None:
                    raise RepairApplicationError(
                        "REPAIR_AUTHORITY_MISSING", "Repair revision authority is missing"
                    )
                if latest.id != attempt.id:
                    raise RepairApplicationError(
                        "REPAIR_ATTEMPT_SUPERSEDED",
                        "Superseded repair attempts cannot be revised",
                    )
                if (
                    attempt.proposal_artifact_id != proposal_id
                    or attempt.proposal_checksum != base_checksum
                ):
                    raise RepairApplicationError(
                        "REPAIR_PROPOSAL_STALE", "Repair proposal binding changed"
                    )
                if attempt.attempt_number >= continuation.max_attempts:
                    raise RepairApplicationError(
                        "REPAIR_LOOP_EXHAUSTED",
                        "Repair revision limit has been reached",
                    )
                binding = session.scalar(
                    select(StageWorkspaceBindingModel).where(
                        StageWorkspaceBindingModel.run_id == attempt.run_id,
                        StageWorkspaceBindingModel.stage_id == attempt.stage_id,
                        StageWorkspaceBindingModel.active.is_(True),
                    )
                )
                try:
                    live_fingerprint = (
                        StageSandboxCopier.fingerprint(Path(binding.workspace_path))
                        if binding is not None
                        else None
                    )
                except OSError as error:
                    raise RepairApplicationError(
                        "REPAIR_WORKSPACE_STALE", "Repair workspace is unavailable"
                    ) from error
                if binding is None or live_fingerprint != attempt.pre_fingerprint:
                    raise RepairApplicationError(
                        "REPAIR_WORKSPACE_STALE", "Repair workspace fingerprint changed"
                    )
                pending_g10 = session.scalar(
                    select(StageGatePackageModel).where(
                        StageGatePackageModel.run_id == attempt.run_id,
                        StageGatePackageModel.stage_id == attempt.stage_id,
                        StageGatePackageModel.gate_id == "G10",
                        StageGatePackageModel.status == "pending",
                    )
                )
                reviewer_revision = (
                    attempt.status == "request_changes"
                    and review["decision"] == "request_changes"
                    and continuation.current_stage_id == attempt.stage_id
                    and continuation.status == "waiting_repair_revision"
                    and continuation.current_node == "review_repair"
                )
                accepted_revision = (
                    attempt.status == "waiting_g10"
                    and review["decision"] == "accept"
                    and continuation.current_stage_id == attempt.stage_id
                    and continuation.status == "waiting_gate"
                    and continuation.current_node == "wait_g10"
                    and pending_g10 is not None
                    and attempt.g10_gate_package_id == pending_g10.id
                )
                g10_override_revision = (
                    attempt.status == "waiting_g10"
                    and review["decision"] == "request_changes"
                    and continuation.current_stage_id == attempt.stage_id
                    and continuation.status == "waiting_gate"
                    and continuation.current_node == "wait_g10"
                    and pending_g10 is not None
                    and attempt.g10_gate_package_id == pending_g10.id
                )
                if not reviewer_revision and not accepted_revision and not g10_override_revision:
                    raise RepairApplicationError(
                        "REPAIR_REVISION_NOT_ALLOWED",
                        "Repair attempt is not in its live human revision state",
                    )
                if accepted_revision or g10_override_revision:
                    pending_g10.status = "stale"
                    pending_g10.stale_at = self._now()
                self._register_artifact_metadata(session, context, stored)
                child = RepairAttemptModel(
                    id=child_id,
                    run_id=attempt.run_id,
                    stage_id=attempt.stage_id,
                    attempt_number=attempt.attempt_number + 1,
                    status="evidence_frozen",
                    risk_level="unknown",
                    diagnosis=f"human revision; parent={attempt.id}",
                    checkpoint_id=attempt.checkpoint_id,
                    failure_evidence_artifact_id=attempt.failure_evidence_artifact_id,
                    failure_evidence_checksum=attempt.failure_evidence_checksum,
                    failure_route_artifact_id=attempt.failure_route_artifact_id,
                    failure_route_checksum=attempt.failure_route_checksum,
                    context_pack_artifact_id=stored.ref.artifact_id,
                    context_pack_checksum=stored.ref.checksum,
                    pre_fingerprint=attempt.pre_fingerprint,
                    failure_fingerprint=attempt.failure_fingerprint,
                    parent_attempt_id=attempt.id,
                    parent_review_artifact_id=attempt.review_artifact_id,
                    parent_review_checksum=attempt.review_checksum,
                    created_at=self._now(),
                    updated_at=self._now(),
                )
                session.add(child)
                attempt.status = "superseded"
                attempt.updated_at = self._now()
                expected_state_version = continuation.state_version
                continuation.status = "queued"
                continuation.current_node = "propose_repair"
                continuation.worker_id = None
                continuation.lease_expires_at = None
                continuation.wake_sequence += 1
                continuation.state_version += 1
                continuation.updated_at = self._now()
                session.flush()
                append_continuation_event(
                    session,
                    continuation,
                    event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED,
                    key=self._revision_event_key(idempotency_key),
                    reason="human repair revision requested",
                    actor=actor,
                    payload={
                        "attempt_id": attempt.id,
                        "child_attempt_id": child.id,
                        "request_checksum": request_checksum,
                        "expected_state_version": expected_state_version,
                    },
                )
                return {
                    "attempt_id": child.id,
                    "status": child.status,
                    "idempotent_replay": False,
                }
        except IntegrityError:
            self._remove_uncommitted_artifact(stored)
            replay = self._revision_replay(attempt_id, idempotency_key, request_checksum)
            if replay is not None:
                return replay
            raise RepairApplicationError(
                "REPAIR_REVISION_CONFLICT", "Concurrent repair revision could not be resolved"
            )
        except RepairApplicationError:
            self._remove_uncommitted_artifact(stored)
            raise

    def reject(
        self,
        *,
        attempt_id: str,
        proposal_id: str,
        base_checksum: str,
        idempotency_key: str,
        actor: str,
    ) -> dict[str, object]:
        request_checksum = self._request_checksum(
            {
                "attempt_id": attempt_id,
                "proposal_id": proposal_id,
                "base_checksum": base_checksum,
                "actor": actor,
            }
        )
        with self._scope() as session:
            attempt = session.get(RepairAttemptModel, attempt_id)
            if attempt is None:
                raise RepairApplicationError(
                    "REPAIR_ATTEMPT_NOT_FOUND", "Repair attempt is missing"
                )
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == attempt.run_id,
                )
            )
            existing = self._revision_event(session, continuation, idempotency_key, reject=True)
            if existing is not None:
                if (existing.payload or {}).get("request_checksum") != request_checksum:
                    raise RepairApplicationError(
                        "IDEMPOTENCY_PAYLOAD_MISMATCH", "Rejection key has a different payload"
                    )
                return {
                    "attempt_id": attempt_id,
                    "status": "rejected",
                    "idempotent_replay": True,
                }
            latest = session.scalar(
                select(RepairAttemptModel)
                .where(
                    RepairAttemptModel.run_id == attempt.run_id,
                    RepairAttemptModel.stage_id == attempt.stage_id,
                )
                .order_by(RepairAttemptModel.attempt_number.desc())
                .limit(1)
            )
            if continuation is None or latest is None:
                raise RepairApplicationError(
                    "REPAIR_AUTHORITY_MISSING", "Repair rejection authority is missing"
                )
            if latest.id != attempt.id:
                raise RepairApplicationError(
                    "REPAIR_ATTEMPT_SUPERSEDED",
                    "Superseded repair attempts cannot be rejected",
                )
            if (
                attempt.status != "request_changes"
                or attempt.proposal_artifact_id != proposal_id
                or attempt.proposal_checksum != base_checksum
                or continuation.current_stage_id != attempt.stage_id
                or continuation.status != "waiting_repair_revision"
                or continuation.current_node != "review_repair"
            ):
                raise RepairApplicationError(
                    "REPAIR_REJECTION_NOT_ALLOWED",
                    "Repair attempt is not waiting for rejection",
                )
            expected_state_version = continuation.state_version
            attempt.status = "rejected"
            attempt.updated_at = self._now()
            continuation.status = "blocked"
            continuation.last_error_code = "REPAIR_HUMAN_REJECTED"
            continuation.last_error_message = "Repair candidate rejected by the operator"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.state_version += 1
            continuation.updated_at = self._now()
            append_continuation_event(
                session,
                continuation,
                event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_BLOCKED,
                key=self._revision_event_key(idempotency_key, reject=True),
                reason=continuation.last_error_message,
                actor=actor,
                payload={
                    "attempt_id": attempt.id,
                    "request_checksum": request_checksum,
                    "expected_state_version": expected_state_version,
                },
            )
            return {
                "attempt_id": attempt.id,
                "status": attempt.status,
                "idempotent_replay": False,
            }

    @staticmethod
    def _json_object_without_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON object key")
            value[key] = item
        return value

    def _normalize_dependency_operation(self, operation: dict[str, object], target: Path):
        fields = [operation.get(name) for name in ("section", "package", "new_version")]
        if not any(field is not None for field in fields):
            return operation
        if not all(isinstance(field, str) and field.strip() for field in fields):
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_INTENT_INVALID",
                "Dependency changes require section, package, and new_version",
            )
        section, package, new_version = (str(field) for field in fields)
        if section not in _DEPENDENCY_SECTIONS:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_SECTION_INVALID",
                "Dependency changes must target a supported package section",
            )
        try:
            with target.open("r", encoding="utf-8", newline="") as handle:
                raw = handle.read()
            document = json.loads(raw, object_pairs_hook=self._json_object_without_duplicates)
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_PACKAGE_INVALID", "Authoritative package.json is invalid"
            ) from error
        if not isinstance(document, dict):
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_PACKAGE_INVALID", "Authoritative package.json must be an object"
            )
        matches = [
            (name, document[name][package])
            for name in _DEPENDENCY_SECTIONS
            if isinstance(document.get(name), dict) and package in document[name]
        ]
        if not matches:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_PACKAGE_MISSING",
                "The requested package is missing from authoritative package.json",
            )
        if len(matches) != 1 or matches[0][0] != section:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_PACKAGE_AMBIGUOUS",
                "The requested package has ambiguous dependency entries",
            )
        if not isinstance(matches[0][1], str):
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_VERSION_INVALID",
                "The authoritative dependency value is not a version string",
            )
        document[section][package] = new_version
        newline = _dominant_newline(raw)
        canonical = json.dumps(document, ensure_ascii=False, indent=2).replace("\n", newline)
        if raw.endswith(("\n", "\r")):
            canonical += newline
        operation["old_text"] = raw
        operation["new_text"] = canonical
        return operation

    def _coalesce_operations(
        self,
        operations: list[dict[str, object]],
        workspace: Path,
        *,
        context: dict[str, object] | None = None,
        bind_preimages: bool = False,
    ) -> list[dict[str, object]]:
        """Bind logical edits to one deterministic mutation per physical path."""
        groups: dict[str, list[dict[str, object]]] = {}
        result: list[dict[str, object]] = []
        for item in operations:
            bound = dict(item)
            relative = self._safe_path(str(item.get("path") or ""), workspace)
            bound["path"] = relative
            if str(item.get("operation")) == "dependency_transition":
                if relative != "package.json":
                    raise RepairApplicationError(
                        "REPAIR_DEPENDENCY_PATH_INVALID",
                        "Dependency transitions may target only package.json",
                    )
                bound["preimage_sha256"] = None
                result.append(bound)
                continue
            groups.setdefault(relative, []).append(bound)

        for relative, group in groups.items():
            target = workspace / relative
            current_path = workspace
            for part in PurePosixPath(relative).parts:
                current_path = current_path / part
                if current_path.is_symlink():
                    raise RepairApplicationError(
                        "REPAIR_SYMLINK_FORBIDDEN",
                        "Repair targets may not traverse symlinks",
                    )
            actions = {str(item.get("operation")) for item in group}
            if not actions <= {"replace_text", "create_text_file", "delete_text_file", "dependency_change"}:
                raise RepairApplicationError(
                    "REPAIR_OPERATION_INVALID", "Repair operation is unsupported"
                )
            if "create_text_file" in actions:
                if len(group) != 1 or target.exists() or group[0].get("content") is None:
                    raise RepairApplicationError(
                        "REPAIR_OPERATION_AMBIGUOUS",
                        "Create operations cannot share a physical path",
                    )
                group[0]["preimage_sha256"] = None
                result.append(group[0])
                continue

            if target.is_symlink() or not target.is_file():
                raise RepairApplicationError(
                    "REPAIR_PREIMAGE_INVALID",
                    "Repair target must be a regular existing file",
                )
            try:
                with target.open("r", encoding="utf-8", newline="") as handle:
                    current = handle.read()
            except UnicodeDecodeError as error:
                raise RepairApplicationError(
                    "REPAIR_BINARY_FORBIDDEN", "Repair target is not UTF-8 text"
                ) from error
            actual = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
            for item in group:
                if bind_preimages:
                    item["preimage_sha256"] = actual
                elif item.get("preimage_sha256") != actual:
                    raise RepairApplicationError(
                        "REPAIR_PREIMAGE_STALE",
                        "Repair target preimage checksum changed",
                    )

            if relative == "package.json" or "dependency_change" in actions:
                if relative != "package.json":
                    raise RepairApplicationError(
                        "REPAIR_DEPENDENCY_PATH_INVALID",
                        "Dependency changes may edit only package.json",
                    )
                if actions != {"dependency_change"}:
                    raise RepairApplicationError(
                        "REPAIR_OPERATION_AMBIGUOUS",
                        "package.json cannot combine dependency and file operations",
                    )
                if context is not None:
                    self._require_lockfile_generation_authority(context)
                try:
                    document = json.loads(
                        current, object_pairs_hook=self._json_object_without_duplicates
                    )
                except ValueError as error:
                    raise RepairApplicationError(
                        "REPAIR_DEPENDENCY_PACKAGE_INVALID",
                        "Authoritative package.json is invalid",
                    ) from error
                if not isinstance(document, dict):
                    raise RepairApplicationError(
                        "REPAIR_DEPENDENCY_PACKAGE_INVALID",
                        "Authoritative package.json must be an object",
                    )
                if len(group) == 1 and not any(
                    group[0].get(name) is not None
                    for name in ("section", "package", "new_version")
                ):
                    after = replace_text_once(
                        current,
                        str(group[0].get("old_text")),
                        str(group[0].get("new_text")),
                    )
                    result.append(
                        {
                            "operation": "dependency_change",
                            "path": relative,
                            "preimage_sha256": actual,
                            "old_text": current,
                            "new_text": after,
                            "section": None,
                            "package": None,
                            "new_version": None,
                            "provenance": list(group[0].get("provenance") or []),
                        }
                    )
                    continue
                seen: dict[tuple[str, str], str] = {}
                provenance: list[dict[str, str]] = []
                for item in group:
                    fields = [item.get(name) for name in ("section", "package", "new_version")]
                    if not all(isinstance(field, str) and field.strip() for field in fields):
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_INTENT_INVALID",
                            "Dependency changes require section, package, and new_version",
                        )
                    section, package, new_version = (str(field) for field in fields)
                    if section not in _DEPENDENCY_SECTIONS:
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_SECTION_INVALID",
                            "Dependency changes must target a supported package section",
                        )
                    key = (section, package)
                    prior = seen.get(key)
                    if prior is not None and prior != new_version:
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_CONFLICT",
                            "Contradictory dependency changes target the same package key",
                        )
                    seen[key] = new_version
                    matches = [
                        (name, document[name][package])
                        for name in _DEPENDENCY_SECTIONS
                        if isinstance(document.get(name), dict) and package in document[name]
                    ]
                    if not matches:
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_PACKAGE_MISSING",
                            "The requested package is missing from authoritative package.json",
                        )
                    if len(matches) != 1 or matches[0][0] != section:
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_PACKAGE_AMBIGUOUS",
                            "The requested package has ambiguous dependency entries",
                        )
                    if not isinstance(matches[0][1], str):
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_VERSION_INVALID",
                            "The authoritative dependency value is not a version string",
                        )
                    document[section][package] = new_version
                    provenance.append(
                        {
                            "operation": "dependency_change",
                            "path": relative,
                            "section": section,
                            "package": package,
                            "new_version": new_version,
                        }
                    )
                newline = _dominant_newline(current)
                canonical = json.dumps(document, ensure_ascii=False, indent=2).replace(
                    "\n", newline
                )
                if current.endswith(("\n", "\r")):
                    canonical += newline
                if canonical == current:
                    raise RepairApplicationError(
                        "REPAIR_REPLACEMENT_NOOP",
                        "Dependency changes produced no file change",
                    )
                first = group[0]
                result.append(
                    {
                        "operation": "dependency_change",
                        "path": relative,
                        "preimage_sha256": actual,
                        "old_text": current,
                        "new_text": canonical,
                        "section": first.get("section") if len(group) == 1 else None,
                        "package": first.get("package") if len(group) == 1 else None,
                        "new_version": first.get("new_version") if len(group) == 1 else None,
                        "provenance": provenance,
                    }
                )
                continue

            if "delete_text_file" in actions:
                if len(group) != 1:
                    raise RepairApplicationError(
                        "REPAIR_OPERATION_AMBIGUOUS",
                        "Delete operations cannot share a physical path",
                    )
                result.append(
                    {
                        "operation": "delete_text_file",
                        "path": relative,
                        "content": "",
                        "preimage_sha256": actual,
                        "provenance": [],
                    }
                )
                continue

            if actions != {"replace_text"}:
                raise RepairApplicationError(
                    "REPAIR_OPERATION_AMBIGUOUS",
                    "Different file operations cannot share a physical path",
                )
            after = current
            provenance = []
            for item in group:
                try:
                    after = replace_text_once(
                        after, str(item.get("old_text")), str(item.get("new_text"))
                    )
                except RepairApplicationError:
                    raise
                provenance.append(
                    {
                        "operation": "replace_text",
                        "path": relative,
                        "old_text": str(item.get("old_text")),
                        "new_text": str(item.get("new_text")),
                    }
                )
            result.append(
                {
                    "operation": "replace_text",
                    "path": relative,
                    "preimage_sha256": actual,
                    "old_text": current,
                    "new_text": after,
                    "provenance": provenance,
                }
            )
        for operation in result:
            operation['provenance'] = _normalize_provenance(operation.get('provenance'))
        return result

    def _bind_dependency_transition(
        self, value: dict[str, object], context: dict[str, object]
    ) -> dict[str, object]:
        """Validate and normalize the single structured dependency_transition operation."""
        operations = list(value.get("operations") or [])
        transitions = [
            item for item in operations if item.get("operation") == "dependency_transition"
        ]
        if len(operations) != 1 or len(transitions) != 1:
            raise RepairApplicationError(
                "REPAIR_OPERATION_AMBIGUOUS",
                "dependency_transition requires exactly one operation and no other mutations",
            )
        operation = dict(transitions[0])
        expected_fields = {
            "schema_version": "transformer-repair-v2",
            "repair_kind": "dependency_transition",
            "failure_type": "peer_dependency_conflict",
            "strategy": "detach_update_reattach",
        }
        for field, expected in expected_fields.items():
            supplied = operation.get(field)
            if supplied is not None and supplied != expected:
                raise RepairApplicationError(
                    "REPAIR_DEPENDENCY_INTENT_INVALID",
                    f"dependency_transition {field} conflicts with backend authority",
                )
            operation[field] = expected
        try:
            blocking_value = operation.get("blocking_dependency")
            blocking = (
                BlockingDependencyCandidateInput.model_validate(blocking_value)
                if blocking_value is not None
                else None
            )
            target_value = operation.get("target_state")
            target_state = (
                TargetStateCandidateInput.model_validate(target_value)
                if target_value is not None
                else None
            )
        except ValidationError as error:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_INTENT_INVALID",
                "dependency_transition intent fields are incomplete",
            ) from error
        checkpoint_id = context.get("checkpoint_id")
        if not isinstance(checkpoint_id, str) or not checkpoint_id:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_AUTHORITY_MISSING",
                "Repair attempt checkpoint authority is missing",
            )
        if operation.get("checkpoint_id") is not None and operation["checkpoint_id"] != checkpoint_id:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_INTENT_INVALID",
                "dependency_transition checkpoint_id conflicts with backend authority",
            )
        expected_major = _version_major(context.get("target_exact"))
        target_exact = context.get("target_exact")
        if expected_major is None or not is_exact_version(target_exact):
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_AUTHORITY_MISSING",
                "Stage plan target exact version authority is missing",
            )
        workspace = Path(str(context["workspace_path"])).resolve(strict=True)
        segments = context.get("segments")
        try:
            evidence = json.loads(str(segments[0]))
        except (IndexError, TypeError, ValueError) as error:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_EVIDENCE_MISSING",
                "Backend dependency conflict evidence is missing",
            ) from error
        try:
            normalized = evidence.get("normalized_failure")
            diagnosis = normalized.get("failure_diagnosis") if isinstance(normalized, dict) else None
            if (
                isinstance(normalized, dict)
                and (
                    not isinstance(diagnosis, dict)
                    or not isinstance(diagnosis.get("package"), str)
                    or not diagnosis.get("required_ranges")
                )
            ):
                reparsed = FailureEvidenceService.diagnose_angular_update_failure(normalized)
                if reparsed is not None:
                    normalized = {**normalized, "failure_diagnosis": reparsed}
                    evidence = {**evidence, "normalized_failure": normalized}
                    diagnosis = reparsed
            backend_package = diagnosis.get("package") if isinstance(diagnosis, dict) else None
            if not isinstance(backend_package, str) or not backend_package:
                raise ValueError(
                    "field=normalized_failure.failure_diagnosis.package; "
                    "expected=non-empty blocking package parsed from the failed Angular command; "
                    f"observed={json.dumps(backend_package)}; "
                    f"artifact_id={context.get('failure_evidence_artifact_id') or 'unavailable'}; "
                    f"execution_id={evidence.get('execution_id') or 'unavailable'}; "
                    "recovery=reparse the immutable command failure with the npm package-name grammar"
                )
            installed_version = installed_dependency_version(workspace, backend_package)
            authority = validate_dependency_transition_evidence(
                evidence,
                package=backend_package,
                target_major=expected_major,
                installed_version=installed_version,
                artifact_id=str(context.get("failure_evidence_artifact_id") or ""),
            )
            if blocking is not None:
                if blocking.package is not None and blocking.package != authority["package"]:
                    raise RepairApplicationError(
                        "REPAIR_DEPENDENCY_INTENT_INVALID",
                        "proposal blocking package conflicts with backend evidence",
                    )
                if blocking.installed_version is not None:
                    if not is_exact_version(blocking.installed_version):
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_INTENT_INVALID",
                            "proposal installed package version must be exact",
                        )
                    if blocking.installed_version != authority["installed_version"]:
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_INTENT_INVALID",
                            "proposal installed package version conflicts with backend authority",
                        )
                if blocking.required_peer_ranges is not None:
                    proposed_ranges = {
                        item.package: item.version_range
                        for item in blocking.required_peer_ranges
                        if item.package is not None or item.version_range is not None
                    }
                    if any(item.package is None or item.version_range is None for item in blocking.required_peer_ranges):
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_INTENT_INVALID",
                            "proposal peer range fields are incomplete",
                        )
                    if proposed_ranges != authority["peer_ranges"]:
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_INTENT_INVALID",
                            "proposal peer ranges conflict with backend evidence",
                        )
            if target_state is not None:
                if target_state.package is not None and target_state.package != authority["package"]:
                    raise RepairApplicationError(
                        "REPAIR_DEPENDENCY_INTENT_INVALID",
                        "proposal target package conflicts with backend evidence",
                    )
                if target_state.target_version is not None:
                    if not is_exact_version(target_state.target_version):
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_INTENT_INVALID",
                            "proposal target version must be exact",
                        )
                    if target_state.target_version != authority["target_version"]:
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_INTENT_INVALID",
                            "proposal target version conflicts with backend authority",
                        )
                if target_state.angular_major is not None and target_state.angular_major != expected_major:
                    raise RepairApplicationError(
                        "REPAIR_DEPENDENCY_INTENT_INVALID",
                        "proposal Angular major conflicts with backend authority",
                    )
            verify_dependency_transition_state(
                workspace,
                package=str(authority["package"]),
                installed_version=str(authority["installed_version"]),
                peer_ranges=dict(authority["peer_ranges"]),
            )
        except RepairApplicationError:
            raise
        except ValueError as error:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_EVIDENCE_INVALID",
                str(error),
            ) from error
        operation["blocking_dependency"] = BlockingDependencyCandidate(
            package=authority["package"],
            installed_version=authority["installed_version"],
            required_peer_ranges=[
                RequiredPeerRange(package=peer_package, version_range=version_range)
                for peer_package, version_range in authority["peer_ranges"].items()
            ],
        ).model_dump(mode="json")
        operation["target_state"] = TargetStateCandidate(
            package=authority["package"],
            target_version=str(authority["target_version"]),
            angular_major=expected_major,
        ).model_dump(mode="json")
        operation["checkpoint_id"] = checkpoint_id
        value["operations"] = [operation]
        package = str(authority["package"])
        try:
            with (workspace / "package.json").open("r", encoding="utf-8", newline="") as handle:
                document = json.loads(
                    handle.read(), object_pairs_hook=self._json_object_without_duplicates
                )
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_PACKAGE_INVALID", "Authoritative package.json is invalid"
            ) from error
        if not isinstance(document, dict):
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_PACKAGE_INVALID", "Authoritative package.json must be an object"
            )
        present = [
            section
            for section in _DEPENDENCY_TRANSITION_TARGET_SECTIONS
            if isinstance(document.get(section), dict) and package in document[section]
        ]
        if len(present) != 1:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_PACKAGE_MISSING",
                "The backend blocking package is missing or ambiguous in authoritative package.json",
            )
        return RepairProposal.model_validate(value).model_dump(mode="json")

    def _causal_gate_rejection(self, context: dict[str, object], proposal: dict[str, object]):
        """Run the causal gate over the failure evidence and the bound proposal."""
        evidence_dict = None
        segments = context.get("segments")
        if segments and isinstance(segments[0], str):
            try:
                parsed = json.loads(segments[0])
                if isinstance(parsed, dict):
                    evidence_dict = parsed
            except (TypeError, ValueError):
                evidence_dict = None
        if evidence_dict is None:
            evidence_dict = {
                key: context.get(key)
                for key in ("run_id", "stage_id", "attempt_id")
                if context.get(key) is not None
            }
            evidence_dict = evidence_dict or None
        return causal_rejection(
            evidence_dict,
            proposal,
            stage_plan_commands=context.get("stage_plan_commands"),
        )

    def _bind_proposal_candidate(self, value: dict[str, object], context: dict[str, object]):
        candidate = RepairProposalCandidate.model_validate(value)
        for index, operation in enumerate(candidate.operations):
            if not operation.path or len(operation.path) > 500:
                raise RepairApplicationError(
                    "REPAIR_PATH_INVALID",
                    f"operations.{index}.path must contain 1 to 500 characters",
                )
        if candidate.proposal_format == "operations":
            if not candidate.operations or candidate.unified_diff is not None:
                raise RepairApplicationError(
                    "REPAIR_PROPOSAL_FORMAT_INVALID", "Operations format must contain only operations"
                )
        elif candidate.operations or not candidate.unified_diff:
            raise RepairApplicationError(
                "REPAIR_PROPOSAL_FORMAT_INVALID", "Unified diff format must contain only a diff"
            )
        workspace = Path(str(context["workspace_path"])).resolve(strict=True)
        operations = self._coalesce_operations(
            [operation.model_dump(mode="json") for operation in candidate.operations],
            workspace,
            context=context,
            bind_preimages=True,
        )
        payload = {
            **candidate.model_dump(mode="json"),
            "failure_evidence_checksum": context["failure_evidence_checksum"],
            "context_pack_checksum": context["context_pack_checksum"],
            "operations": operations,
            "touched_files": (
                [operation["path"] for operation in operations]
                if operations
                else self._unified_diff_touched_files(candidate.unified_diff, workspace)
            ),
            "validation_targets": self._normalize_validation_targets(
                candidate.validation_targets
            ),
        }
        if any(item.get("operation") == "dependency_transition" for item in operations):
            return self._bind_dependency_transition(payload, context)
        return RepairProposal.model_validate(payload).model_dump(mode="json")

    def _unified_diff_touched_files(self, diff: str | None, workspace: Path) -> list[str]:
        lines = (diff or "").splitlines()
        paths = []
        index = 0
        while index < len(lines):
            if not lines[index].startswith("--- "):
                if lines[index].startswith("+++ "):
                    raise RepairApplicationError(
                        "REPAIR_DIFF_INVALID", "Unified diff header pair is incomplete"
                    )
                index += 1
                continue
            if index + 1 >= len(lines) or not lines[index + 1].startswith("+++ "):
                raise RepairApplicationError(
                    "REPAIR_DIFF_INVALID", "Unified diff header pair is incomplete"
                )
            old_path = _unified_diff_header_path(lines[index], "a/")
            new_path = _unified_diff_header_path(lines[index + 1], "b/")
            old_path = None if old_path == "/dev/null" else self._safe_path(old_path, workspace)
            new_path = None if new_path == "/dev/null" else self._safe_path(new_path, workspace)
            if old_path is None and new_path is None:
                raise RepairApplicationError(
                    "REPAIR_DIFF_INVALID", "Unified diff header pair has no file path"
                )
            paths.append(new_path or old_path)
            if (new_path or old_path) == "package.json":
                raise RepairApplicationError(
                    "REPAIR_DEPENDENCY_OPERATION_REQUIRED",
                    "package.json changes require the controlled dependency operation",
                )
            index += 2
            while index < len(lines):
                if lines[index].startswith("diff --git "):
                    break
                hunk = _UNIFIED_HUNK.match(lines[index])
                if hunk:
                    old_remaining = int(hunk.group(2) or 1)
                    new_remaining = int(hunk.group(4) or 1)
                    index += 1
                    while index < len(lines) and (old_remaining or new_remaining):
                        line = lines[index]
                        if not line.startswith("\\"):
                            if line.startswith((" ", "-")):
                                old_remaining -= 1
                            if line.startswith((" ", "+")):
                                new_remaining -= 1
                        index += 1
                    if old_remaining or new_remaining:
                        raise RepairApplicationError(
                            "REPAIR_DIFF_INVALID", "Unified diff hunk is incomplete"
                        )
                    continue
                if lines[index].startswith("--- "):
                    if index + 1 < len(lines) and lines[index + 1].startswith("+++ "):
                        break
                    raise RepairApplicationError(
                        "REPAIR_DIFF_INVALID", "Unified diff header pair is incomplete"
                    )
                if lines[index].startswith("+++ "):
                    raise RepairApplicationError(
                        "REPAIR_DIFF_INVALID", "Unified diff header pair is incomplete"
                    )
                index += 1
        if not paths:
            raise RepairApplicationError(
                "REPAIR_TOUCHED_FILES_MISSING", "Unified diff must identify touched files"
            )
        return paths

    @staticmethod
    def _prompt_version(schema_name: str, task_type: LlmTaskType) -> str:
        return PromptRegistry.defaults().get(schema_name, task_type).version

    @staticmethod
    def _logical_request_checksum(
        segments: list[str], schema_name: str, prompt_version: str, schema_version: str
    ) -> str:
        payload = {
            "segments": segments,
            "schema_name": schema_name,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
        }
        return "sha256:" + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _bind_review_candidate(self, value: dict[str, object], context: dict[str, object]):
        candidate = RepairReviewCandidate.model_validate(value)
        try:
            proposal = json.loads(str(context["segments"][2]))
            evidence = json.loads(str(context["segments"][0]))
        except (TypeError, ValueError, KeyError, IndexError):
            proposal = None
            evidence = None
        if (
            candidate.decision == "accept"
            and isinstance(proposal, dict)
            and isinstance(evidence, dict)
        ):
            rejection = causal_rejection(
                evidence,
                proposal,
                stage_plan_commands=context.get("stage_plan_commands"),
            )
            if rejection is not None:
                raise RepairApplicationError("REPAIR_REVIEW_CAUSAL_INVALID", rejection.reason)
        return RepairReview(
            **candidate.model_dump(
                mode="json",
                exclude={"required_validation_targets"},
            ),
            required_validation_targets=self._normalize_validation_targets(
                candidate.required_validation_targets
            ),
            proposal_checksum=context["proposal_checksum"],
        ).model_dump(mode="json")

    def _normalize_validation_targets(self, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip().lower() for value in values))
        rejected = [
            _bounded_text(value, 64)
            for value in normalized
            if value not in self.supported_validation_targets
        ][:16]
        if rejected:
            logger.warning(
                "repair validation targets rejected",
                extra={"rejected_validation_targets": rejected},
            )
            raise RepairApplicationError(
                "REPAIR_VALIDATION_TARGET_INVALID",
                "Repair validation targets must use backend-supported names; "
                f"rejected_targets={','.join(rejected)}",
            )
        return normalized

    def validate_proposal(
        self, value: dict[str, object], context: dict[str, object]
    ) -> dict[str, object]:
        proposal = RepairProposal.model_validate(value)
        if (
            proposal.failure_evidence_checksum != context["failure_evidence_checksum"]
            or proposal.context_pack_checksum != context["context_pack_checksum"]
        ):
            raise RepairApplicationError("REPAIR_PROPOSAL_STALE", "Proposal evidence binding is stale")
        if proposal.proposal_format == "operations":
            if not proposal.operations or proposal.unified_diff is not None:
                raise RepairApplicationError(
                    "REPAIR_PROPOSAL_FORMAT_INVALID", "Operations format must contain only operations"
                )
        elif proposal.operations or not proposal.unified_diff:
            raise RepairApplicationError(
                "REPAIR_PROPOSAL_FORMAT_INVALID", "Unified diff format must contain only a diff"
            )
        workspace = Path(str(context["workspace_path"])).resolve(strict=True)
        normalized = [self._safe_path(item, workspace) for item in proposal.touched_files]
        if proposal.operations:
            operation_paths = [self._safe_path(item.path, workspace) for item in proposal.operations]
            if len(normalized) != len(set(normalized)) and len(operation_paths) == len(set(operation_paths)):
                raise RepairApplicationError(
                    "REPAIR_PATH_DUPLICATE", "Touched file paths must be unique"
                )
            operations = self._coalesce_operations(
                [item.model_dump(mode="json") for item in proposal.operations],
                workspace,
                context=context,
            )
            expected_paths = [str(item["path"]) for item in operations]
            normalized = list(dict.fromkeys(normalized))
            if normalized != expected_paths:
                raise RepairApplicationError(
                    "REPAIR_TOUCHED_FILES_MISMATCH", "Operation paths do not match touched_files"
                )
        else:
            if len(normalized) != len(set(normalized)):
                raise RepairApplicationError("REPAIR_PATH_DUPLICATE", "Touched file paths must be unique")
            operations = []
        if proposal.proposal_format == "operations" and proposal.operations:
            bound = proposal.model_dump(mode="json")
            bound["operations"] = operations
            bound["touched_files"] = expected_paths
            if any(item.get("operation") == "dependency_transition" for item in operations):
                bound = self._bind_dependency_transition(bound, context)
            rendered = self._render_safe_diff(bound, workspace)
            if not rendered:
                raise RepairApplicationError(
                    "REPAIR_EMPTY_DIFF",
                    "Proposed operations claim changes but render an empty diff",
                )
            result = bound
        else:
            result = proposal.model_dump(mode="json")
        rejection = self._causal_gate_rejection(context, result)
        if rejection is not None:
            raise RepairApplicationError("REPAIR_CAUSAL_REJECTION", rejection.reason)
        return result

    @staticmethod
    def _require_lockfile_generation_authority(context: dict[str, object]) -> None:
        commands = context.get("stage_plan_commands")
        references = commands.get("lockfile_generation") if isinstance(commands, dict) else None
        try:
            reference = CommandTemplateReference.model_validate(references[0])
        except (IndexError, KeyError, TypeError, ValidationError):
            reference = None
        definition = TRANSFORMATION_COMMAND_CATALOGUE["npm-lockfile-generate"]
        if (
            not isinstance(references, (list, tuple))
            or len(references) != 1
            or reference is None
            or reference.command_id != definition.command_id
            or reference.template_id != definition.template_id
            or reference.template_version != 1
            or reference.parameter_bindings
            or reference.executable != definition.executable
            or reference.arguments != definition.arguments
            or reference.shell is not False
            or reference.working_directory_alias != context.get("workspace_binding_alias")
            or reference.timeout_seconds != definition.timeout_seconds
            or reference.network_profile != definition.network_profile
            or reference.runtime_profile_checksum is None
            or reference.cancellation_policy != "terminate_process_tree"
            or reference.conditional is not False
        ):
            raise RepairApplicationError(
                "STAGE_PLAN_COMMAND_AUTHORITY_MISSING",
                "The accepted stage plan lacks exact npm-lockfile-generate authority",
            )

    def _attempt_context(
        self,
        attempt_id: str,
        *,
        include_proposal: bool = False,
        include_review: bool = False,
        validate_context_pack: bool = True,
    ):
        with self._scope() as session:
            attempt = session.scalar(select(RepairAttemptModel).where(RepairAttemptModel.id == attempt_id))
            if attempt is None:
                raise RepairApplicationError("REPAIR_ATTEMPT_NOT_FOUND", "Repair attempt is missing")
            run = session.scalar(select(MigrationRunModel).where(MigrationRunModel.id == attempt.run_id))
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == attempt.run_id,
                    StageWorkspaceBindingModel.stage_id == attempt.stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if run is None or binding is None:
                raise RepairApplicationError("REPAIR_AUTHORITY_MISSING", "Repair authority is missing")
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == attempt.run_id,
                    TransformationContinuationModel.current_stage_id == attempt.stage_id,
                )
            )
            if continuation is None or not continuation.stage_plan_id or not continuation.stage_plan_checksum:
                raise RepairApplicationError("REPAIR_AUTHORITY_MISSING", "Repair continuation or stage plan is missing")
            stage_plan = session.scalar(
                select(StageExecutionPlanModel).where(
                    StageExecutionPlanModel.id == continuation.stage_plan_id,
                    StageExecutionPlanModel.run_id == attempt.run_id,
                    StageExecutionPlanModel.stage_id == attempt.stage_id,
                    StageExecutionPlanModel.checksum == continuation.stage_plan_checksum,
                )
            )
            if stage_plan is None:
                raise RepairApplicationError("REPAIR_AUTHORITY_MISSING", "Repair stage plan is missing")
            stage_value = stage_plan.stage_plan or {}
            angular_references = (stage_value.get("commands") or {}).get("angular_update") or []
            angular_reference = angular_references[0] if len(angular_references) == 1 else {}
            angular_bindings = angular_reference.get("parameter_bindings") or {}
            context = {
                "attempt_id": attempt.id,
                "run_id": attempt.run_id,
                "stage_id": attempt.stage_id,
                "artifact_root": run.artifact_root,
                "run_root": run.run_root,
                "workspace_path": binding.workspace_path,
                "failure_evidence_checksum": attempt.failure_evidence_checksum,
                "failure_fingerprint": attempt.failure_fingerprint,
                "pre_fingerprint": attempt.pre_fingerprint,
                "context_pack_checksum": attempt.context_pack_checksum,
                "context_pack_artifact_id": attempt.context_pack_artifact_id,
                "proposal_checksum": attempt.proposal_checksum,
                "proposal_artifact_id": attempt.proposal_artifact_id,
                "review_checksum": attempt.review_checksum,
                "review_artifact_id": attempt.review_artifact_id,
                "proposer_invocation_id": attempt.proposer_invocation_id,
                "reviewer_invocation_id": attempt.reviewer_invocation_id,
                "failure_evidence_artifact_id": attempt.failure_evidence_artifact_id,
                "attempt_number": attempt.attempt_number,
                "attempt_status": attempt.status,
                "attempt_state_version": attempt.state_version,
                "parent_attempt_id": attempt.parent_attempt_id,
                "parent_review_artifact_id": attempt.parent_review_artifact_id,
                "parent_review_checksum": attempt.parent_review_checksum,
                "run_state_version": run.state_version,
                "continuation_state_version": continuation.state_version if continuation else None,
                "stage_plan_id": stage_plan.id if stage_plan else (continuation.stage_plan_id if continuation else None),
                "stage_plan_checksum": stage_plan.checksum if stage_plan else (continuation.stage_plan_checksum if continuation else None),
                "stage_plan_state_version": stage_plan.state_version if stage_plan else None,
                "stage_plan_commands": dict((stage_plan.stage_plan or {}).get("commands") or {}),
                "target_exact": angular_bindings.get("target_exact") or stage_value.get("target_exact"),
                "target_cli_exact": angular_bindings.get("target_cli_exact") or stage_value.get("target_cli_exact"),
                "workspace_binding_id": binding.id,
                "workspace_binding_alias": binding.alias,
                "workspace_stored_fingerprint": binding.workspace_fingerprint,
                "checkpoint_id": attempt.checkpoint_id,
            }
            if not attempt.failure_evidence_artifact_id or not attempt.failure_evidence_checksum:
                raise RepairApplicationError("REPAIR_EVIDENCE_MISSING", "Failure evidence artifact is missing")
            if not attempt.context_pack_artifact_id or not attempt.context_pack_checksum:
                raise RepairApplicationError("REPAIR_CONTEXT_MISSING", "Repair context artifact is missing")
            artifact_ids = [attempt.failure_evidence_artifact_id, attempt.context_pack_artifact_id]
            if include_proposal:
                if not attempt.proposal_artifact_id or not attempt.proposal_checksum:
                    raise RepairApplicationError("REPAIR_PROPOSAL_MISSING", "Repair proposal is missing")
                artifact_ids.append(attempt.proposal_artifact_id)
            if include_review:
                if not attempt.review_artifact_id or not attempt.review_checksum:
                    raise RepairApplicationError("REPAIR_REVIEW_MISSING", "Repair review is missing")
                artifact_ids.append(attempt.review_artifact_id)
            metadata = {
                item.id.removeprefix("metadata-"): item
                for item in session.query(ArtifactMetadataModel)
                .filter(
                    ArtifactMetadataModel.run_id == attempt.run_id,
                    ArtifactMetadataModel.id.in_([f"metadata-{item}" for item in artifact_ids]),
                )
                .all()
            }
            if any(artifact_id not in metadata for artifact_id in artifact_ids):
                raise RepairApplicationError("REPAIR_EVIDENCE_MISSING", "Repair artifact metadata is missing")
            expected_checksums = {
                attempt.failure_evidence_artifact_id: attempt.failure_evidence_checksum,
                attempt.context_pack_artifact_id: attempt.context_pack_checksum,
            }
            if include_proposal:
                expected_checksums[attempt.proposal_artifact_id] = attempt.proposal_checksum
            if include_review:
                expected_checksums[attempt.review_artifact_id] = attempt.review_checksum
            for artifact_id, expected in expected_checksums.items():

                if metadata[artifact_id].checksum != expected:
                    raise RepairApplicationError("REPAIR_ARTIFACT_RECOVERY_FAILED", "Repair artifact checksum binding is stale")
        root = Path(str(context["artifact_root"]))
        store = LocalFilesystemArtifactStore(root.parent, fixed_run_root=root)
        artifacts = [store.read_artifact(str(context["run_id"]), metadata[artifact_id].relative_path) for artifact_id in artifact_ids]
        for artifact in artifacts:
            pre_attempt = artifact.ref.artifact_id not in {
                context.get("proposal_artifact_id"),
                context.get("review_artifact_id"),
            }
            self._validate_artifact_envelope(
                artifact,
                expected_run_id=context["run_id"],
                expected_stage_id=context["stage_id"],
                expected_attempt_id=context["attempt_id"],
                pre_attempt=pre_attempt,
                metadata_checksum=metadata[artifact.ref.artifact_id].checksum,
            )
            if artifact.ref.artifact_id == context["context_pack_artifact_id"] and validate_context_pack:
                self._validate_context_pack(artifact.content)
        workspace = Path(str(context["workspace_path"]))
        try:
            context["workspace_live_fingerprint"] = StageSandboxCopier.fingerprint(workspace)
        except OSError as error:
            raise RepairApplicationError("REPAIR_WORKSPACE_MISSING", "Repair workspace is unavailable") from error
        if context["workspace_live_fingerprint"] != context["workspace_stored_fingerprint"]:
            raise RepairApplicationError("REPAIR_WORKSPACE_STALE", "Repair workspace fingerprint changed")
        context["segments"] = [artifact.content for artifact in artifacts]
        if include_proposal:
            proposal_artifact = next(
                artifact
                for artifact in artifacts
                if artifact.ref.artifact_id == context["proposal_artifact_id"]
            )
            context["proposal_checksum"] = proposal_artifact.ref.checksum
            context["proposal_artifact_id"] = proposal_artifact.ref.artifact_id
            context["authority_snapshot"] = self._authority_snapshot(context)
        context["authority_snapshot"] = self._authority_snapshot(context)
        return context

    def recover_legacy_fingerprint_authority(self, attempt_id: str) -> dict[str, object]:
        """Recover a legacy (pre-profile-identity) workspace fingerprint authority.

        A stage workspace binding persisted before fingerprint-profile identity
        existed is "legacy": its stored ``workspace_fingerprint`` was computed
        by a legacy scope and cannot be compared against the live workspace
        under the current canonical profile, so the repair runtime would
        incorrectly block with REPAIR_WORKSPACE_STALE.

        Recovery succeeds ONLY when both of the following hold:

          * check 1 — the stored legacy hash matches the attempt's historical
            pre-repair checkpoint under the deterministically identified
            legacy profile (``SUPPORTED_LEGACY_FINGERPRINT_PROFILES``);
          * check 2 — the live workspace and that checkpoint match under the
            current canonical profile.

        On success the binding is migrated to the current fingerprint and
        profile identity, the attempt is CAS-bound to the checkpoint, and one
        explicit legacy -> current lineage row is persisted — all in a single
        transaction.  The binding's own stored legacy hash is intentionally
        NOT verified against the checkpoint: it is the stale value the runtime
        blocked on and the checkpoint's stored hash is the authoritative
        legacy anchor (see ``_commit_authority_recovery``).  On failure (real
        drift, unknown or ambiguous legacy profile, or an unbindable
        checkpoint) the state is left untouched and REPAIR_WORKSPACE_STALE is
        raised.  A current-profile binding keeps the normal stale-workspace
        check unchanged.  A legacy binding whose stored hash already equals
        the live workspace still requires an identifiable safe checkpoint;
        missing or invalid checkpoint authority remains blocked.  The method
        is idempotent and
        concurrency-safe: a losing concurrent worker observes the committed
        migration and returns without writing anything.
        """
        try:
            return self._recover_legacy_fingerprint_authority_once(attempt_id)
        except RepairApplicationError as error:
            if getattr(error, "diagnostic", None) is not None:
                logger.warning(
                    "legacy fingerprint recovery transaction rolled back",
                    extra={
                        "diagnostic": {
                            "reason": "TRANSACTION_ROLLBACK",
                            "error_code": error.code,
                            "error_message": _bounded_text(error.message, 1000),
                        }
                    },
                )
            raise
        except IntegrityError as error:
            integrity = _integrity_diagnostic(error)
            logger.exception(
                "legacy fingerprint recovery transaction rolled back",
                extra={
                    "diagnostic": {
                        "reason": "TRANSACTION_ROLLBACK",
                        **integrity,
                    }
                },
            )
            with self._scope() as session:
                attempt = session.get(RepairAttemptModel, attempt_id)
                binding = (
                    session.scalar(
                        select(StageWorkspaceBindingModel).where(
                            StageWorkspaceBindingModel.run_id == attempt.run_id,
                            StageWorkspaceBindingModel.stage_id == attempt.stage_id,
                            StageWorkspaceBindingModel.active.is_(True),
                        )
                    )
                    if attempt is not None
                    else None
                )
                if attempt is None or binding is None or binding.fingerprint_profile_id is None:
                    reason = (
                        "RECOVERY_LINEAGE_CONFLICT"
                        if "uq_repair_fingerprint_recovery" in json.dumps(integrity)
                        else "TRANSACTION_ROLLBACK"
                    )
                    raise _legacy_recovery_error(
                        reason,
                        details={
                            "attempt_id": attempt_id,
                            "binding_profile_id": binding.fingerprint_profile_id if binding else None,
                            **integrity,
                        },
                        cause=error,
                    )
                return {"recovered": False, "checkpoint_id": attempt.checkpoint_id}

    def _recover_legacy_fingerprint_authority_once(self, attempt_id: str) -> dict[str, object]:
        with self._scope() as session:
            attempt = session.scalar(
                select(RepairAttemptModel).where(RepairAttemptModel.id == attempt_id)
            )
            if attempt is None:
                raise RepairApplicationError("REPAIR_ATTEMPT_NOT_FOUND", "Repair attempt is missing")
            run = session.scalar(select(MigrationRunModel).where(MigrationRunModel.id == attempt.run_id))
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == attempt.run_id,
                    StageWorkspaceBindingModel.stage_id == attempt.stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if run is None or binding is None:
                raise RepairApplicationError("REPAIR_AUTHORITY_MISSING", "Repair authority is missing")
            run_root = run.run_root
            workspace_path = binding.workspace_path
            stored_fingerprint = binding.workspace_fingerprint
            profile_id = binding.fingerprint_profile_id
            checkpoint_id = attempt.checkpoint_id
        try:
            live_fingerprint = STAGE_FINGERPRINT_PROFILE.fingerprint(Path(workspace_path))
        except OSError as error:
            raise RepairApplicationError("REPAIR_WORKSPACE_MISSING", "Repair workspace is unavailable") from error
        if profile_id is not None:
            if live_fingerprint != stored_fingerprint:
                raise RepairApplicationError("REPAIR_WORKSPACE_STALE", "Repair workspace fingerprint changed")
            if checkpoint_id is None:
                raise RepairApplicationError(
                    "REPAIR_WORKSPACE_STALE",
                    "Repair checkpoint authority is missing",
                )
            return {"recovered": False, "checkpoint_id": checkpoint_id}
        with self._scope() as session:
            attempt = session.get(RepairAttemptModel, attempt_id)
            if attempt is None:
                raise RepairApplicationError("REPAIR_ATTEMPT_NOT_FOUND", "Repair attempt is missing")
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == attempt.run_id,
                    StageWorkspaceBindingModel.stage_id == attempt.stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if binding is None:
                raise RepairApplicationError("REPAIR_AUTHORITY_MISSING", "Repair authority is missing")
            try:
                workspace_root = Path(workspace_path).resolve(strict=True)
                workspace_root.relative_to(Path(run_root).resolve(strict=True))
            except (OSError, ValueError) as error:
                raise _legacy_recovery_error(
                    "CHECKPOINT_PATH_INVALID",
                    details={
                        "path_validation": "binding_workspace_outside_run_root",
                        "exception_type": type(error).__name__,
                    },
                    cause=error,
                )
            if live_fingerprint == stored_fingerprint:
                diagnostic = {}
                checkpoint, legacy_profile = self._identify_legacy_checkpoint(
                    session,
                    attempt,
                    run_root,
                    live_fingerprint,
                    stored_fingerprint,
                    diagnostic,
                )
                if checkpoint is None:
                    raise _legacy_recovery_error(
                        diagnostic.pop("reason", "NO_ELIGIBLE_PRE_REPAIR_CHECKPOINT"),
                        details=diagnostic,
                    )
                return self._commit_authority_recovery(
                    session, attempt, binding, checkpoint, legacy_profile, live_fingerprint
                )
            diagnostic = {}
            checkpoint, legacy_profile = self._identify_legacy_checkpoint(
                session,
                attempt,
                run_root,
                live_fingerprint,
                stored_fingerprint,
                diagnostic,
            )
            if checkpoint is None:
                raise _legacy_recovery_error(
                    diagnostic.pop("reason", "CANONICAL_FINGERPRINT_MISMATCH"),
                    details=diagnostic,
                )
            return self._commit_authority_recovery(
                session, attempt, binding, checkpoint, legacy_profile, live_fingerprint
            )

    @staticmethod
    def _immutable_checkpoint_references(session, attempt) -> set[str]:
        if not attempt.failure_evidence_artifact_id or not attempt.failure_evidence_checksum:
            return set()
        metadata = session.get(
            ArtifactMetadataModel,
            f"metadata-{attempt.failure_evidence_artifact_id}",
        )
        run = session.get(MigrationRunModel, attempt.run_id)
        if (
            metadata is None
            or run is None
            or metadata.run_id != attempt.run_id
            or metadata.stage_id != attempt.stage_id
            or metadata.artifact_type != ArtifactType.JSON.value
            or not metadata.immutable
            or metadata.checksum != attempt.failure_evidence_checksum
            or not run.artifact_root
        ):
            return set()
        try:
            artifact = LocalFilesystemArtifactStore(
                Path(str(run.artifact_root)).parent,
                fixed_run_root=Path(str(run.artifact_root)),
            ).read_artifact(attempt.run_id, metadata.relative_path)
            if (
                artifact.ref.artifact_id != attempt.failure_evidence_artifact_id
                or artifact.ref.artifact_type != ArtifactType.JSON
                or artifact.ref.checksum != attempt.failure_evidence_checksum
            ):
                return set()
            evidence = json.loads(artifact.content)
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, TypeError, ValueError):
            return set()
        if not isinstance(evidence, dict):
            return set()
        if (
            evidence.get("schema_version") != "transformer-failure-evidence-v1"
            or evidence.get("run_id") != attempt.run_id
            or evidence.get("stage_id") != attempt.stage_id
        ):
            return set()
        references = set()
        checkpoint_id = evidence.get("checkpoint_id")
        if isinstance(checkpoint_id, str) and checkpoint_id:
            references.add(checkpoint_id)
        execution_id = evidence.get("execution_id")
        if isinstance(execution_id, str) and execution_id:
            execution = session.get(CommandExecutionModel, execution_id)
            if (
                execution is not None
                and execution.run_id == attempt.run_id
                and execution.stage_id == attempt.stage_id
                and execution.checkpoint_id
            ):
                references.add(execution.checkpoint_id)
        return references

    @staticmethod
    def _identify_legacy_checkpoint(
        session,
        attempt,
        run_root,
        live_fingerprint,
        binding_fingerprint=None,
        diagnostic=None,
    ):
        """Deterministically identify the attempt's historical pre-repair checkpoint.

        For every stage checkpoint (ascending sequence) the supported legacy
        profiles are evaluated in fixed order against the checkpoint's stored
        fingerprint (check 1).  A checkpoint qualifies only when exactly one
        legacy profile reproduces its stored hash and the live workspace
        matches the checkpoint under the current canonical profile (check 2).
        Exactly one
        qualifying (checkpoint, profile) pair is accepted; anything else —
        unknown or ambiguous legacy profile, or no/several matching
        checkpoints — returns ``(None, None)`` and the caller fails closed.
        When the attempt is already bound to a checkpoint, ONLY that
        checkpoint is eligible (the bound checkpoint either verifies or the
        recovery fails closed). References to other checkpoint kinds remain
        provenance and do not participate in authority selection.
        """
        diagnostic = diagnostic if diagnostic is not None else {}
        diagnosis_references = re.findall(
            r"(?:^|[;\s])checkpoint=([^\s;]+)", attempt.diagnosis or ""
        )
        evidence_references = RepairApplicationService._immutable_checkpoint_references(
            session, attempt
        )
        diagnostic.update(
            {
                "referenced_checkpoint_ids": sorted(
                    set(diagnosis_references) | evidence_references
                ),
                "reference_sources": {
                    "diagnosis": diagnosis_references,
                    "failure_evidence": sorted(evidence_references),
                },
            }
        )
        referenced_ids = set(diagnosis_references) | evidence_references
        has_checkpoint_reference = "checkpoint=" in (attempt.diagnosis or "") or bool(referenced_ids)
        if "checkpoint=" in (attempt.diagnosis or "") and len(diagnosis_references) != 1:
            diagnostic.update(
                {
                    "reason": "CHECKPOINT_REFERENCE_CONFLICT",
                    "diagnosis_reference_count": len(diagnosis_references),
                }
            )
            return None, None
        reference_checkpoints = {}
        reference_diagnostics = []
        for checkpoint_id in sorted(referenced_ids):
            checkpoint = session.get(StageCheckpointModel, checkpoint_id)
            sources = []
            if checkpoint_id in diagnosis_references:
                sources.append("diagnosis")
            if checkpoint_id in evidence_references:
                sources.append("failure_evidence")
            reference = {
                "checkpoint_id": checkpoint_id,
                "sources": sources,
                "kind": checkpoint.kind if checkpoint is not None else None,
                "safe_for_resume": (
                    bool(checkpoint.safe_for_resume) if checkpoint is not None else None
                ),
            }
            if (
                checkpoint is None
                or checkpoint.run_id != attempt.run_id
                or checkpoint.stage_id != attempt.stage_id
            ):
                reference["validation"] = "wrong_run_stage_or_missing"
                reference_diagnostics.append(reference)
                diagnostic.update(
                    {
                        "reason": "CHECKPOINT_REFERENCE_CONFLICT",
                        "reference_checkpoints": reference_diagnostics,
                    }
                )
                return None, None
            reference["validation"] = "same_run_stage"
            reference_checkpoints[checkpoint_id] = checkpoint
            reference_diagnostics.append(reference)
        diagnostic["reference_checkpoints"] = reference_diagnostics

        authority_reference_ids = {
            checkpoint_id
            for checkpoint_id, checkpoint in reference_checkpoints.items()
            if checkpoint.kind == "pre_repair" and checkpoint.safe_for_resume
        }
        unsafe_authority_reference_ids = {
            checkpoint_id
            for checkpoint_id, checkpoint in reference_checkpoints.items()
            if checkpoint.kind == "pre_repair" and not checkpoint.safe_for_resume
        }
        diagnostic.update(
            {
                "authority_reference_ids": sorted(authority_reference_ids),
                "provenance_reference_ids": sorted(
                    set(reference_checkpoints) - authority_reference_ids
                ),
            }
        )

        bound = None
        if attempt.checkpoint_id is not None:
            bound = session.get(StageCheckpointModel, attempt.checkpoint_id)
            if bound is None or bound.run_id != attempt.run_id or bound.stage_id != attempt.stage_id:
                diagnostic.update(
                    {
                        "reason": "CHECKPOINT_REFERENCE_CONFLICT",
                        "attempt_checkpoint_id": attempt.checkpoint_id,
                        "checkpoint_lookup": "missing_or_wrong_run_stage",
                    }
                )
                return None, None
            if bound.kind == "pre_repair" and bound.safe_for_resume:
                authority_reference_ids.add(bound.id)
            elif bound.kind == "pre_repair":
                unsafe_authority_reference_ids.add(bound.id)
        diagnostic["authority_reference_ids"] = sorted(authority_reference_ids)

        if unsafe_authority_reference_ids:
            diagnostic.update(
                {
                    "reason": "NO_ELIGIBLE_PRE_REPAIR_CHECKPOINT",
                    "unsafe_authority_reference_ids": sorted(unsafe_authority_reference_ids),
                }
            )
            return None, None
        if len(authority_reference_ids) > 1:
            diagnostic.update(
                {
                    "reason": "CHECKPOINT_REFERENCE_CONFLICT",
                    "authority_reference_ids": sorted(authority_reference_ids),
                }
            )
            return None, None

        if bound is not None:
            checkpoints = [bound]
        elif authority_reference_ids:
            checkpoints = [reference_checkpoints[next(iter(authority_reference_ids))]]
        else:
            checkpoints = session.scalars(
                select(StageCheckpointModel).where(
                    StageCheckpointModel.run_id == attempt.run_id,
                    StageCheckpointModel.stage_id == attempt.stage_id,
                ).order_by(StageCheckpointModel.sequence)
            ).all()
        diagnostic["checkpoint_count"] = len(checkpoints)
        try:
            run_root_resolved = Path(run_root).resolve(strict=True)
        except OSError as error:
            diagnostic.update(
                {
                    "reason": "CHECKPOINT_PATH_INVALID",
                    "path_validation": "run_root_invalid",
                    "exception_type": type(error).__name__,
                    "candidate_diagnostics": [],
                    "qualifying_candidate_count": 0,
                }
            )
            return None, None
        matches = []
        candidate_diagnostics = []
        for checkpoint in checkpoints:
            candidate = {
                "checkpoint_id": checkpoint.id,
                "kind": checkpoint.kind,
                "safe_for_resume": bool(checkpoint.safe_for_resume),
                "stored_legacy_fingerprint": checkpoint.workspace_fingerprint,
            }
            if checkpoint.kind != "pre_repair" or not checkpoint.safe_for_resume:
                candidate["rejection_reason"] = "NO_ELIGIBLE_PRE_REPAIR_CHECKPOINT"
                candidate_diagnostics.append(candidate)
                continue
            try:
                checkpoint_root = Path(checkpoint.workspace_path).resolve(strict=True)
                checkpoint_root.relative_to(run_root_resolved)
                candidate["path_validation"] = "valid"
            except (OSError, ValueError) as error:
                candidate.update(
                    {
                        "path_validation": "invalid",
                        "exception_type": type(error).__name__,
                        "rejection_reason": "CHECKPOINT_PATH_INVALID",
                    }
                )
                candidate_diagnostics.append(candidate)
                continue
            try:
                legacy_matches = [
                    profile
                    for profile in SUPPORTED_LEGACY_FINGERPRINT_PROFILES
                    if profile.fingerprint(checkpoint_root) == checkpoint.workspace_fingerprint
                ]
                current_fingerprint = STAGE_FINGERPRINT_PROFILE.fingerprint(checkpoint_root)
            except OSError as error:
                candidate.update(
                    {
                        "path_validation": "fingerprint_unavailable",
                        "exception_type": type(error).__name__,
                        "rejection_reason": "CHECKPOINT_PATH_INVALID",
                    }
                )
                candidate_diagnostics.append(candidate)
                continue
            candidate.update(
                {
                    "legacy_profile_match_count": len(legacy_matches),
                    "legacy_profile_match_ids": [profile.profile_id for profile in legacy_matches],
                    "checkpoint_current_profile_fingerprint": current_fingerprint,
                    "live_current_profile_fingerprint": live_fingerprint,
                }
            )
            if len(legacy_matches) != 1:
                candidate["rejection_reason"] = (
                    "LEGACY_PROFILE_NO_MATCH" if not legacy_matches else "LEGACY_PROFILE_AMBIGUOUS"
                )
                candidate_diagnostics.append(candidate)
                continue
            if current_fingerprint != live_fingerprint:
                candidate["rejection_reason"] = "CANONICAL_FINGERPRINT_MISMATCH"
                candidate_diagnostics.append(candidate)
                continue
            matches.append((checkpoint, legacy_matches[0]))
            candidate["rejection_reason"] = "QUALIFIED"
            candidate_diagnostics.append(candidate)
        diagnostic.update(
            {
                "candidate_diagnostics": candidate_diagnostics,
                "qualifying_candidate_count": len(matches),
            }
        )
        if len(matches) != 1:
            rejection_reasons = {
                item.get("rejection_reason")
                for item in candidate_diagnostics
                if item.get("rejection_reason") not in {None, "QUALIFIED"}
            }
            if diagnostic.get("reason") == "CHECKPOINT_REFERENCE_CONFLICT":
                pass
            elif len(rejection_reasons) == 1 and not matches:
                diagnostic["reason"] = next(iter(rejection_reasons))
            else:
                diagnostic["reason"] = "NO_ELIGIBLE_PRE_REPAIR_CHECKPOINT"
            return None, None
        return matches[0]

    def _commit_authority_recovery(
        self, session, attempt, binding, checkpoint, legacy_profile, live_fingerprint
    ) -> dict[str, object]:
        """CAS-migrate the binding, CAS-bind the attempt, and persist the lineage.

        Runs inside the caller's transaction; the caller commits on success and
        rolls back on failure.  Only the first concurrent worker wins the
        binding CAS; every other worker observes ``fingerprint_profile_id``
        already set and returns without writing.

        The binding's STORED legacy hash is intentionally NOT required to
        match the checkpoint hash: the binding hash is precisely the stale
        legacy value being replaced (the runtime blocked on it), while the
        checkpoint's stored hash is the authoritative legacy anchor that
        check 1 verifies under the identified legacy profile.  The lineage
        row records the replaced binding hash explicitly.
        """
        now = self._now()
        replaced_binding_fingerprint = binding.workspace_fingerprint
        binding_claim = session.execute(
            update(StageWorkspaceBindingModel)
            .where(
                StageWorkspaceBindingModel.id == binding.id,
                StageWorkspaceBindingModel.run_id == attempt.run_id,
                StageWorkspaceBindingModel.stage_id == attempt.stage_id,
                StageWorkspaceBindingModel.active.is_(True),
                StageWorkspaceBindingModel.fingerprint_profile_id.is_(None),
                StageWorkspaceBindingModel.workspace_fingerprint == replaced_binding_fingerprint,
            )
            .values(
                workspace_fingerprint=live_fingerprint,
                fingerprint_profile_id=STAGE_FINGERPRINT_PROFILE.profile_id,
                last_verified_fingerprint=live_fingerprint,
                last_verified_at=now,
            )
        )
        if binding_claim.rowcount != 1:
            session.expire_all()
            actual_binding = session.get(StageWorkspaceBindingModel, binding.id)
            actual_attempt = session.get(RepairAttemptModel, attempt.id)
            details = {
                "rowcount": binding_claim.rowcount,
                "expected": {
                    "id": binding.id,
                    "run_id": attempt.run_id,
                    "stage_id": attempt.stage_id,
                    "active": True,
                    "fingerprint_profile_id": None,
                    "workspace_fingerprint": replaced_binding_fingerprint,
                },
                "actual_binding": (
                    {
                        "id": actual_binding.id,
                        "run_id": actual_binding.run_id,
                        "stage_id": actual_binding.stage_id,
                        "active": actual_binding.active,
                        "fingerprint_profile_id": actual_binding.fingerprint_profile_id,
                        "workspace_fingerprint": actual_binding.workspace_fingerprint,
                    }
                    if actual_binding is not None
                    else None
                ),
                "actual_attempt": (
                    {
                        "checkpoint_id": actual_attempt.checkpoint_id,
                        "state_version": actual_attempt.state_version,
                    }
                    if actual_attempt is not None
                    else None
                ),
            }
            if actual_binding is not None and actual_binding.fingerprint_profile_id is not None:
                return {
                    "recovered": False,
                    "checkpoint_id": actual_attempt.checkpoint_id if actual_attempt else None,
                }
            raise _legacy_recovery_error("BINDING_CAS_MISS", details=details)
        if attempt.checkpoint_id is None:
            attempt_claim = session.execute(
                update(RepairAttemptModel)
                .where(
                    RepairAttemptModel.id == attempt.id,
                    RepairAttemptModel.run_id == attempt.run_id,
                    RepairAttemptModel.stage_id == attempt.stage_id,
                    RepairAttemptModel.checkpoint_id.is_(None),
                    RepairAttemptModel.state_version == attempt.state_version,
                )
                .values(
                    checkpoint_id=checkpoint.id,
                    state_version=attempt.state_version + 1,
                    updated_at=now,
                    diagnosis=(attempt.diagnosis or "")
                    + f"; authority_recovered_from={legacy_profile.profile_id}:{checkpoint.workspace_fingerprint}",
                )
            )
            if attempt_claim.rowcount != 1:
                session.expire_all()
                actual_attempt = session.get(RepairAttemptModel, attempt.id)
                raise _legacy_recovery_error(
                    "ATTEMPT_CAS_MISS",
                    code="REPAIR_ARTIFACT_RECOVERY_FAILED",
                    details={
                        "rowcount": attempt_claim.rowcount,
                        "expected": {
                            "id": attempt.id,
                            "run_id": attempt.run_id,
                            "stage_id": attempt.stage_id,
                            "checkpoint_id": None,
                            "state_version": attempt.state_version,
                        },
                        "actual": (
                            {
                                "checkpoint_id": actual_attempt.checkpoint_id,
                                "state_version": actual_attempt.state_version,
                            }
                            if actual_attempt is not None
                            else None
                        ),
                    },
                )
        elif attempt.checkpoint_id != checkpoint.id:
            raise _legacy_recovery_error(
                "CHECKPOINT_REFERENCE_CONFLICT",
                details={
                    "attempt_checkpoint_id": attempt.checkpoint_id,
                    "candidate_checkpoint_id": checkpoint.id,
                },
            )
        existing_lineage = session.scalar(
            select(RepairFingerprintRecoveryModel).where(
                RepairFingerprintRecoveryModel.run_id == attempt.run_id,
                RepairFingerprintRecoveryModel.stage_id == attempt.stage_id,
                RepairFingerprintRecoveryModel.attempt_id == attempt.id,
                RepairFingerprintRecoveryModel.checkpoint_id == checkpoint.id,
            )
        )
        if existing_lineage is None:
            session.add(
                RepairFingerprintRecoveryModel(
                    id=f"fp-recovery-{uuid4().hex[:12]}",
                    run_id=attempt.run_id,
                    stage_id=attempt.stage_id,
                    attempt_id=attempt.id,
                    checkpoint_id=checkpoint.id,
                    legacy_profile_id=legacy_profile.profile_id,
                    legacy_fingerprint=checkpoint.workspace_fingerprint,
                    replaced_binding_fingerprint=replaced_binding_fingerprint,
                    current_profile_id=STAGE_FINGERPRINT_PROFILE.profile_id,
                    current_fingerprint=live_fingerprint,
                    recovered_at=now,
                )
            )
        return {
            "recovered": True,
            "checkpoint_id": checkpoint.id,
            "legacy_profile_id": legacy_profile.profile_id,
            "legacy_fingerprint": checkpoint.workspace_fingerprint,
            "current_fingerprint": live_fingerprint,
        }

    def _recover_legacy_context_pack(self, attempt_id: str) -> None:
        """Replace only a pre-bounds pack from authoritative failure/workspace data."""
        context = self._attempt_context(attempt_id, validate_context_pack=False)
        try:
            old_pack = json.loads(context["segments"][1])
            failure = json.loads(context["segments"][0])
        except (TypeError, ValueError, IndexError) as error:
            raise RepairApplicationError(
                "REPAIR_CONTEXT_RECOVERY_FAILED", "Legacy repair evidence cannot be loaded"
            ) from error
        if not isinstance(old_pack, dict) or not isinstance(failure, dict):
            raise RepairApplicationError(
                "REPAIR_CONTEXT_RECOVERY_FAILED", "Legacy repair evidence is invalid"
            )
        if "bounds" in old_pack:
            self._validate_context_pack(context["segments"][1])
            return
        if (
            failure.get("schema_version") != "transformer-failure-evidence-v1"
            or failure.get("run_id") != context["run_id"]
            or failure.get("stage_id") != context["stage_id"]
            or failure.get("failure_fingerprint") != context.get("failure_fingerprint")
            or failure.get("workspace_fingerprint")
            != (context.get("pre_fingerprint") or context["workspace_stored_fingerprint"])
            or not isinstance(failure.get("normalized_failure"), dict)
            or not isinstance(failure.get("forbidden_change_policy"), dict)
        ):
            raise RepairApplicationError(
                "REPAIR_CONTEXT_RECOVERY_FAILED", "Authoritative repair failure evidence is invalid"
            )

        old_artifact_id = str(context["context_pack_artifact_id"])
        old_checksum = str(context["context_pack_checksum"])
        recovery_path = (
            f"05_repairs/{context['stage_id']}/"
            f"{hashlib.sha256(f'{old_artifact_id}:{old_checksum}'.encode()).hexdigest()}"
            "-context-recovered.json"
        )
        evidence = {
            "run_id": context["run_id"],
            "stage_id": context["stage_id"],
            "workspace_path": context["workspace_path"],
            "workspace_fingerprint": context["workspace_stored_fingerprint"],
            "artifact_root": context["artifact_root"],
            "failure_fingerprint": failure["failure_fingerprint"],
            "normalized_failure": failure["normalized_failure"],
            "forbidden_change_policy": failure["forbidden_change_policy"],
        }
        try:
            workspace = Path(str(context["workspace_path"])).resolve(strict=True)
            workspace.relative_to(Path(str(context["run_root"])).resolve(strict=True))
        except (OSError, ValueError) as error:
            raise RepairApplicationError(
                "REPAIR_CONTEXT_RECOVERY_FAILED", "Repair workspace escapes the authoritative run root"
            ) from error
        with self._scope() as session:
            attempt = session.get(RepairAttemptModel, attempt_id)
            if (
                attempt is None
                or attempt.context_pack_artifact_id != old_artifact_id
                or attempt.context_pack_checksum != old_checksum
            ):
                return
            expected_state = attempt.state_version
            claimed = session.execute(
                update(RepairAttemptModel)
                .where(
                    RepairAttemptModel.id == attempt_id,
                    RepairAttemptModel.run_id == context["run_id"],
                    RepairAttemptModel.stage_id == context["stage_id"],
                    RepairAttemptModel.state_version == expected_state,
                    RepairAttemptModel.context_pack_artifact_id == old_artifact_id,
                    RepairAttemptModel.context_pack_checksum == old_checksum,
                )
                .values(state_version=expected_state + 1)
            )
            if claimed.rowcount != 1:
                return

            store = LocalFilesystemArtifactStore(
                Path(str(context["artifact_root"])).parent,
                fixed_run_root=Path(str(context["artifact_root"])),
            )
            try:
                replacement = store.read_artifact(context["run_id"], recovery_path)
                if (
                    replacement.envelope is None
                    or replacement.envelope.input_hashes.get("failure")
                    != context["failure_evidence_checksum"]
                    or replacement.envelope.input_hashes.get("recovered_from") != old_checksum
                ):
                    raise ArtifactStoreError("Legacy context replacement lineage is invalid")
                self._validate_context_pack(replacement.content)
            except ArtifactNotFoundError:
                replacement = FailureEvidenceService(now_provider=self._now).write_context_pack(
                    evidence,
                    str(context["failure_evidence_checksum"]),
                    relative_path=recovery_path,
                    lineage_from=old_checksum,
                )
                if StageSandboxCopier.fingerprint(Path(str(context["workspace_path"]))) != context["workspace_stored_fingerprint"]:
                    raise RepairApplicationError(
                        "REPAIR_WORKSPACE_STALE", "Repair workspace changed during context recovery"
                    )
                self._validate_context_pack(replacement.content)

            metadata_id = "metadata-" + replacement.ref.artifact_id
            metadata = session.get(ArtifactMetadataModel, metadata_id)
            if metadata is None:
                session.add(
                    ArtifactMetadataModel(
                        id=metadata_id,
                        run_id=context["run_id"],
                        stage_id=context["stage_id"],
                        artifact_type=replacement.ref.artifact_type.value,
                        relative_path=replacement.ref.relative_path,
                        checksum=replacement.ref.checksum,
                        schema_version=replacement.envelope.schema_version if replacement.envelope else 1,
                        created_at=replacement.ref.created_at,
                        finalized_at=replacement.ref.created_at,
                        immutable=True,
                        size_bytes=len(replacement.content.encode("utf-8")),
                        safe_metadata={
                            "lineage": {
                                "recovered_from_artifact_id": old_artifact_id,
                                "recovered_from_checksum": old_checksum,
                            }
                        },
                    )
                )
            elif metadata.checksum != replacement.ref.checksum:
                raise ArtifactStoreError("Legacy context replacement metadata is stale")
            finalized = session.execute(
                update(RepairAttemptModel)
                .where(
                    RepairAttemptModel.id == attempt_id,
                    RepairAttemptModel.state_version == expected_state + 1,
                    RepairAttemptModel.context_pack_artifact_id == old_artifact_id,
                    RepairAttemptModel.context_pack_checksum == old_checksum,
                )
                .values(
                    context_pack_artifact_id=replacement.ref.artifact_id,
                    context_pack_checksum=replacement.ref.checksum,
                    diagnosis=(attempt.diagnosis or "")
                    + f"; context_recovered_from={old_artifact_id}:{old_checksum}",
                    state_version=expected_state + 2,
                    updated_at=self._now(),
                )
            )
            if finalized.rowcount != 1:
                raise RepairApplicationError(
                    "REPAIR_CONTEXT_RECOVERY_FAILED", "Repair attempt changed during context recovery"
                )

    @staticmethod
    def _validate_context_pack(content: str) -> None:
        """Re-validate the repair context pack's bounds contract at use time.

        The pack is checksum-bound to the attempt row and envelope, but its
        internal bounds block (byte budgets, preimage checksums, deterministic
        entry ordering) is only enforced here, so a structurally invalid or
        tampered pack fails closed with REPAIR_CONTEXT_INVALID.
        """
        try:
            payload = json.loads(content)
        except ValueError as error:
            raise RepairApplicationError(
                "REPAIR_CONTEXT_INVALID", "Repair context pack is not valid JSON"
            ) from error
        try:
            validate_context_pack(payload)
        except ValueError as error:
            raise RepairApplicationError("REPAIR_CONTEXT_INVALID", str(error)) from error

    @staticmethod
    def _validate_artifact_envelope(
        artifact: StoredArtifact,
        *,
        expected_run_id: object,
        expected_stage_id: object,
        expected_attempt_id: object,
        pre_attempt: bool,
        metadata_checksum: str,
    ) -> None:
        """Validate one repair artifact envelope's run/stage/attempt ownership.

        PRE-ATTEMPT artifacts (failure evidence, context pack) are written by
        FailureEvidenceService before the RepairAttempt row exists, so their
        envelope attempt_id is legitimately NULL; a non-NULL id must still
        equal the current attempt. ATTEMPT-BOUND artifacts (proposal, review,
        repair error) require the exact RepairAttempt id and reject NULL.
        Checksum, run_id and stage_id binding stays strict for both roles.
        """
        envelope = artifact.envelope
        if (
            artifact.ref.checksum != metadata_checksum
            or envelope is None
            or envelope.run_id != expected_run_id
            or envelope.stage_id != expected_stage_id
        ):
            raise RepairApplicationError(
                "REPAIR_ARTIFACT_RECOVERY_FAILED", "Repair artifact envelope binding is stale"
            )
        if pre_attempt:
            if envelope.attempt_id not in (None, expected_attempt_id):
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED", "Repair artifact envelope binding is stale"
                )
            return
        if envelope.attempt_id != expected_attempt_id:
            raise RepairApplicationError(
                "REPAIR_ARTIFACT_RECOVERY_FAILED", "Repair artifact envelope binding is stale"
            )

    @staticmethod
    def _authority_snapshot(context: dict[str, object]) -> dict[str, object]:
        return {
            key: context.get(key)
            for key in (
                "run_id", "run_state_version", "continuation_state_version", "stage_id",
                "stage_plan_id", "stage_plan_checksum", "stage_plan_state_version",
                "attempt_id", "attempt_number", "attempt_status", "parent_attempt_id",
                "parent_review_artifact_id", "parent_review_checksum",
                "failure_evidence_artifact_id", "failure_evidence_checksum",
                "context_pack_artifact_id", "context_pack_checksum",
                "proposal_artifact_id", "proposal_checksum", "workspace_binding_id",
                "proposer_invocation_id", "reviewer_invocation_id",
                "workspace_path", "workspace_stored_fingerprint", "workspace_live_fingerprint",
                "invocation_id", "invocation_state_version", "request_checksum",
                "prompt_version", "schema_version",
            )
        }

    @staticmethod
    def _backend_authority_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
        return {
            key: value
            for key, value in snapshot.items()
            if key not in {"invocation_id", "invocation_state_version", "request_checksum", "prompt_version", "schema_version"}
        }

    def _assert_fresh_authority(
        self, context: dict[str, object], *, role: str, include_proposal: bool = False
    ) -> dict[str, object]:
        fresh = self._attempt_context(str(context["attempt_id"]), include_proposal=include_proposal)
        if self._backend_authority_snapshot(fresh["authority_snapshot"]) != self._backend_authority_snapshot(context["authority_snapshot"]):
            raise RepairApplicationError(
                "REPAIR_REVIEW_STALE" if role == "reviewer" else "REPAIR_PROPOSAL_STALE",
                "Repair authority changed while the provider was running",
            )
        fresh.update(
            request_checksum=context.get("request_checksum"),
            prompt_version=context.get("prompt_version"),
            schema_version=context.get("schema_version"),
            invocation_id=context.get("invocation_id"),
            invocation_key=context.get("invocation_key"),
            semantic_retry_count=context.get("semantic_retry_count"),
            retry_of_invocation_key=context.get("retry_of_invocation_key"),
            invocation_state_version=context.get("invocation_state_version"),
            authority_snapshot=context["authority_snapshot"],
            invocation_owner_state=context.get("invocation_owner_state"),
        )
        return fresh

    def _call(self, context, *, role, task, schema_name, schema, policy):
        if self._gateway is None and not get_settings().llm_enabled:
            raise RepairApplicationError(
                "REPAIR_LLM_DISABLED", "Governed repair requires the configured Azure gateway"
            )
        registry = PromptSchemaRegistry(version=get_settings().llm_schema_registry_version)
        registry.register(schema_name, schema)
        try:
            gateway = self._gateway or AzureOpenAILLMGateway(settings=get_settings(), registry=registry)
            if isinstance(gateway, AzureOpenAILLMGateway):
                gateway._prompt_registry.get(schema_name, task)
                gateway.registry.json_schema(schema_name)
            self._mark_transport_started(context, role)
            response = gateway.complete(
                LlmRequest(
                    request_id=_context_invocation_key(context, role),
                    run_id=str(context["run_id"]),
                    stage_id=str(context["stage_id"]),
                    agent_kind=AgentKind.REPAIR,
                    task_type=task,
                    role=role,
                    prompt_name=schema_name,
                    system_policy=policy,
                    context=[
                        LlmContextSegment(
                            segment_id=f"evidence-{index}",
                            label="untrusted repair evidence",
                            content=content,
                            untrusted=True,
                        )
                        for index, content in enumerate(context["segments"])
                    ],
                    response_schema=schema_name,
                    max_output_tokens=4096,
                )
            )
            return registry.validate(schema_name, response.structured_output), response
        except AzureGatewayError as exc:
            translated = _translate_gateway_failure(exc)
            uncertain = self._persist_failure(context, role, translated)
            if uncertain:
                raise RepairApplicationError(
                    "REPAIR_INVOCATION_UNCERTAIN",
                    "Repair provider transport started without a response",
                ) from exc
            raise translated from exc

    def _recover_completed(self, context, *, role: str, schema_name=None, task_type=None, schema=None):
        invocation_key = _context_invocation_key(context, role)
        artifact_field = "proposal_artifact_id" if role == "proposer" else "review_artifact_id"
        with self._scope() as session:
            invocation = (
                session.query(LlmInvocationModel)
                .filter_by(run_id=context["run_id"], idempotency_key=invocation_key)
                .one_or_none()
            )
            if invocation is None:
                return None
            if invocation.status == "failed":
                return None
            if invocation.status == "in_progress" and not invocation.transport_started:
                return None
            if invocation.status == "in_progress":
                raise RepairApplicationError(
                    "REPAIR_INVOCATION_UNCERTAIN",
                    "Repair LLM invocation outcome is uncertain",
                )
            if invocation.status != "completed":
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED",
                    "Completed repair LLM invocation is not finalized",
                )
            legacy_v1 = invocation.schema_version == "schema-registry-v1" and invocation.prompt_version in {
                "prompt-repair-proposer-v1", "prompt-repair-reviewer-v1",
                "repair-proposer-v1", "repair-reviewer-v1",
            }
            if schema_name and task_type and schema:
                prompt_version = self._prompt_version(schema_name, task_type)
                schema_version = get_settings().llm_schema_registry_version
                expected_request = self._logical_request_checksum(
                    context["segments"], schema_name, prompt_version, schema_version
                )
                if not legacy_v1 and (
                    invocation.request_checksum != expected_request
                    or invocation.prompt_version != prompt_version
                    or invocation.schema_version != schema_version
                ):
                    raise RepairApplicationError(
                        "REPAIR_ARTIFACT_RECOVERY_FAILED",
                        "Completed invocation provenance is incompatible",
                    )
            attempt = session.get(RepairAttemptModel, context["attempt_id"])
            if (
                attempt is None
                or attempt.run_id != context["run_id"]
                or attempt.stage_id != context["stage_id"]
            ):
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED",
                    "Repair attempt is missing",
                )
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == attempt.run_id,
                    TransformationContinuationModel.current_stage_id == attempt.stage_id,
                )
            )
            stage_plan = session.scalar(
                select(StageExecutionPlanModel).where(
                    StageExecutionPlanModel.id == continuation.stage_plan_id if continuation else False,
                    StageExecutionPlanModel.run_id == attempt.run_id,
                    StageExecutionPlanModel.stage_id == attempt.stage_id,
                    StageExecutionPlanModel.checksum == continuation.stage_plan_checksum if continuation else False,
                )
            ) if continuation else None
            if (
                continuation is None
                or stage_plan is None
                or (
                    context.get("continuation_state_version") is not None
                    and continuation.state_version != context.get("continuation_state_version")
                )
                or (
                    context.get("stage_plan_id") is not None
                    and continuation.stage_plan_id != context.get("stage_plan_id")
                )
                or (
                    context.get("stage_plan_checksum") is not None
                    and continuation.stage_plan_checksum != context.get("stage_plan_checksum")
                )
                or (
                    context.get("stage_plan_state_version") is not None
                    and stage_plan.state_version != context.get("stage_plan_state_version")
                )
            ):
                raise RepairApplicationError("REPAIR_ARTIFACT_RECOVERY_FAILED", "Completed continuation lineage is stale")
            expected_role = "repair_proposer" if role == "proposer" else "repair_reviewer"
            expected_task = LlmTaskType.REPAIR_DIAGNOSIS.value if role == "proposer" else LlmTaskType.REPAIR_REVIEW.value
            if invocation.role != expected_role or invocation.task_type != expected_task or invocation.stage_id != attempt.stage_id:
                raise RepairApplicationError("REPAIR_ARTIFACT_RECOVERY_FAILED", "Completed invocation identity is invalid")
            if context.get("request_checksum") and invocation.request_checksum != context["request_checksum"]:
                raise RepairApplicationError("REPAIR_ARTIFACT_RECOVERY_FAILED", "Completed invocation request lineage is stale")
            if attempt.parent_attempt_id:
                parent = session.scalar(select(RepairAttemptModel).where(RepairAttemptModel.id == attempt.parent_attempt_id, RepairAttemptModel.run_id == attempt.run_id, RepairAttemptModel.stage_id == attempt.stage_id))
                if parent is None or parent.attempt_number >= attempt.attempt_number:
                    raise RepairApplicationError("REPAIR_ARTIFACT_RECOVERY_FAILED", "Completed attempt parent lineage is invalid")
            binding = session.scalar(select(StageWorkspaceBindingModel).where(StageWorkspaceBindingModel.run_id == attempt.run_id, StageWorkspaceBindingModel.stage_id == attempt.stage_id, StageWorkspaceBindingModel.active.is_(True)))
            if context.get("workspace_path") and (binding is None or binding.id != context.get("workspace_binding_id") or binding.workspace_path != context["workspace_path"] or StageSandboxCopier.fingerprint(Path(binding.workspace_path)) != binding.workspace_fingerprint):
                raise RepairApplicationError("REPAIR_ARTIFACT_RECOVERY_FAILED", "Completed workspace binding is stale")
            artifact_id = getattr(attempt, artifact_field)
            if not artifact_id:
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED",
                    "Completed repair LLM invocation has no persisted artifact",
                )
            metadata = session.get(ArtifactMetadataModel, "metadata-" + artifact_id)
            if (
                metadata is None
                or metadata.run_id != attempt.run_id
                or metadata.stage_id != attempt.stage_id
                or (
                    role == "reviewer"
                    and attempt.review_checksum != metadata.checksum
                )
                or (
                    role == "proposer"
                    and attempt.proposal_checksum != metadata.checksum
                )
                or artifact_id not in (invocation.artifact_ids or [])
                or (invocation.artifact_checksums or {}).get(artifact_id) != metadata.checksum
                or invocation.role != ("repair_proposer" if role == "proposer" else "repair_reviewer")
                or (
                    getattr(attempt, "proposer_invocation_id" if role == "proposer" else "reviewer_invocation_id")
                    not in ({None, invocation.id} if legacy_v1 else {invocation.id})
                )
            ):
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED",
                    "Completed repair artifact lineage is invalid",
                )
            relative_path = metadata.relative_path
        root = Path(str(context["artifact_root"]))
        store = LocalFilesystemArtifactStore(root.parent, fixed_run_root=root)
        try:
            stored = store.read_artifact(str(context["run_id"]), relative_path)
            if stored.ref.artifact_id != artifact_id or stored.ref.checksum != metadata.checksum:
                raise ArtifactStoreError("Completed repair artifact checksum binding is invalid")
            payload = json.loads(stored.content)
            if role == "proposer":
                value = RepairProposal.model_validate(payload).model_dump(mode="json")
                if (
                    value["failure_evidence_checksum"] != attempt.failure_evidence_checksum
                    or value["context_pack_checksum"] != attempt.context_pack_checksum
                ):
                    raise RepairApplicationError("REPAIR_PROPOSAL_STALE", "Completed proposal evidence lineage is stale")
            else:
                value = RepairReview.model_validate(payload).model_dump(mode="json")
                if value["proposal_checksum"] != attempt.proposal_checksum:
                    raise RepairApplicationError("REPAIR_REVIEW_STALE", "Completed review proposal lineage is stale")
            return payload if legacy_v1 else value
        except RepairApplicationError:
            raise
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError) as exc:
            raise RepairApplicationError(
                "REPAIR_ARTIFACT_RECOVERY_FAILED",
                "Completed repair artifact cannot be loaded",
            ) from exc

    def _start_invocation(
        self, context, *, role: LlmRole, task_type: LlmTaskType, schema_name: str, schema
    ) -> dict[str, object]:
        base_invocation_id = _invocation_key(str(context["attempt_id"]), role)
        invocation_id = _context_invocation_key(context, role)
        now = self._now()
        prompt_version = self._prompt_version(schema_name, task_type)
        schema_version = get_settings().llm_schema_registry_version
        request_checksum = self._logical_request_checksum(
            context["segments"], schema_name, prompt_version, schema_version
        )
        input_hashes = [
            str(context["failure_evidence_checksum"]),
            str(context["context_pack_checksum"]),
            "schema:"
            + hashlib.sha256(json.dumps(schema.model_json_schema(), sort_keys=True).encode()).hexdigest(),
        ]
        if context.get("retry_of_invocation_key"):
            input_hashes.extend([
                "retry_of:" + str(context["retry_of_invocation_key"]),
                "semantic_retry_count:" + str(context.get("semantic_retry_count") or 0),
            ])
        try:
            with self._scope() as session:
                if not context.get("semantic_retry_count"):
                    prior_retry_id = f"{base_invocation_id}:semantic-retry-1"
                    prior_retry = session.scalar(
                        select(LlmInvocationModel).where(
                            LlmInvocationModel.run_id == context["run_id"],
                            LlmInvocationModel.idempotency_key == prior_retry_id,
                        )
                    )
                    if prior_retry is not None:
                        if prior_retry.status == "failed":
                            raise RepairApplicationError(
                                "REPAIR_SEMANTIC_RETRY_EXHAUSTED",
                                "Repair semantic correction retry has already failed",
                            )
                        if prior_retry.status == "in_progress" and prior_retry.transport_started:
                            raise RepairApplicationError(
                                "REPAIR_INVOCATION_UNCERTAIN",
                                "Repair semantic correction retry outcome is uncertain",
                            )
                        context.update(
                            invocation_key=prior_retry_id,
                            semantic_retry_count=1,
                            retry_of_invocation_key=base_invocation_id,
                        )
                        context["segments"].append(_SEMANTIC_RETRY_FEEDBACK)
                        invocation_id = prior_retry_id
                        input_hashes.extend([
                            "retry_of:" + base_invocation_id,
                            "semantic_retry_count:1",
                        ])
                existing = session.scalar(
                    select(LlmInvocationModel).where(
                        LlmInvocationModel.run_id == context["run_id"],
                        LlmInvocationModel.idempotency_key == invocation_id,
                    )
                )
                if (
                    existing is not None
                    and existing.status == "failed"
                    and existing.request_checksum != request_checksum
                    and not context.get("semantic_retry_count")
                ):
                    invocation_id = (
                        f"{base_invocation_id}:prompt-revision-"
                        f"{hashlib.sha256(prompt_version.encode()).hexdigest()[:12]}"
                    )
                    context["retry_of_invocation_key"] = base_invocation_id
                    input_hashes.extend([
                        "retry_of:" + base_invocation_id,
                        "prompt_revision:" + prompt_version,
                    ])
                    existing = session.scalar(
                        select(LlmInvocationModel).where(
                            LlmInvocationModel.run_id == context["run_id"],
                            LlmInvocationModel.idempotency_key == invocation_id,
                        )
                    )
                context["invocation_key"] = invocation_id
                if existing is None:
                    session.add(LlmInvocationModel(
                        id=invocation_id,
                        run_id=context["run_id"],
                        stage_id=context["stage_id"],
                        idempotency_key=invocation_id,
                        request_checksum=request_checksum,
                        input_hashes=input_hashes,
                        correlation_id=invocation_id,
                        actor="transformer",
                        role=role.value,
                        task_type=task_type.value,
                        provider="azure_openai",
                        deployment_alias="azure-openai",
                        prompt_version=prompt_version,
                        schema_version=schema_version,
                        pricing_version=get_settings().llm_pricing_version,
                        stage="repair",
                        redacted_summary=None,
                        status="in_progress",
                        failure_code=None,
                        artifact_ids=[],
                        artifact_checksums={},
                        state_version=1,
                        event_sequence=0,
                        retries=int(context.get("semantic_retry_count") or 0),
                        transport_started=False,
                        started_at=now,
                        completed_at=None,
                        created_at=now,
                    ))
                    context.update(
                        request_checksum=request_checksum,
                        prompt_version=prompt_version,
                        schema_version=schema_version,
                        invocation_id=invocation_id,
                        invocation_state_version=1,
                    )
                    context["authority_snapshot"] = self._authority_snapshot(context)
                    return context
                legacy_v1 = existing.schema_version == "schema-registry-v1" and existing.prompt_version in {
                    "prompt-repair-proposer-v1", "prompt-repair-reviewer-v1",
                    "repair-proposer-v1", "repair-reviewer-v1",
                }
                if existing.request_checksum != request_checksum and not (
                    existing.status == "failed" and legacy_v1
                ):
                    raise RepairApplicationError(
                        "REPAIR_INVOCATION_PAYLOAD_MISMATCH",
                        "Repair invocation key has a different logical request",
                    )
                if existing.status == "completed":
                    context.update(
                        request_checksum=request_checksum,
                        prompt_version=prompt_version,
                        schema_version=schema_version,
                        invocation_id=existing.id,
                        invocation_state_version=existing.state_version,
                    )
                    context["authority_snapshot"] = self._authority_snapshot(context)
                    recovered = self._recover_completed(
                        context,
                        role=role.value.removeprefix("repair_"),
                        schema_name=schema_name,
                        task_type=task_type,
                        schema=schema,
                    )
                    if recovered is None:
                        raise RepairApplicationError("REPAIR_INVOCATION_UNCERTAIN", "Completed replay could not be verified")
                    context["_recovered_result"] = recovered
                    return context
                if existing.status == "in_progress" and existing.transport_started:
                    raise RepairApplicationError(
                        "REPAIR_INVOCATION_UNCERTAIN",
                        "Repair LLM invocation outcome is uncertain",
                    )
                if existing.status not in {"failed", "in_progress"}:
                    raise RepairApplicationError("REPAIR_INVOCATION_INVALID", "Repair invocation state is invalid")
                prior_state_version = existing.state_version
                changed = session.execute(
                    update(LlmInvocationModel)
                    .where(
                        LlmInvocationModel.run_id == context["run_id"],
                        LlmInvocationModel.idempotency_key == invocation_id,
                        LlmInvocationModel.state_version == prior_state_version,
                        (
                            (LlmInvocationModel.status == "failed")
                            | (
                                (LlmInvocationModel.status == "in_progress")
                                & LlmInvocationModel.transport_started.is_not(True)
                            )
                        ),
                    )
                    .values(
                        request_checksum=request_checksum,
                        input_hashes=input_hashes,
                        prompt_version=prompt_version,
                        schema_version=schema_version,
                        status="in_progress",
                        transport_started=False,
                        completed_at=None,
                        state_version=prior_state_version + 1,
                    )
                )
                if changed.rowcount != 1:
                    raise RepairApplicationError("REPAIR_INVOCATION_UNCERTAIN", "Repair invocation ownership was lost")
                new_state_version = session.scalar(
                    select(LlmInvocationModel.state_version).where(
                        LlmInvocationModel.run_id == context["run_id"],
                        LlmInvocationModel.idempotency_key == invocation_id,
                    )
                )
                context.update(
                    request_checksum=request_checksum,
                    prompt_version=prompt_version,
                    schema_version=schema_version,
                    invocation_id=existing.id,
                    invocation_state_version=new_state_version,
                )
                context["authority_snapshot"] = self._authority_snapshot(context)
                return context
        except IntegrityError:
            with self._scope() as session:
                existing = (
                    session.query(LlmInvocationModel)
                    .filter_by(run_id=context["run_id"], idempotency_key=invocation_id)
                    .one_or_none()
                )
                if (
                    existing is not None
                    and existing.status == "failed"
                    and existing.request_checksum != request_checksum
                    and not context.get("semantic_retry_count")
                ):
                    invocation_id = (
                        f"{base_invocation_id}:prompt-revision-"
                        f"{hashlib.sha256(prompt_version.encode()).hexdigest()[:12]}"
                    )
                    context["retry_of_invocation_key"] = base_invocation_id
                    input_hashes.extend([
                        "retry_of:" + base_invocation_id,
                        "prompt_revision:" + prompt_version,
                    ])
                    existing = session.scalar(
                        select(LlmInvocationModel).where(
                            LlmInvocationModel.run_id == context["run_id"],
                            LlmInvocationModel.idempotency_key == invocation_id,
                        )
                    )
                context["invocation_key"] = invocation_id
                if existing is None:
                    raise
                if existing.status == "in_progress" and existing.transport_started:
                    raise RepairApplicationError("REPAIR_INVOCATION_UNCERTAIN", "Repair LLM invocation outcome is uncertain")
                legacy_v1 = existing.schema_version == "schema-registry-v1" and existing.prompt_version in {
                    "prompt-repair-proposer-v1", "prompt-repair-reviewer-v1",
                    "repair-proposer-v1", "repair-reviewer-v1",
                }
                if existing.request_checksum != request_checksum and not (
                    existing.status == "failed" and legacy_v1
                ):
                    raise RepairApplicationError(
                        "REPAIR_INVOCATION_PAYLOAD_MISMATCH",
                        "Repair invocation key has a different logical request",
                    )
                if existing.status == "completed":
                    context.update(
                        request_checksum=request_checksum,
                        prompt_version=prompt_version,
                        schema_version=schema_version,
                        invocation_id=existing.id,
                        invocation_state_version=existing.state_version,
                    )
                    context["authority_snapshot"] = self._authority_snapshot(context)
                    recovered = self._recover_completed(
                        context,
                        role=role.value.removeprefix("repair_"),
                        schema_name=schema_name,
                        task_type=task_type,
                        schema=schema,
                    )
                    if recovered is None:
                        raise RepairApplicationError("REPAIR_INVOCATION_UNCERTAIN", "Completed replay could not be verified")
                    context["_recovered_result"] = recovered
                    return context
                changed = session.execute(
                    update(LlmInvocationModel)
                    .where(
                        LlmInvocationModel.run_id == context["run_id"],
                        LlmInvocationModel.idempotency_key == invocation_id,
                        LlmInvocationModel.state_version == existing.state_version,
                        (LlmInvocationModel.status == "failed")
                        | (
                            (LlmInvocationModel.status == "in_progress")
                            & LlmInvocationModel.transport_started.is_not(True)
                        ),
                    )
                    .values(
                        request_checksum=request_checksum,
                        status="in_progress",
                        transport_started=False,
                        prompt_version=prompt_version,
                        schema_version=schema_version,
                        input_hashes=input_hashes,
                        state_version=existing.state_version + 1,
                    )
                )
                if changed.rowcount != 1:
                    raise RepairApplicationError("REPAIR_INVOCATION_UNCERTAIN", "Repair invocation ownership was lost")
                verified = session.scalar(
                    select(LlmInvocationModel).where(
                        LlmInvocationModel.run_id == context["run_id"],
                        LlmInvocationModel.idempotency_key == invocation_id,
                    )
                )
                if (
                    verified is None
                    or verified.request_checksum != request_checksum
                    or verified.status != "in_progress"
                    or verified.transport_started
                    or verified.state_version != existing.state_version + 1
                ):
                    raise RepairApplicationError("REPAIR_INVOCATION_UNCERTAIN", "Repair invocation ownership could not be verified")
                context.update(
                    request_checksum=request_checksum,
                    prompt_version=prompt_version,
                    schema_version=schema_version,
                    invocation_id=existing.id,
                    invocation_state_version=verified.state_version,
                )
                context["authority_snapshot"] = self._authority_snapshot(context)
                return context

    def _mark_transport_started(self, context, role: LlmRole) -> None:
        with self._scope() as session:
            invocation = session.scalar(
                select(LlmInvocationModel).where(
                    LlmInvocationModel.run_id == context["run_id"],
                    LlmInvocationModel.idempotency_key == _context_invocation_key(context, role),
                    LlmInvocationModel.status == "in_progress",
                    LlmInvocationModel.state_version == context.get("invocation_state_version"),
                    LlmInvocationModel.transport_started.is_not(True),
                )
            )
            if invocation is None:
                raise RepairApplicationError("REPAIR_INVOCATION_UNCERTAIN", "Repair invocation ownership was lost")
            invocation.transport_started = True
            invocation.state_version += 1
            context["invocation_state_version"] = invocation.state_version
            context["invocation_owner_state"] = {
                "run_id": context["run_id"],
                "idempotency_key": invocation.idempotency_key,
                "invocation_id": invocation.id,
                "state_version": invocation.state_version,
            }

    def _persist_failure(
        self,
        context,
        role,
        error: RepairApplicationError,
        *,
        failure_stage_override=None,
        response=None,
        rejected_candidate=None,
    ) -> None:
        kind = "propose-error" if role == LlmRole.REPAIR_PROPOSER else "review-error"
        cause = error.__cause__ if isinstance(error.__cause__, AzureGatewayError) else None
        request_id = getattr(error, "provider_request_id", None)
        if not request_id and response is not None:
            request_id = response.provider_request_id
        transport_started = bool(getattr(cause, "transport_started", False) or response is not None)
        response_received = bool(getattr(cause, "response_received", False) or response is not None)
        retries = (getattr(cause, "retry_count", None) or 0) + (
            response.usage.retry_count if response is not None else 0
        )
        stored = self._write(
            context,
            kind,
            {
                "code": error.code,
                "message": error.message,
                "retryable": getattr(error, "retryable", False),
                "failure_stage": failure_stage_override
                or getattr(error, "failure_stage", None)
                or "local",
                "provider_status": getattr(error, "provider_status", None),
                "provider_request_id": request_id,
                "failure_subtype": getattr(error, "failure_subtype", None),
                "provider_http_status": getattr(cause, "provider_status", None),
                "provider_error_code": getattr(cause, "provider_code", None),
                "sanitized_provider_message": _bounded_text(getattr(cause, "provider_message", None)),
                "response_received": response_received,
                "transport_started": transport_started,
                "response_sha256": getattr(cause, "response_sha256", None),
                "response_bytes": getattr(cause, "response_bytes", None),
                "response_kind": getattr(cause, "response_kind", None)
                or ("json" if response is not None else None),
                "retries": retries,
            },
        )
        rejected_stored = None
        if rejected_candidate is not None and role == LlmRole.REPAIR_PROPOSER:
            parsed_candidate = RepairProposalCandidate.model_validate(rejected_candidate).model_dump(mode="json")
            rejected_stored = self._write(
                context,
                "rejected-proposer-candidate",
                {
                    "attempt_id": context["attempt_id"],
                    "candidate": parsed_candidate,
                    "prompt_version": context.get("prompt_version"),
                    "schema_version": context.get("schema_version"),
                    "candidate_checksum": self._request_checksum(parsed_candidate),
                    "context_checksum": context.get("context_pack_checksum"),
                    "semantic_failure_code": error.code,
                    "semantic_failure_message": _bounded_text(error.message, 512),
                    "provider_request_id": _bounded_text(request_id, 256),
                },
            )
        now = self._now()
        with self._scope() as session:
            invocation = session.scalar(
                select(LlmInvocationModel).where(
                    LlmInvocationModel.run_id == context["run_id"],
                    LlmInvocationModel.idempotency_key == _context_invocation_key(context, role),
                )
            )
            if invocation is None:
                self._remove_uncommitted_artifact(stored)
                if rejected_stored is not None:
                    self._remove_uncommitted_artifact(rejected_stored)
                return
            expected_state = context.get("invocation_state_version")
            if expected_state is None or invocation.state_version != expected_state or invocation.status != "in_progress":
                self._remove_uncommitted_artifact(stored)
                if rejected_stored is not None:
                    self._remove_uncommitted_artifact(rejected_stored)
                return
            artifact_ids = list(dict.fromkeys([*(invocation.artifact_ids or []), stored.ref.artifact_id]))
            artifact_checksums = {**(invocation.artifact_checksums or {}), stored.ref.artifact_id: stored.ref.checksum}
            if rejected_stored is not None:
                artifact_ids.append(rejected_stored.ref.artifact_id)
                artifact_checksums[rejected_stored.ref.artifact_id] = rejected_stored.ref.checksum
            changed = session.execute(
                update(LlmInvocationModel)
                .where(
                    LlmInvocationModel.run_id == context["run_id"],
                    LlmInvocationModel.idempotency_key == invocation.idempotency_key,
                    LlmInvocationModel.state_version == expected_state,
                    LlmInvocationModel.status == "in_progress",
                )
                .values(
                    status=("in_progress" if transport_started and not response_received else "failed"),
                    artifact_ids=artifact_ids, artifact_checksums=artifact_checksums,
                    failure_code=error.code,
                    failure_stage=failure_stage_override or getattr(error, "failure_stage", None) or "local",
                    failure_subtype=getattr(error, "failure_subtype", None),
                    provider_http_status=getattr(cause, "provider_status", None),
                    provider_error_code=getattr(cause, "provider_code", None),
                    sanitized_provider_message=_bounded_text(getattr(cause, "provider_message", None)),
                    provider_request_id=invocation.provider_request_id or request_id,
                    response_received=response_received, response_content_type=getattr(cause, "response_content_type", None),
                    response_bytes=getattr(cause, "response_bytes", None), response_sha256=getattr(cause, "response_sha256", None),
                    response_kind=getattr(cause, "response_kind", None) or ("json" if response is not None else None),
                    transport_started=transport_started, retryable=getattr(error, "retryable", None),
                    retries=invocation.retries + retries,
                    transport_exception_type=type(error.__cause__).__name__ if error.__cause__ else None,
                    completed_at=None if transport_started and not response_received else now,
                    state_version=expected_state + 1,
                )
            )
            if changed.rowcount != 1:
                self._remove_uncommitted_artifact(stored)
                if rejected_stored is not None:
                    self._remove_uncommitted_artifact(rejected_stored)
                return
            self._register_artifact_metadata(session, context, stored)
            if rejected_stored is not None:
                self._register_artifact_metadata(session, context, rejected_stored)
            return transport_started and not response_received
    def _register_artifact_metadata(self, session, context, stored) -> None:
        session.add(
            ArtifactMetadataModel(
                id="metadata-" + stored.ref.artifact_id,
                run_id=context["run_id"],
                stage_id=context["stage_id"],
                artifact_type=stored.ref.artifact_type.value,
                relative_path=stored.ref.relative_path,
                checksum=stored.ref.checksum,
                created_at=stored.ref.created_at,
                finalized_at=stored.ref.created_at,
                immutable=True,
            )
        )

    @staticmethod
    def _request_checksum(value: object) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _revision_event_key(idempotency_key: str, *, reject: bool = False) -> str:
        prefix = "repair-reject:" if reject else "repair-revision:"
        return prefix + hashlib.sha256(idempotency_key.encode()).hexdigest()

    def _revision_event(self, session, continuation, idempotency_key: str, *, reject=False):
        if continuation is None:
            return None
        key = f"{continuation.id}:{self._revision_event_key(idempotency_key, reject=reject)}"
        return session.scalar(
            select(WorkflowEventModel).where(
                WorkflowEventModel.run_id == continuation.run_id,
                WorkflowEventModel.idempotency_key == key,
            )
        )

    @staticmethod
    def _revision_result(session, event) -> dict[str, object]:
        child_id = str((event.payload or {}).get("child_attempt_id") or "")
        child = session.get(RepairAttemptModel, child_id)
        if child is None:
            raise RepairApplicationError(
                "REPAIR_REVISION_REPLAY_INVALID", "Revision replay child is missing"
            )
        return {
            "attempt_id": child.id,
            "status": child.status,
            "idempotent_replay": True,
        }

    def _revision_replay(
        self, attempt_id: str, idempotency_key: str, request_checksum: str
    ) -> dict[str, object] | None:
        with self._scope() as session:
            attempt = session.get(RepairAttemptModel, attempt_id)
            if attempt is None:
                raise RepairApplicationError(
                    "REPAIR_ATTEMPT_NOT_FOUND", "Repair attempt is missing"
                )
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == attempt.run_id,
                )
            )
            event = self._revision_event(session, continuation, idempotency_key)
            if event is None:
                return None
            if (event.payload or {}).get("request_checksum") != request_checksum:
                raise RepairApplicationError(
                    "IDEMPOTENCY_PAYLOAD_MISMATCH", "Revision key has a different payload"
                )
            return self._revision_result(session, event)

    def _write_revision_context(
        self,
        context: dict[str, object],
        *,
        child_id: str,
        payload: dict[str, object],
        instruction: str,
    ) -> StoredArtifact:
        root = Path(str(context["artifact_root"]))
        self._last_artifact_root = root
        return LocalFilesystemArtifactStore(root.parent, fixed_run_root=root).write_text_artifact(
            str(context["run_id"]),
            f"05_repairs/attempt-{child_id}/revision-context.json",
            json.dumps(payload, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=str(context["stage_id"]),
            attempt_id=child_id,
            created_by="repair-human-revision",
            created_at=self._now(),
            input_hashes={
                "proposal": str(context["proposal_checksum"]),
                "review": str(context["review_checksum"]),
                "instruction": self._request_checksum(instruction),
            },
            policy_version="repair-human-revision-v1",
        )

    def _write_safe_diff(
        self,
        context: dict[str, object],
        proposal: dict[str, object],
        proposal_checksum: str,
    ) -> StoredArtifact:
        root = Path(str(context["artifact_root"]))
        self._last_artifact_root = root
        content = self._render_safe_diff(proposal, Path(str(context["workspace_path"])))
        return LocalFilesystemArtifactStore(root.parent, fixed_run_root=root).write_text_artifact(
            str(context["run_id"]),
            f"05_repairs/attempt-{context['attempt_id']}/candidate.diff",
            content,
            ArtifactType.DIFF,
            stage_id=str(context["stage_id"]),
            attempt_id=str(context["attempt_id"]),
            created_by="repair-proposer-safe-diff",
            created_at=self._now(),
            input_hashes={"proposal": proposal_checksum},
            policy_version="repair-safe-diff-v1",
        )

    @staticmethod
    def _render_safe_diff(proposal: dict[str, object], workspace: Path) -> str:
        if proposal["proposal_format"] == "unified_diff":
            return str(proposal["unified_diff"])
        rendered: list[str] = []
        for operation in proposal["operations"]:
            path = str(operation["path"])
            action = str(operation["operation"])
            if action == "dependency_transition":
                rendered.append(_render_dependency_transition_intent(operation))
                continue
            target = workspace / path
            if action == "create_text_file":
                before = ""
            else:
                with target.open("r", encoding="utf-8", newline="") as handle:
                    before = handle.read()
            if action == "create_text_file":
                after = str(operation["content"])
            elif action == "delete_text_file":
                after = ""
            else:
                after = replace_text_once(
                    before,
                    str(operation["old_text"]),
                    str(operation["new_text"]),
                )
            diff = "".join(
                unified_diff(
                    before.splitlines(keepends=True),
                    after.splitlines(keepends=True),
                    fromfile="/dev/null" if action == "create_text_file" else f"a/{path}",
                    tofile="/dev/null" if action == "delete_text_file" else f"b/{path}",
                    lineterm="\n",
                )
            )
            if not diff and action in {"create_text_file", "delete_text_file"}:
                diff = (
                    f"--- {'/dev/null' if action == 'create_text_file' else f'a/{path}'}\n"
                    f"+++ {'/dev/null' if action == 'delete_text_file' else f'b/{path}'}\n"
                )
            if diff:
                rendered.append(diff if diff.endswith("\n") else diff + "\n")
        return "".join(rendered)

    def _write(self, context, kind, value):
        root = Path(str(context["artifact_root"]))
        self._last_artifact_root = root
        return LocalFilesystemArtifactStore(root.parent, fixed_run_root=root).write_text_artifact(
            str(context["run_id"]),
            f"05_repairs/attempt-{context['attempt_id']}/{kind}.json",
            json.dumps(value, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=str(context["stage_id"]),
            attempt_id=str(context["attempt_id"]),
            created_by=f"repair-{kind}",
            created_at=self._now(),
            input_hashes={
                "failure": str(context["failure_evidence_checksum"]),
                "context": str(context["context_pack_checksum"]),
            },
            policy_version=f"repair-{kind}-v1",
        )

    def _persist_call(
        self,
        context,
        response,
        stored,
        *,
        role,
        schema_name,
        summary,
        additional_stored=(),
    ):
        with self._scope() as session:
            attempt = session.scalar(
                select(RepairAttemptModel).where(
                    RepairAttemptModel.id == context["attempt_id"],
                    RepairAttemptModel.run_id == context["run_id"],
                    RepairAttemptModel.stage_id == context["stage_id"],
                )
            )
            run = session.scalar(select(MigrationRunModel).where(MigrationRunModel.id == context["run_id"]))
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == context["run_id"],
                    StageWorkspaceBindingModel.stage_id == context["stage_id"],
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == context["run_id"],
                    TransformationContinuationModel.current_stage_id == context["stage_id"],
                )
            )
            stage_plan = session.get(StageExecutionPlanModel, context.get("stage_plan_id")) if context.get("stage_plan_id") else None
            if attempt is None or run is None or binding is None:
                raise RepairApplicationError("REPAIR_PROPOSAL_STALE" if role == "proposer" else "REPAIR_REVIEW_STALE", "Repair authority is missing")
            proposal_metadata = (
                session.get(ArtifactMetadataModel, "metadata-" + str(attempt.proposal_artifact_id))
                if attempt.proposal_artifact_id
                else None
            )
            try:
                live_fingerprint = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
            except OSError as error:
                raise RepairApplicationError("REPAIR_WORKSPACE_STALE", "Repair workspace is unavailable") from error
            current = {
                "run_id": run.id,
                "run_state_version": run.state_version,
                "continuation_state_version": continuation.state_version if continuation else None,
                "stage_id": attempt.stage_id,
                "stage_plan_id": stage_plan.id if stage_plan else (continuation.stage_plan_id if continuation else None),
                "stage_plan_checksum": stage_plan.checksum if stage_plan else (continuation.stage_plan_checksum if continuation else None),
                "stage_plan_state_version": stage_plan.state_version if stage_plan else None,
                "attempt_id": attempt.id,
                "attempt_number": attempt.attempt_number,
                "attempt_status": attempt.status,
                "parent_attempt_id": attempt.parent_attempt_id,
                "parent_review_artifact_id": attempt.parent_review_artifact_id,
                "parent_review_checksum": attempt.parent_review_checksum,
                "failure_evidence_artifact_id": attempt.failure_evidence_artifact_id,
                "failure_evidence_checksum": attempt.failure_evidence_checksum,
                "context_pack_artifact_id": attempt.context_pack_artifact_id,
                "context_pack_checksum": attempt.context_pack_checksum,
                "proposal_artifact_id": attempt.proposal_artifact_id,
                "proposal_checksum": proposal_metadata.checksum if proposal_metadata else attempt.proposal_checksum,
                "proposer_invocation_id": attempt.proposer_invocation_id,
                "reviewer_invocation_id": attempt.reviewer_invocation_id,
                "workspace_binding_id": binding.id,
                "workspace_path": binding.workspace_path,
                "workspace_stored_fingerprint": binding.workspace_fingerprint,
                "workspace_live_fingerprint": live_fingerprint,
                "invocation_id": context.get("invocation_id"),
                "invocation_state_version": context.get("invocation_state_version"),
                "request_checksum": context.get("request_checksum"),
                "prompt_version": context.get("prompt_version"),
                "schema_version": context.get("schema_version"),
            }
            if self._backend_authority_snapshot(current) != self._backend_authority_snapshot(context["authority_snapshot"]):
                raise RepairApplicationError(
                    "REPAIR_REVIEW_STALE" if role == "reviewer" else "REPAIR_PROPOSAL_STALE",
                    "Repair authority changed before success persistence",
                )
            expected_run_version = context["authority_snapshot"]["run_state_version"]
            run_claim = session.execute(
                update(MigrationRunModel)
                .where(MigrationRunModel.id == context["run_id"], MigrationRunModel.state_version == expected_run_version)
                .values(state_version=MigrationRunModel.state_version + 1, updated_at=self._now())
            )
            if run_claim.rowcount != 1:
                raise RepairApplicationError(
                    "REPAIR_REVIEW_STALE" if role == "reviewer" else "REPAIR_PROPOSAL_STALE",
                    "Run state changed before success persistence",
                )
            invocation_id = _context_invocation_key(context, role)
            continuation_claim = None
            if continuation is not None:
                continuation_claim = session.execute(update(TransformationContinuationModel).where(
                    TransformationContinuationModel.id == continuation.id,
                    TransformationContinuationModel.run_id == context["run_id"],
                    TransformationContinuationModel.current_stage_id == context["stage_id"],
                    TransformationContinuationModel.state_version == context["authority_snapshot"]["continuation_state_version"],
                ).values(state_version=TransformationContinuationModel.state_version + 1, updated_at=self._now()))
                if continuation_claim.rowcount != 1:
                    raise RepairApplicationError("REPAIR_REVIEW_STALE" if role == "reviewer" else "REPAIR_PROPOSAL_STALE", "Continuation changed before success persistence")
            if stage_plan is not None:
                plan_claim = session.execute(update(StageExecutionPlanModel).where(
                    StageExecutionPlanModel.id == stage_plan.id,
                    StageExecutionPlanModel.run_id == context["run_id"],
                    StageExecutionPlanModel.stage_id == context["stage_id"],
                    StageExecutionPlanModel.checksum == context["authority_snapshot"]["stage_plan_checksum"],
                    StageExecutionPlanModel.state_version == context["authority_snapshot"]["stage_plan_state_version"],
                ).values(updated_at=self._now()))
                if plan_claim.rowcount != 1:
                    raise RepairApplicationError("REPAIR_REVIEW_STALE" if role == "reviewer" else "REPAIR_PROPOSAL_STALE", "Stage plan changed before success persistence")
            binding_claim = session.execute(update(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.id == binding.id,
                StageWorkspaceBindingModel.run_id == context["run_id"],
                StageWorkspaceBindingModel.stage_id == context["stage_id"],
                StageWorkspaceBindingModel.active.is_(True),
                StageWorkspaceBindingModel.workspace_path == context["authority_snapshot"]["workspace_path"],
                StageWorkspaceBindingModel.workspace_fingerprint == context["authority_snapshot"]["workspace_stored_fingerprint"],
            ).values(last_verified_fingerprint=live_fingerprint, last_verified_at=self._now()))
            if binding_claim.rowcount != 1:
                raise RepairApplicationError("REPAIR_WORKSPACE_STALE", "Workspace binding changed before success persistence")
            attempt_predicates = [
                RepairAttemptModel.id == attempt.id,
                RepairAttemptModel.run_id == context["run_id"],
                RepairAttemptModel.stage_id == context["stage_id"],
                RepairAttemptModel.attempt_number == context["authority_snapshot"]["attempt_number"],
                RepairAttemptModel.status == context["authority_snapshot"]["attempt_status"],
                RepairAttemptModel.context_pack_artifact_id == context["authority_snapshot"]["context_pack_artifact_id"],
                RepairAttemptModel.context_pack_checksum == context["authority_snapshot"]["context_pack_checksum"],
                RepairAttemptModel.failure_evidence_artifact_id == context["authority_snapshot"]["failure_evidence_artifact_id"],
                RepairAttemptModel.failure_evidence_checksum == context["authority_snapshot"]["failure_evidence_checksum"],
                RepairAttemptModel.proposer_invocation_id.is_(None) if context["authority_snapshot"]["proposer_invocation_id"] is None else RepairAttemptModel.proposer_invocation_id == context["authority_snapshot"]["proposer_invocation_id"],
                RepairAttemptModel.reviewer_invocation_id.is_(None) if context["authority_snapshot"]["reviewer_invocation_id"] is None else RepairAttemptModel.reviewer_invocation_id == context["authority_snapshot"]["reviewer_invocation_id"],
            ]
            old_parent = context["authority_snapshot"]["parent_attempt_id"]
            old_proposal = context["authority_snapshot"]["proposal_checksum"]
            attempt_predicates += [RepairAttemptModel.parent_attempt_id.is_(None) if old_parent is None else RepairAttemptModel.parent_attempt_id == old_parent, RepairAttemptModel.proposal_checksum.is_(None) if old_proposal is None else RepairAttemptModel.proposal_checksum == old_proposal]
            attempt_values = {"updated_at": self._now()}
            if role == "proposer":
                attempt_values.update(proposal_artifact_id=stored.ref.artifact_id, proposal_checksum=stored.ref.checksum, proposer_invocation_id=invocation_id, status="proposed")
            else:
                attempt_values.update(review_artifact_id=stored.ref.artifact_id, review_checksum=stored.ref.checksum, reviewer_invocation_id=invocation_id, status=("review_accepted" if summary["decision"] == "accept" else summary["decision"]))
            attempt_claim = session.execute(update(RepairAttemptModel).where(*attempt_predicates).values(**attempt_values))
            if attempt_claim.rowcount != 1:
                raise RepairApplicationError("REPAIR_REVIEW_STALE" if role == "reviewer" else "REPAIR_PROPOSAL_STALE", "Repair attempt changed before success persistence")
            invocation_id = _context_invocation_key(context, role)
            now = self._now()
            invocation = session.scalar(
                select(LlmInvocationModel).where(
                    LlmInvocationModel.run_id == attempt.run_id,
                    LlmInvocationModel.idempotency_key == invocation_id,
                )
            )
            if invocation is None:
                raise RepairApplicationError("REPAIR_INVOCATION_UNCERTAIN", "Repair invocation is missing")
            if invocation.status != "in_progress" or not invocation.transport_started:
                raise RepairApplicationError("REPAIR_INVOCATION_UNCERTAIN", "Repair invocation is not owned")
            if (
                invocation.request_checksum != context.get("request_checksum")
                or invocation.prompt_version != context.get("prompt_version")
                or invocation.schema_version != context.get("schema_version")
            ):
                raise RepairApplicationError("REPAIR_INVOCATION_UNCERTAIN", "Repair invocation provenance changed")
            invocation_claim = session.execute(update(LlmInvocationModel).where(
                LlmInvocationModel.id == invocation.id,
                LlmInvocationModel.run_id == context["run_id"],
                LlmInvocationModel.idempotency_key == invocation_id,
                LlmInvocationModel.state_version == context["invocation_state_version"],
                LlmInvocationModel.status == "in_progress",
                LlmInvocationModel.transport_started.is_(True),
            ).values(state_version=LlmInvocationModel.state_version))
            if invocation_claim.rowcount != 1:
                raise RepairApplicationError("REPAIR_INVOCATION_UNCERTAIN", "Repair invocation ownership changed")
            invocation.status = "completed"
            invocation.failure_code = None
            invocation.role = "repair_proposer" if role == "proposer" else "repair_reviewer"
            invocation.task_type = "repair_diagnosis" if role == "proposer" else "repair_review"
            invocation.deployment_alias = response.model_deployment_alias
            invocation.prompt_version = context["prompt_version"]
            invocation.schema_version = context["schema_version"]
            invocation.pricing_version = response.pricing_version or get_settings().llm_pricing_version
            invocation.redacted_summary = json.dumps(summary, sort_keys=True)
            persisted_artifacts = (stored, *additional_stored)
            invocation.artifact_ids = list(
                dict.fromkeys(
                    [
                        *(invocation.artifact_ids or []),
                        *(item.ref.artifact_id for item in persisted_artifacts),
                    ]
                )
            )
            invocation.artifact_checksums = {
                **(invocation.artifact_checksums or {}),
                **{
                    item.ref.artifact_id: item.ref.checksum
                    for item in persisted_artifacts
                },
            }
            invocation.retries = (invocation.retries or 0) + (response.usage.retry_count or 0)
            if response.provider_request_id and not invocation.provider_request_id:
                invocation.provider_request_id = response.provider_request_id
            invocation.transport_started = True
            invocation.response_received = True
            invocation.completed_at = now
            invocation.state_version += 1
            started_at = invocation.started_at
            if started_at is not None and started_at.tzinfo is not None:
                invocation.latency_ms = max(0, int((now - started_at).total_seconds() * 1000))
            session.add(
                UsageCostRecordModel(
                    id="usage-cost-" + uuid4().hex[:12],
                    invocation_id=invocation.id,
                    run_id=attempt.run_id,
                    stage_id=attempt.stage_id,
                    pricing_version=invocation.pricing_version,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    total_tokens=response.usage.total_tokens,
                    input_price_per_million=response.usage.input_price_per_million,
                    output_price_per_million=response.usage.output_price_per_million,
                    input_cost_usd=response.usage.input_cost_usd,
                    output_cost_usd=response.usage.output_cost_usd,
                    total_cost_usd=response.usage.total_cost_usd,
                    created_at=now,
                )
            )
            self._register_artifact_metadata(session, context, stored)
            for item in additional_stored:
                self._register_artifact_metadata(session, context, item)
            if role == "proposer":
                attempt.proposal_artifact_id = stored.ref.artifact_id
                attempt.proposal_checksum = stored.ref.checksum
                attempt.proposer_invocation_id = invocation.id
                attempt.status = "proposed"
            else:
                attempt.review_artifact_id = stored.ref.artifact_id
                attempt.review_checksum = stored.ref.checksum
                attempt.reviewer_invocation_id = invocation.id
                attempt.status = (
                    "review_accepted" if summary["decision"] == "accept" else summary["decision"]
                )
            attempt.updated_at = now

    def _remove_uncommitted_artifact(self, stored) -> None:
        # The store has already versioned this path; remove only this newly-created pair.
        run_root = Path(str(self._last_artifact_root)) if hasattr(self, "_last_artifact_root") else None
        if run_root is None:
            return
        for path in (run_root / stored.ref.relative_path, run_root / f"{stored.ref.relative_path}.meta.json"):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def _safe_path(self, value: str, workspace: Path) -> str:
        if "\\" in value:
            raise RepairApplicationError("REPAIR_PATH_INVALID", "Repair paths must use '/'")
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or ".." in path.parts
            or any(
                part in self.forbidden_parts
                or part.startswith(".env")
                or part.endswith((".pem", ".key", ".pfx"))
                for part in path.parts
            )
        ):
            raise RepairApplicationError("REPAIR_PATH_FORBIDDEN", "Repair path is outside policy")
        normalized = path.as_posix()
        try:
            (workspace / normalized).resolve(strict=False).relative_to(workspace)
        except ValueError as error:
            raise RepairApplicationError("REPAIR_PATH_ESCAPE", "Repair path escapes workspace") from error
        return normalized
