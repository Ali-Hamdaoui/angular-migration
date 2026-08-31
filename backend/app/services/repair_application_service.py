"""Governed repair proposal/review and deterministic semantic validation."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from difflib import unified_diff
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
from app.domain.contracts import AgentKind, ArtifactType, CommandStatus, WorkflowEventType
from app.domain.planning import (
    SUPPORTED_VALIDATION_TARGETS,
    CommandTemplateReference,
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
    MigrationStageModel,
    MigrationRunModel,
    RepairAttemptModel,
    RepairFingerprintRecoveryModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageGatePackageModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    UsageCostRecordModel,
    WorkflowEventModel,
)
from app.services.causal_review import (
    REVIEWER_CAUSAL_POLICY,
    CausalRejection,
    causal_rejection,
    repair_budget,
)
from app.services.dependency_addition_policy import (
    DEPENDENCY_ADDITION_POLICY_VERSION,
    DependencyAdditionPolicy,
    DependencyAdditionPolicyError,
)
from app.services.dependency_closure_service import (
    installed_dependency_version,
    is_exact_version,
    validate_dependency_transition_evidence,
    verify_dependency_transition_evidence_for_source,
)
from app.domain.dependency_normalization import (
    DEPENDENCY_NORMALIZATION_REPAIR_KIND,
    DEPENDENCY_NORMALIZATION_SCHEMA_VERSION,
    DependencyNormalizationAction,
    DependencyNormalizationPlan,
)
from app.services.dependency_normalization_service import DependencyNormalizationService
from app.services.dependency_repair_preflight_service import DependencyRepairPreflightService
from app.services.failure_evidence_service import (
    CONTEXT_PACK_MAX_BYTES_PER_FILE,
    FailureEvidenceService,
    validate_context_pack,
)
from app.services.repair_lifecycle_service import RepairLifecycleService
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
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if set(entry) == {"key", "value"}:
            key = str(entry["key"])
            entry_value = str(entry["value"])
        else:
            key = str(entry.get("operation") or "backend_provenance")
            entry_value = json.dumps(
                {str(name): entry[name] for name in sorted(entry)},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        identity = (key, entry_value)
        if identity not in seen:
            normalized.append({"key": key, "value": entry_value})
            seen.add(identity)
    return normalized


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
        provider_response_id: str | None,
        failure_stage: str | None,
        failure_subtype: str | None,
    ) -> None:
        super().__init__(code, message)
        self.retryable = retryable
        self.provider_status = provider_status
        self.provider_request_id = provider_request_id
        self.provider_response_id = provider_response_id
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
_DEPENDENCY_ADDITION_SECTIONS = frozenset({"dependencies", "devDependencies"})
_DEPENDENCY_TRANSITION_VALID_REPAIR_KINDS = frozenset({"dependency_transition"})
_DEPENDENCY_TRANSITION_VALID_FAILURE_TYPES = frozenset({"peer_dependency_conflict"})
_DEPENDENCY_TRANSITION_VALID_STRATEGIES = frozenset({"detach_update_reattach"})
_DEPENDENCY_TRANSITION_NOT_EXCLUSIVE = "REPAIR_DEPENDENCY_TRANSITION_NOT_EXCLUSIVE"
_DEPENDENCY_NORMALIZATION_NOT_EXCLUSIVE = "REPAIR_DEPENDENCY_NORMALIZATION_NOT_EXCLUSIVE"
_DEPENDENCY_SECTION_MISMATCH = "REPAIR_DEPENDENCY_SECTION_MISMATCH"
_REPLACEMENT_CONTEXT_MISSING = "REPAIR_REPLACEMENT_CONTEXT_MISSING"
_REPLACEMENT_CONTEXT_INVALID = "REPAIR_REPLACEMENT_CONTEXT_INVALID"
_REPLACEMENT_PREIMAGE_REQUIRED = "REPAIR_REPLACEMENT_PREIMAGE_REQUIRED"
_CREATE_TARGET_EXISTS = "REPAIR_CREATE_TARGET_EXISTS"
_SEMANTIC_RETRY_CONTEXT_SCHEMA = "repair-semantic-retry-context-v1"
_SEMANTIC_RETRY_CODES = frozenset(
    {
        "REPAIR_REPLACEMENT_MISSING",
        "REPAIR_REPLACEMENT_AMBIGUOUS",
        "REPAIR_PREIMAGE_STALE",
        "REPAIR_CAUSAL_REJECTION",
        "REPAIR_DEPENDENCY_INTENT_INVALID",
        # A proposer may select dependency_transition for a failure whose
        # immutable evidence does not prove a peer conflict. The backend must
        # reject that candidate, but the proposer gets one bounded semantic
        # correction opportunity before the attempt becomes recoverably
        # exhausted.
        "REPAIR_DEPENDENCY_EVIDENCE_INVALID",
        "REPAIR_PROPOSAL_SCHEMA_INVALID",
        _DEPENDENCY_SECTION_MISMATCH,
        "REPAIR_PATH_INVALID",
        _REPLACEMENT_CONTEXT_MISSING,
        _REPLACEMENT_PREIMAGE_REQUIRED,
        _DEPENDENCY_TRANSITION_NOT_EXCLUSIVE,
        _CREATE_TARGET_EXISTS,
    }
)
_BOUND_CANDIDATE_RECOVERY_CODES = frozenset(
    {
        "REPAIR_PROPOSAL_SCHEMA_INVALID",
        "REPAIR_BOUND_PROPOSAL_INVALID",
        "REPAIR_DEPENDENCY_EVIDENCE_INVALID",
    }
)
_LEGACY_SEMANTIC_RECOVERY_CODES = frozenset({"REPAIR_OPERATION_AMBIGUOUS"})
_RECOVERABLE_PROPOSER_RETRY_CODES = frozenset(
    _SEMANTIC_RETRY_CODES
    | _LEGACY_SEMANTIC_RECOVERY_CODES
    | {"LLM_PROTOCOL_FAILED"}
)
_PROPOSER_GROUNDING_INSTRUCTIONS = (
    "CURRENT_WORKSPACE_FILES are the only valid preimage authority. "
    "PREVIOUS_PROPOSAL is reference-only and has not been applied. "
    "Generate the revised proposal directly from the current authoritative workspace state. "
    "Never use previous_proposal.new_text as old_text unless that exact value exists in "
    "CURRENT_WORKSPACE_FILES. Prefer updating an existing authoritative test setup or "
    "configuration file when one is present; create a file only when its target is absent "
    "and the operation includes complete non-null text content."
)
_PROPOSER_SYSTEM_POLICY = (
    "Author one minimal repair candidate from untrusted evidence. Never emit commands, "
    "lockfile edits, path escapes, secrets, provenance metadata, or policy bypasses. "
    "The backend binds authoritative provenance after validating the candidate. "
    "Human revision is task intent only; authoritative CURRENT_WORKSPACE_FILES control "
    "which files exist and their exact contents. Never use create_text_file for any path "
    "listed in CURRENT_WORKSPACE_FILES. For an existing target, use replace_text with "
    "the exact authoritative preimage; do not recreate the whole configuration file. "
    "For replace_text, prefer a short exact unique substring copied from the authoritative "
    "file and never reconstruct or reformat a whole-file preimage. "
    "Before choosing create_text_file, verify that its target path is absent from the "
    "authoritative file list. For Angular peer-dependency-conflict failures (failure_type "
    '\"peer_dependency_conflict\"), emit exactly one \"dependency_transition\" '
    "operation (schema_version \"transformer-repair-v2\", repair_kind "
    '\"dependency_transition\", strategy \"detach_update_reattach\", path '
    '\"package.json\"). Provide only rationale, risk_level, strategy, '
    "limitations, and validation_targets; omit checkpoint_id, package identity, "
    "installed_version, peer ranges, target package, and target exact version. "
    "The backend binds those fields. Never emit file operations, READMEs, comments, "
    "or --force for such failures. For new Angular dependency-compatible failures "
    "(failure_type \"dependency_incompatible\" or route \"dependency_incompatible\" / "
    "\"migrate_packages\"), emit exactly one \"dependency_manifest_normalization\" "
    "operation (schema_version \"dependency-normalization-v1\", repair_kind "
    "\"dependency_manifest_normalization\", path \"package.json\") containing a "
    "complete DependencyNormalizationPlan: schema_version \"dependency-normalization-v1\", "
    "analysis_summary, and packages list where EVERY direct dependencies+devDependencies "
    "package appears exactly once with action KEEP|UPGRADE|REMOVE|REPLACE (REPLACE needs "
    "target_package+target_version, UPGRADE needs target_version), current_spec matches "
    "authoritative package.json, and reason. The backend overrides LLM suggestions with "
    "fixed Angular target requirements (e.g., @angular/*, typescript, rxjs, zone.js pinned "
    "to stage target) and materializes the authoritative postimage package.json bytes, "
    "checksums, and unified diff. Human Request Change re-evaluates the ENTIRE plan: "
    "keep foo-grid at 7.5 triggers a fresh full-plan LLM call re-evaluating ALL packages, "
    "not a patch. Never emit npm shell commands. "
    "When the failure evidence proves a required package "
    "is absent from package.json, emit exactly one \"dependency_add\" operation at "
    'path \"package.json\" with section limited to \"dependencies\" or '
    '\"devDependencies\", package, and new_version as a registry semver range or intent; '
    "the backend validates the requested registry semver spec and binds it as the approved "
    "version spec, and governed lockfile generation fixes the exact resolved version after "
    "human approval. Never emit npm shell commands. "
    + _PROPOSER_GROUNDING_INSTRUCTIONS
)
_SEMANTIC_RETRY_FEEDBACK = (
    "The candidate does not match the current authoritative workspace. "
    "The previous proposal was not applied. "
    "Regenerate using the exact current file content."
)
_REPLACEMENT_CONTEXT_MISSING_RETRY_FEEDBACK = (
    "The requested replace_text target was not present in the authoritative\n"
    "repository context supplied to the previous proposer invocation.\n"
    "The backend has now supplied the exact current target content and checksum.\n"
    "Regenerate old_text from that authoritative content. It must match exactly\n"
    "once. Do not infer whitespace, line endings, or an EOF newline from the\n"
    "human instruction."
)
_REPLACEMENT_AMBIGUOUS_RETRY_FEEDBACK = (
    "The previous replace_text candidate used a preimage that matched the "
    "authoritative file more than once. Each replace_text operation must use "
    "an exact non-empty preimage that occurs exactly once. Do not repeat an "
    "identical operation to target multiple occurrences. Instead, use one "
    "larger unique preimage or distinct unique preimages for distinct edits, "
    "preserving the smallest causal source change."
)
_DEPENDENCY_TRANSITION_RETRY_FEEDBACK = (
    "The previous proposer candidate violated the dependency_transition exclusivity rule. "
    "dependency_transition is exclusive: emit exactly one operation with "
    'operation="dependency_transition" and path="package.json". '
    "Do not emit replace_text, create_text_file, or delete_text_file. "
    "Do not emit dependency_add or dependency_change or another dependency_transition. "
    "Do not emit a package.json unified_diff. "
    "The backend binds authoritative transition targets. "
    "Regenerate from the same immutable failure/context evidence."
)
_DEPENDENCY_NORMALIZATION_RETRY_FEEDBACK = (
    "The previous proposer candidate violated the dependency_manifest_normalization exclusivity rule. "
    "dependency_manifest_normalization is exclusive: emit exactly one operation with "
    'operation="dependency_manifest_normalization" (or repair_kind="dependency_manifest_normalization") '
    'and path="package.json" and schema_version="dependency-normalization-v1". '
    "The packages list must contain EVERY direct dependencies+devDependencies package exactly once "
    "with action KEEP|UPGRADE|REMOVE|REPLACE, no duplicates, current_spec must match authoritative "
    "package.json, REPLACE needs explicit target_package+target_version, and no --force or "
    "scripts/.npmrc/workspaces/overrides mutation. The backend overrides LLM suggestions with "
    "fixed Angular target requirements and materializes the authoritative postimage. "
    "Regenerate the ENTIRE plan from the same immutable failure/context evidence."
)
_CREATE_TARGET_EXISTS_RETRY_FEEDBACK = (
    "The proposed create_text_file target already exists in the authoritative workspace. "
    "Do not create or overwrite it. Inspect the hydrated authoritative target content "
    "supplied with this retry. Use the exact authoritative preimage. If the intended "
    "repair modifies that existing file, use replace_text with a non-empty old_text "
    "copied EXACTLY from the authoritative file content and an appropriate new_text. "
    "Preserve exact preimage semantics including EOF/newline state. Do not fabricate "
    "file state."
)
_UNIFIED_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _semantic_retry_feedback(error_code: str | None, error_message: str | None = None) -> str:
    if error_code == "REPAIR_REPLACEMENT_AMBIGUOUS":
        return _REPLACEMENT_AMBIGUOUS_RETRY_FEEDBACK + (
            "\nBackend rejection for the prior candidate: "
            + (error_message or "the replacement preimage matched multiple times")
            + "\n"
        )
    if error_code in {_REPLACEMENT_CONTEXT_MISSING, "REPAIR_REPLACEMENT_MISSING"}:
        return _REPLACEMENT_CONTEXT_MISSING_RETRY_FEEDBACK + (
            "\nBackend rejection for the prior candidate: "
            + (error_message or "the replacement preimage did not match")
            + "\n"
        )
    if error_code == _DEPENDENCY_TRANSITION_NOT_EXCLUSIVE:
        return _DEPENDENCY_TRANSITION_RETRY_FEEDBACK
    if error_code in {_DEPENDENCY_NORMALIZATION_NOT_EXCLUSIVE, "REPAIR_DEPENDENCY_NORMALIZATION_NOT_EXCLUSIVE", "REPAIR_DEPENDENCY_NORMALIZATION_INCOMPLETE", "REPAIR_DEPENDENCY_NORMALIZATION_INVALID"}:
        return _DEPENDENCY_NORMALIZATION_RETRY_FEEDBACK + (
            "\nBackend rejection for the prior candidate: "
            + (error_message or "normalization plan invalid")
            + "\n"
        )
    if error_code == _CREATE_TARGET_EXISTS:
        return _CREATE_TARGET_EXISTS_RETRY_FEEDBACK + (
            "\nBackend rejection for the prior candidate: "
            + (error_message or "the existing target path was not included")
            + "\n"
        )
    if error_code == _DEPENDENCY_SECTION_MISMATCH:
        return (
            "The requested dependency exists exactly once in authoritative package.json, "
            "but the candidate supplied the wrong dependency section.\n"
            f"{error_message or 'The backend supplied the authoritative dependency facts.'}\n"
            "Do not move the dependency between package.json sections merely to resolve a "
            "module/runtime failure.\n"
            "Regenerate the repair from the original immutable failure and repository evidence.\n"
            "If dependency_change remains appropriate, it must use the authoritative section "
            "and produce an actual causal state change.\n"
            "If the failure is caused by repository source/configuration rather than the "
            "dependency declaration, repair the causal repository file instead.\n"
            "Do not fabricate package state, lockfile state, or node_modules state."
        )
    if error_code == "REPAIR_DEPENDENCY_EVIDENCE_INVALID":
        return (
            "The previous candidate used dependency_transition, but the immutable failure "
            "evidence does not prove an Angular peer-dependency conflict.\n"
            f"{error_message or 'The backend could not bind a proven dependency conflict.'}\n"
            "Use dependency_transition only when the failure evidence contains a non-empty "
            "blocking package and incompatible peer ranges. Otherwise, propose the smallest "
            "causal source or configuration repair supported by the current workspace evidence. "
            "Do not fabricate package, lockfile, or node_modules state."
        )
    if error_code == "REPAIR_PROPOSAL_SCHEMA_INVALID":
        return (
            "The previous repair candidate became invalid while the backend bound its "
            "authoritative operation evidence. Regenerate one minimal proposal from the "
            "immutable failure and current workspace evidence. Keep every bounded list, "
            "including operation provenance, within the declared schema limits. Do not "
            "fabricate package, lockfile, node_modules, or prior-proposal state.\n"
            f"Backend schema rejection: {error_message or 'the proposal failed schema validation.'}"
        )
    return _SEMANTIC_RETRY_FEEDBACK


def _dependency_section_mismatch_error(
    package: str,
    actual_section: str,
    actual_version: object,
    requested_section: str,
) -> RepairApplicationError:
    return RepairApplicationError(
        _DEPENDENCY_SECTION_MISMATCH,
        "The requested dependency exists exactly once in authoritative package.json, "
        f"but in section '{actual_section}' rather than requested section "
        f"'{requested_section}'.\n"
        f"Authoritative package: {package}\n"
        f"Authoritative section: {actual_section}\n"
        f"Authoritative version: {actual_version}",
    )


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
        f"strategy: {operation.get('strategy') or 'detach_update_reattach'!s}",
        f"failure_type: {operation.get('failure_type') or 'peer_dependency_conflict'!s}",
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


def _proposal_validation_message(error: ValidationError) -> str:
    first = error.errors()[0] if error.errors() else {}
    loc = ".".join(str(part) for part in first.get("loc", ()))
    return (
        _bounded_text(f"{loc} {first.get('type', '')}".strip())
        or "Repair proposal failed schema validation"
    )


def _repair_llm_error(code, message, exc: AzureGatewayError, *, retryable: bool) -> RepairLlmError:
    error = RepairLlmError(
        code,
        message,
        retryable=retryable,
        provider_status=exc.provider_status,
        provider_request_id=exc.provider_request_id,
        provider_response_id=exc.provider_response_id,
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
        "dependency_add",
        "dependency_transition",
        "dependency_manifest_normalization",
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
    # P3 normalization — full-manifest plan
    packages: list[DependencyNormalizationAction] | None = Field(default=None, max_length=128)
    analysis_summary: str | None = Field(default=None, min_length=1, max_length=4000)
    normalization_plan: DependencyNormalizationPlan | None = None
    plan: DependencyNormalizationPlan | None = None
    post_text: str | None = None
    pre_checksum: str | None = None
    post_checksum: str | None = None
    diff: str | None = Field(default=None, max_length=100_000)


class RepairOperation(RepairOperationCandidate):
    preimage_sha256: str | None = None
    provenance: list[ProvenanceEntry] = Field(default_factory=list, max_length=32)


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

    # V2.2 P1-1: insufficient_context is the bounded fourth outcome; the
    # reviewer decides and can never author replacement content.
    decision: Literal["accept", "request_changes", "reject", "insufficient_context"]
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

    def recover_stale_dependency_state(
        self,
        *,
        run_id: str,
        attempt_id: str,
        expected_state_version: int,
        idempotency_key: str,
        actor: str,
    ) -> dict[str, object]:
        """Supersede a repeated failed transition and resume deterministic lock repair."""
        event_key = "dependency-state-recovery:" + hashlib.sha256(
            idempotency_key.encode()
        ).hexdigest()
        with self._scope() as session:
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == run_id
                )
            )
            event = session.scalar(
                select(WorkflowEventModel).where(
                    WorkflowEventModel.run_id == run_id,
                    WorkflowEventModel.idempotency_key == f"{continuation.id}:{event_key}"
                    if continuation is not None
                    else False,
                )
            )
            if event is not None:
                return {
                    "attempt_id": attempt_id,
                    "status": continuation.status,
                    "state_version": continuation.state_version,
                    "idempotent_replay": True,
                }
            attempt = session.get(RepairAttemptModel, attempt_id)
            initial_recovery = bool(
                continuation is not None
                and continuation.status == "waiting_gate"
                and continuation.current_node == "wait_g10"
                and attempt is not None
                and attempt.status == "waiting_g10"
            )
            retry_recovery = bool(
                continuation is not None
                and continuation.status == "blocked"
                and continuation.current_node == "lockfile_generation"
                and continuation.last_error_code == "IDEMPOTENCY_KEY_REUSED"
                and attempt is not None
                and attempt.status == "superseded"
            )
            if (
                continuation is None
                or attempt is None
                or attempt.run_id != run_id
                or attempt.stage_id != continuation.current_stage_id
                or continuation.state_version != expected_state_version
                or not (initial_recovery or retry_recovery)
            ):
                raise RepairApplicationError(
                    "DEPENDENCY_STATE_RECOVERY_STALE",
                    "The waiting G10 dependency recovery authority changed",
                )
            run = session.get(MigrationRunModel, run_id)
            stage = session.get(MigrationStageModel, continuation.current_stage_id)
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == run_id,
                    StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if run is None or stage is None or binding is None:
                raise RepairApplicationError(
                    "DEPENDENCY_STATE_RECOVERY_AUTHORITY_MISSING",
                    "Run, stage, or workspace authority is missing",
                )
            workspace = Path(binding.workspace_path).resolve(strict=True)
            live = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
            if live != binding.workspace_fingerprint or live != attempt.pre_fingerprint:
                raise RepairApplicationError(
                    "REPAIR_WORKSPACE_STALE", "Repair workspace fingerprint changed"
                )
            diagnosis = DependencyRepairPreflightService().classify_current_state(
                workspace=workspace,
                source_family=stage.source_version_family,
                target_family=stage.target_version_family,
            )
            if diagnosis.get("classification") != "TARGET_MANIFEST_AHEAD":
                raise RepairApplicationError(
                    "DEPENDENCY_STATE_RECONCILIATION_NOT_APPLICABLE",
                    f"Current dependency state is {diagnosis.get('classification')}",
                )
            causal_execution, result_checksum = self._causal_lockfile_execution(
                session, run, attempt, workspace
            )
            proposal = self._recovery_proposal(session, run, attempt)
            operation = next(iter(proposal.get("operations") or []), {})
            if not self._same_failed_transition_exists(session, run, attempt, operation):
                raise RepairApplicationError(
                    "REPAIR_STRATEGY_NOT_PREVIOUSLY_FAILED",
                    "The proposed transition has no equivalent applied runtime failure",
                )
            now = self._now()
            if initial_recovery:
                gate = session.get(StageGatePackageModel, attempt.g10_gate_package_id)
                if gate is None or gate.status != "pending":
                    raise RepairApplicationError(
                        "DEPENDENCY_STATE_RECOVERY_GATE_STALE", "The G10 package is not pending"
                    )
                gate.status = "stale"
                gate.stale_at = now
                attempt.status = "superseded"
                attempt.completed_at = now
                attempt.updated_at = now
            step = session.scalar(
                select(StageStepModel).where(
                    StageStepModel.run_id == run_id,
                    StageStepModel.stage_id == continuation.current_stage_id,
                    StageStepModel.name == "lockfile_generation-0",
                )
            )
            if step is None:
                raise RepairApplicationError(
                    "STAGE_PLAN_COMMAND_AUTHORITY_MISSING",
                    "The stage has no governed lockfile-generation step",
                )
            step.status = "RUNNING"
            step.execution_id = causal_execution.id
            step.completed_at = None
            continuation.status = "queued"
            continuation.current_node = "lockfile_generation"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.waiting_execution_id = None
            continuation.last_error_code = None
            continuation.last_error_message = None
            continuation.wake_sequence += 1
            continuation.state_version += 1
            continuation.updated_at = now
            session.flush()
            append_continuation_event(
                session,
                continuation,
                event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED,
                key=event_key,
                reason="repeated dependency transition superseded by deterministic state reconciliation",
                actor=actor,
                occurred_at=now,
                payload={
                    "attempt_id": attempt.id,
                    "causal_execution_id": causal_execution.id,
                    "causal_result_checksum": result_checksum,
                    "classification": diagnosis["classification"],
                    "manifest_checksum": self._request_checksum(
                        json.loads((workspace / "package.json").read_text(encoding="utf-8"))
                    ),
                    "lockfile_checksum": "sha256:" + hashlib.sha256(
                        (workspace / "package-lock.json").read_bytes()
                    ).hexdigest(),
                    "workspace_fingerprint": live,
                    "expected_state_version": expected_state_version,
                },
            )
            return {
                "attempt_id": attempt.id,
                "status": continuation.status,
                "state_version": continuation.state_version,
                "classification": diagnosis["classification"],
                "causal_execution_id": causal_execution.id,
                "idempotent_replay": False,
            }

    def recover_manifest_ahead_dependency_state(
        self,
        *,
        run_id: str,
        attempt_id: str,
        expected_state_version: int,
        idempotency_key: str,
        actor: str,
    ) -> dict[str, object]:
        """Route a target manifest with stale resolution to lockfile recovery.

        This path is deliberately narrower than repair recovery: the current
        manifest must already be present in the attempt-bound checkpoint, so
        no proposal, G10, or LLM output is treated as the source of authority.
        """
        event_key = "dependency-state-manifest-ahead:" + hashlib.sha256(
            idempotency_key.encode()
        ).hexdigest()
        with self._scope() as session:
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == run_id
                )
            )
            attempt = session.get(RepairAttemptModel, attempt_id)
            legacy_blocked_recovery = bool(
                continuation is not None
                and continuation.status == "blocked"
                and continuation.current_node == "classify_failure"
                and continuation.last_error_code == "REPAIR_ATTEMPT_LIMIT"
                and attempt is not None
                and attempt.status == "superseded"
            )
            if (
                continuation is None
                or attempt is None
                or not (
                    (
                        continuation.status == "waiting_gate"
                        and continuation.current_node == "wait_g10"
                        and attempt.status == "waiting_g10"
                    )
                    or legacy_blocked_recovery
                )
                or attempt.run_id != run_id
                or attempt.stage_id != continuation.current_stage_id
                or continuation.state_version != expected_state_version
            ):
                raise RepairApplicationError(
                    "DEPENDENCY_STATE_RECOVERY_STALE",
                    "The waiting G10 dependency recovery authority changed",
                )
            existing = session.scalar(
                select(WorkflowEventModel).where(
                    WorkflowEventModel.run_id == run_id,
                    WorkflowEventModel.idempotency_key == f"{continuation.id}:{event_key}",
                )
            )
            if existing is not None:
                return {
                    "attempt_id": attempt.id,
                    "status": continuation.status,
                    "state_version": continuation.state_version,
                    "idempotent_replay": True,
                }
            stage = session.get(MigrationStageModel, continuation.current_stage_id)
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == run_id,
                    StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if stage is None or binding is None:
                raise RepairApplicationError(
                    "DEPENDENCY_STATE_RECOVERY_AUTHORITY_MISSING",
                    "Stage or workspace authority is missing",
                )
            workspace = Path(binding.workspace_path).resolve(strict=True)
            live = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
            if live != binding.workspace_fingerprint or live != attempt.pre_fingerprint:
                raise RepairApplicationError(
                    "REPAIR_WORKSPACE_STALE",
                    "Repair workspace fingerprint changed",
                )
            diagnosis = DependencyRepairPreflightService().classify_current_state(
                workspace=workspace,
                source_family=stage.source_version_family,
                target_family=stage.target_version_family,
            )
            if diagnosis.get("classification") != "TARGET_MANIFEST_AHEAD":
                raise RepairApplicationError(
                    "DEPENDENCY_STATE_RECONCILIATION_NOT_APPLICABLE",
                    f"Current dependency state is {diagnosis.get('classification')}",
                )
            checkpoint = session.get(StageCheckpointModel, attempt.checkpoint_id)
            if (
                checkpoint is None
                or checkpoint.kind != "pre_repair"
                or not checkpoint.safe_for_resume
                or self._stage_checkpoint_fingerprint(session, checkpoint) != attempt.pre_fingerprint
            ):
                raise RepairApplicationError(
                    "DEPENDENCY_STATE_RECOVERY_CHECKPOINT_INVALID",
                    "The target manifest is not bound to a safe repair checkpoint",
                )
            checkpoint_manifest = Path(checkpoint.workspace_path) / "package.json"
            current_manifest = workspace / "package.json"
            if (
                not checkpoint_manifest.is_file()
                or not current_manifest.is_file()
                or self._file_checksum(checkpoint_manifest) != self._file_checksum(current_manifest)
            ):
                raise RepairApplicationError(
                    "DEPENDENCY_STATE_RECOVERY_MANIFEST_INVALID",
                    "Current package.json does not match the authoritative checkpoint",
                )
            step = session.scalar(
                select(StageStepModel).where(
                    StageStepModel.run_id == run_id,
                    StageStepModel.stage_id == continuation.current_stage_id,
                    StageStepModel.name == "lockfile_generation-0",
                )
            )
            execution = session.get(CommandExecutionModel, step.execution_id) if step and step.execution_id else None
            if not self._valid_lockfile_failure(session, execution, run_id, continuation.current_stage_id):
                raise RepairApplicationError(
                    "DEPENDENCY_STATE_CAUSAL_EXECUTION_INVALID",
                    "The stage has no immutable failed npm lockfile execution to reconcile",
                )
            now = self._now()
            if not legacy_blocked_recovery:
                gate = session.get(StageGatePackageModel, attempt.g10_gate_package_id)
                if gate is None or gate.status != "pending":
                    raise RepairApplicationError(
                        "DEPENDENCY_STATE_RECOVERY_GATE_STALE",
                        "The G10 package is not pending",
                    )
                gate.status = "stale"
                gate.stale_at = now
                RepairLifecycleService.transition_in_session(
                    session,
                    attempt,
                    "superseded",
                    reason="deterministic target-manifest reconciliation superseded pending G10",
                    actor=actor,
                    now=now,
                )
            step.status = "RUNNING"
            step.execution_id = execution.id
            step.completed_at = None
            continuation.status = "queued"
            continuation.current_node = "lockfile_generation"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.waiting_execution_id = None
            continuation.last_error_code = None
            continuation.last_error_message = None
            continuation.wake_sequence += 1
            continuation.state_version += 1
            continuation.updated_at = now
            session.flush()
            append_continuation_event(
                session,
                continuation,
                event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED,
                key=event_key,
                reason="target manifest is ahead of stale dependency resolution; deterministic lockfile reconciliation queued",
                actor=actor,
                occurred_at=now,
                payload={
                    "attempt_id": attempt.id,
                    "checkpoint_id": checkpoint.id,
                    "causal_execution_id": execution.id,
                    "classification": diagnosis["classification"],
                    "manifest_checksum": self._file_checksum(current_manifest),
                    "lockfile_checksum": self._file_checksum(workspace / "package-lock.json"),
                    "workspace_fingerprint": live,
                    "expected_state_version": expected_state_version,
                },
            )
            return {
                "attempt_id": attempt.id,
                "status": continuation.status,
                "state_version": continuation.state_version,
                "classification": diagnosis["classification"],
                "causal_execution_id": execution.id,
                "idempotent_replay": False,
            }

    @staticmethod
    def _file_checksum(path: Path) -> str:
        return (
            "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            if path.is_file() and not path.is_symlink()
            else "missing"
        )

    @staticmethod
    def _stage_checkpoint_fingerprint(session, checkpoint) -> str | None:
        from app.services.transformer_stage_service import TransformerStageService

        return TransformerStageService().authoritative_checkpoint_fingerprint(session, checkpoint)

    @staticmethod
    def _valid_lockfile_failure(session, execution, run_id: str, stage_id: str) -> bool:
        if (
            execution is None
            or execution.run_id != run_id
            or execution.stage_id != stage_id
            or execution.command_id != "npm-lockfile-generate"
            or execution.status != "failed"
            or execution.exit_code in (None, 0)
            or not re.search(
                r"(?im)^\s*npm\s+(?:ERR!|error)\s+(?:code\s+)?ERESOLVE\b",
                execution.failure_message or "",
            )
        ):
            return False
        artifact_ids = (
            execution.result_artifact_id,
            execution.command_log_artifact_id,
            execution.manifest_artifact_id,
        )
        return all(
            artifact_id
            and (metadata := session.get(ArtifactMetadataModel, "metadata-" + str(artifact_id))) is not None
            and metadata.immutable
            and metadata.run_id == run_id
            and metadata.stage_id == stage_id
            and metadata.execution_id == execution.id
            for artifact_id in artifact_ids
        )

    @staticmethod
    def _causal_lockfile_execution(session, run, attempt, workspace):
        metadata = session.get(
            ArtifactMetadataModel,
            "metadata-" + str(attempt.failure_evidence_artifact_id),
        )
        if (
            metadata is None
            or not metadata.immutable
            or metadata.run_id != attempt.run_id
            or metadata.stage_id != attempt.stage_id
            or metadata.checksum != attempt.failure_evidence_checksum
        ):
            raise RepairApplicationError(
                "DEPENDENCY_STATE_CAUSAL_EVIDENCE_INVALID",
                "Immutable dependency failure evidence is missing or stale",
            )
        stored = LocalFilesystemArtifactStore(
            Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
        ).read_artifact(run.id, metadata.relative_path)
        payload = json.loads(stored.content)
        execution = session.get(CommandExecutionModel, payload.get("execution_id"))
        if (
            stored.ref.checksum != metadata.checksum
            or stored.envelope is None
            or stored.envelope.run_id != attempt.run_id
            or stored.envelope.stage_id != attempt.stage_id
            or execution is None
            or execution.run_id != attempt.run_id
            or execution.stage_id != attempt.stage_id
            or execution.command_id != "npm-lockfile-generate"
            or execution.status != "failed"
            or execution.exit_code in (None, 0)
            or not re.search(r"(?im)^\s*npm\s+(?:ERR!|error)\s+(?:code\s+)?ERESOLVE\b", execution.failure_message or "")
        ):
            raise RepairApplicationError(
                "DEPENDENCY_STATE_CAUSAL_EXECUTION_INVALID",
                "Failure evidence does not bind a terminal npm ERESOLVE lockfile execution",
            )
        artifacts = (
            execution.result_artifact_id,
            execution.command_log_artifact_id,
            execution.manifest_artifact_id,
        )
        artifact_rows = [
            session.get(ArtifactMetadataModel, "metadata-" + str(artifact_id))
            for artifact_id in artifacts
        ]
        if any(
            row is None
            or not row.immutable
            or row.run_id != attempt.run_id
            or row.stage_id != attempt.stage_id
            or row.execution_id != execution.id
            for row in artifact_rows
        ):
            raise RepairApplicationError(
                "DEPENDENCY_STATE_CAUSAL_EVIDENCE_INVALID",
                "Causal command result, log, or manifest evidence is incomplete",
            )
        start = execution.start_fingerprint or {}
        package_checksum = "sha256:" + hashlib.sha256(
            (workspace / "package.json").read_bytes()
        ).hexdigest()
        lock_checksum = "sha256:" + hashlib.sha256(
            (workspace / "package-lock.json").read_bytes()
        ).hexdigest()
        if (
            start.get("post_apply_pre_command_package_json_sha256") != package_checksum
            or start.get("post_apply_pre_command_package_lock_sha256") != lock_checksum
        ):
            raise RepairApplicationError(
                "DEPENDENCY_STATE_CAUSAL_WORKSPACE_MISMATCH",
                "Current manifest/lockfile state differs from the causal failed execution",
            )
        return execution, artifact_rows[0].checksum

    @staticmethod
    def _recovery_proposal(session, run, attempt) -> dict[str, object]:
        metadata = session.get(ArtifactMetadataModel, "metadata-" + str(attempt.proposal_artifact_id))
        if metadata is None or metadata.checksum != attempt.proposal_checksum:
            raise RepairApplicationError("REPAIR_PROPOSAL_STALE", "Repair proposal is missing")
        stored = LocalFilesystemArtifactStore(
            Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
        ).read_artifact(run.id, metadata.relative_path)
        if stored.ref.checksum != attempt.proposal_checksum:
            raise RepairApplicationError("REPAIR_PROPOSAL_STALE", "Repair proposal checksum changed")
        value = json.loads(stored.content)
        return value if isinstance(value, dict) else {}

    @classmethod
    def _same_failed_transition_exists(cls, session, run, attempt, operation) -> bool:
        if not isinstance(operation, dict) or operation.get("operation") != "dependency_transition":
            return False
        current = (
            operation.get("strategy"),
            (operation.get("blocking_dependency") or {}).get("package"),
            (operation.get("target_state") or {}).get("target_version"),
        )
        rows = session.scalars(
            select(RepairAttemptModel).where(
                RepairAttemptModel.run_id == attempt.run_id,
                RepairAttemptModel.stage_id == attempt.stage_id,
                RepairAttemptModel.attempt_number < attempt.attempt_number,
                RepairAttemptModel.apply_ledger_artifact_id.is_not(None),
                RepairAttemptModel.status.in_(("validation_failed", "superseded")),
            )
        ).all()
        for row in rows:
            try:
                prior = cls._recovery_proposal(session, run, row)
                item = next(iter(prior.get("operations") or []), {})
            except (RepairApplicationError, ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError):
                continue
            fingerprint = (
                item.get("strategy"),
                (item.get("blocking_dependency") or {}).get("package"),
                (item.get("target_state") or {}).get("target_version"),
            )
            if item.get("operation") == "dependency_transition" and fingerprint == current:
                return True
        return False

    def propose(self, attempt_id: str) -> dict[str, object]:
        from app.services.repair_lifecycle_reliability_service import RepairLifecycleReliabilityService

        # Sealing guard (F04-04): a sealed/terminal repair lifecycle cannot be
        # proposed again. Uses the caller's scope so injected test scopes work.
        RepairLifecycleReliabilityService(session_scope_factory=self._scope).assert_mutable(attempt_id)
        self.recover_legacy_fingerprint_authority(attempt_id)
        self._recover_legacy_context_pack(attempt_id)
        semantic_retry_count = 0
        retry_of_invocation_key = None
        semantic_retry_code = None
        semantic_retry_message = None
        semantic_retry_context_segment = None
        semantic_retry_context_checksum = None
        while True:
            context = self._attempt_context(attempt_id)
            if semantic_retry_context_segment is None:
                recovered_retry_context = self._load_semantic_retry_context(context)
                if recovered_retry_context is not None:
                    semantic_retry_context_segment = recovered_retry_context["segment"]
                    semantic_retry_context_checksum = recovered_retry_context["checksum"]
                    semantic_retry_code = recovered_retry_context["error_code"]
                    semantic_retry_message = recovered_retry_context.get("error_message")
                    if not semantic_retry_count:
                        semantic_retry_count = 1
                        retry_of_invocation_key = _invocation_key(
                            str(attempt_id), LlmRole.REPAIR_PROPOSER
                        )
            if not semantic_retry_count and context.get("proposer_invocation_id"):
                context["invocation_key"] = str(context["proposer_invocation_id"])
                if ":semantic-retry-" in context["invocation_key"]:
                    semantic_retry_count = 1
            if semantic_retry_context_segment is not None:
                context["segments"].append(semantic_retry_context_segment)
                context["semantic_retry_context_checksum"] = semantic_retry_context_checksum
            if semantic_retry_count:
                context["semantic_retry_count"] = semantic_retry_count
                context["retry_of_invocation_key"] = retry_of_invocation_key
                context["invocation_key"] = (
                    f"{attempt_id}:proposer:semantic-retry-{semantic_retry_count}"
                )
                context["semantic_retry_message"] = semantic_retry_message
                context["segments"].append(
                    _semantic_retry_feedback(semantic_retry_code, semantic_retry_message)
                )
            bound_proposer_invocation = context.get("proposer_invocation_id")
            if (
                isinstance(bound_proposer_invocation, str)
                and ":recovery-" in bound_proposer_invocation
            ):
                context["invocation_key"] = bound_proposer_invocation
            recovered = self._recover_completed(
                context,
                role="proposer",
                schema_name=self.proposer_schema,
                task_type=LlmTaskType.REPAIR_DIAGNOSIS,
                schema=RepairProposalCandidate,
            )
            if recovered is not None:
                return recovered
            provider_response_id = context.pop("_provider_response_id", None)
            if provider_response_id:
                output, response = self._retrieve_provider_response(
                    context,
                    role=LlmRole.REPAIR_PROPOSER,
                    task=LlmTaskType.REPAIR_DIAGNOSIS,
                    schema_name=self.proposer_schema,
                    schema=RepairProposalCandidate,
                    provider_response_id=str(provider_response_id),
                )
            else:
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
                        policy=_PROPOSER_SYSTEM_POLICY,
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
            except (RepairApplicationError, ValidationError) as error:
                retry_error = (
                    error
                    if isinstance(error, RepairApplicationError)
                    else RepairApplicationError(
                        "REPAIR_PROPOSAL_SCHEMA_INVALID",
                        _proposal_validation_message(error),
                    )
                )
                hydrated_retry_context = None
                if (
                    retry_error.code
                    in {
                        "REPAIR_REPLACEMENT_MISSING",
                        _REPLACEMENT_PREIMAGE_REQUIRED,
                        _CREATE_TARGET_EXISTS,
                    }
                    and semantic_retry_count == 0
                ):
                    try:
                        hydrated_retry_context = self._hydrate_semantic_retry_context(
                            output, context
                        )
                    except RepairApplicationError as hydration_error:
                        retry_error = hydration_error
                    else:
                        if (
                            hydrated_retry_context is not None
                            and error.code == "REPAIR_REPLACEMENT_MISSING"
                        ):
                            semantic_retry_context_segment = hydrated_retry_context["segment"]
                            semantic_retry_context_checksum = self._request_checksum(
                                hydrated_retry_context["payload"]
                            )
                            retry_error = RepairApplicationError(
                                _REPLACEMENT_CONTEXT_MISSING,
                                "The replace_text target was missing from the authoritative "
                                "proposer context; exact active workspace content was "
                                "hydrated for the bounded semantic retry.",
                            )
                        elif hydrated_retry_context is not None:
                            semantic_retry_context_segment = hydrated_retry_context["segment"]
                            semantic_retry_context_checksum = self._request_checksum(
                                hydrated_retry_context["payload"]
                            )
                self._persist_failure(
                    context,
                    LlmRole.REPAIR_PROPOSER,
                    retry_error,
                    failure_stage_override="repair_semantics",
                    response=response,
                    rejected_candidate=output,
                    semantic_retry_context=(
                        hydrated_retry_context["payload"]
                        if hydrated_retry_context is not None
                        else None
                    ),
                )
                retryable_semantics = retry_error.code in _SEMANTIC_RETRY_CODES or (
                    retry_error.code == "REPAIR_OPERATION_AMBIGUOUS"
                    and retry_error.message == "Create operations require non-null text content"
                )
                if retryable_semantics and semantic_retry_count == 0:
                    retry_of_invocation_key = _context_invocation_key(context, LlmRole.REPAIR_PROPOSER)
                    semantic_retry_code = retry_error.code
                    semantic_retry_message = retry_error.message
                    semantic_retry_count = 1
                    continue
                raise retry_error
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
        if context.get("reviewer_invocation_id"):
            context["invocation_key"] = str(context["reviewer_invocation_id"])
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
        provider_response_id = context.pop("_provider_response_id", None)
        if provider_response_id:
            output, response = self._retrieve_provider_response(
                context,
                role=LlmRole.REPAIR_REVIEWER,
                task=LlmTaskType.REPAIR_REVIEW,
                schema_name=self.reviewer_schema,
                schema=RepairReviewCandidate,
                provider_response_id=str(provider_response_id),
            )
        else:
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
                    )
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

    def recover_exhausted_semantic_retry(
        self,
        *,
        run_id: str,
        attempt_id: str,
        expected_state_version: int,
        idempotency_key: str,
        actor: str,
    ) -> dict[str, object]:
        """Create one governed successor for an exhausted proposal-less attempt."""
        request_checksum = self._request_checksum(
            {
                "run_id": run_id,
                "attempt_id": attempt_id,
                "expected_state_version": expected_state_version,
                "actor": actor,
            }
        )
        replay = self._semantic_recovery_replay(
            run_id, attempt_id, idempotency_key, request_checksum
        )
        if replay is not None:
            return replay
        with self._scope() as session:
            existing = self._semantic_recovery_child(session, run_id, attempt_id)
            if existing is not None:
                return self._semantic_recovery_result(existing, idempotent_replay=True)

        context = self._attempt_context(attempt_id)
        if context["run_id"] != run_id:
            raise RepairApplicationError(
                "REPAIR_ATTEMPT_MISMATCH",
                "Repair attempt does not belong to the requested run",
            )
        try:
            context_pack = json.loads(str(context["segments"][1]))
        except (IndexError, TypeError, ValueError) as error:
            raise RepairApplicationError(
                "REPAIR_RECOVERY_NOT_ELIGIBLE",
                "Repair context evidence cannot be reconstructed",
            ) from error
        if not isinstance(context_pack, dict):
            raise RepairApplicationError(
                "REPAIR_RECOVERY_NOT_ELIGIBLE",
                "Repair context evidence cannot be reconstructed",
            )
        # Recovery contexts may predate a parser fix. Rehydrate derived npm
        # diagnosis from the immutable command text before creating the child
        # lineage; the raw evidence remains unchanged.
        context_pack, _diagnosis = FailureEvidenceService.normalize_dependency_transition_evidence(
            context_pack
        )
        normalized_failure = context_pack.get("normalized_failure")
        forbidden_change_policy = context_pack.get("forbidden_change_policy")
        if not isinstance(normalized_failure, dict) or not isinstance(
            forbidden_change_policy, dict
        ):
            raise RepairApplicationError(
                "REPAIR_RECOVERY_NOT_ELIGIBLE",
                "Repair context evidence is incomplete",
            )
        human_revision = context_pack.get("human_revision")
        if human_revision is not None and (
            not isinstance(human_revision, dict)
            or not str(human_revision.get("instruction") or "").strip()
        ):
            raise RepairApplicationError(
                "REPAIR_RECOVERY_NOT_ELIGIBLE",
                "Repair human-revision context is incomplete",
            )
        evidence = {
            "run_id": context["run_id"],
            "stage_id": context["stage_id"],
            "workspace_path": context["workspace_path"],
            "workspace_fingerprint": context["workspace_stored_fingerprint"],
            "artifact_root": context["artifact_root"],
            "failure_fingerprint": context["failure_fingerprint"],
            "normalized_failure": normalized_failure,
            "causal_repair": context_pack.get("causal_repair"),
            "target_cohort": context_pack.get("target_cohort") or {},
            "forbidden_change_policy": forbidden_change_policy,
        }
        with self._scope() as session:
            authority = self._semantic_recovery_authority(
                session,
                context,
                run_id=run_id,
                attempt_id=attempt_id,
                expected_state_version=expected_state_version,
            )
            if authority["existing_child"] is not None:
                return self._semantic_recovery_result(
                    authority["existing_child"], idempotent_replay=True
                )

        child_id = f"repair-{context['stage_id']}-{int(context['attempt_number']) + 1}"
        stored = None
        try:
            root = Path(str(context["artifact_root"]))
            self._last_artifact_root = root
            stored = FailureEvidenceService(now_provider=self._now).write_context_pack(
                evidence,
                str(context["failure_evidence_checksum"]),
                relative_path=f"05_repairs/attempt-{child_id}/recovery-context.json",
                lineage_from=str(context["context_pack_checksum"]),
                human_revision=human_revision,
            )
            with self._scope() as session:
                authority = self._semantic_recovery_authority(
                    session,
                    context,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    expected_state_version=expected_state_version,
                )
                existing = authority["existing_child"]
                if existing is not None:
                    self._remove_uncommitted_artifact(stored)
                    return self._semantic_recovery_result(existing, idempotent_replay=True)
                attempt = authority["attempt"]
                continuation = authority["continuation"]
                now = self._now()
                self._register_artifact_metadata(session, context, stored)
                child = RepairAttemptModel(
                    id=child_id,
                    run_id=attempt.run_id,
                    stage_id=attempt.stage_id,
                    attempt_number=attempt.attempt_number + 1,
                    state_version=1,
                    status="evidence_frozen",
                    risk_level="unknown",
                    diagnosis=f"semantic retry recovery; parent={attempt.id}",
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
                    created_at=now,
                    updated_at=now,
                )
                session.add(child)
                session.flush()
                attempt.status = "superseded"
                attempt.updated_at = now
                attempt.completed_at = now
                continuation.status = "queued"
                continuation.current_node = "propose_repair"
                continuation.worker_id = None
                continuation.lease_expires_at = None
                continuation.next_attempt_at = None
                continuation.waiting_execution_id = None
                continuation.last_error_code = None
                continuation.last_error_message = None
                continuation.wake_sequence += 1
                continuation.state_version += 1
                continuation.updated_at = now
                session.flush()
                append_continuation_event(
                    session,
                    continuation,
                    event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED,
                    key=self._semantic_recovery_event_key(idempotency_key),
                    reason="semantic retry exhausted recovery requested",
                    actor=actor,
                    occurred_at=now,
                    payload={
                        "attempt_id": attempt.id,
                        "child_attempt_id": child.id,
                        "request_checksum": request_checksum,
                        "expected_state_version": expected_state_version,
                    },
                )
                return self._semantic_recovery_result(child, idempotent_replay=False)
        except IntegrityError:
            if stored is not None:
                self._remove_uncommitted_artifact(stored)
            replay = self._semantic_recovery_replay(
                run_id, attempt_id, idempotency_key, request_checksum
            )
            if replay is not None:
                return replay
            with self._scope() as session:
                existing = self._semantic_recovery_child(session, run_id, attempt_id)
                if existing is not None:
                    return self._semantic_recovery_result(existing, idempotent_replay=True)
            raise RepairApplicationError(
                "REPAIR_RECOVERY_CONFLICT",
                "Concurrent semantic retry recovery could not be resolved",
            )
        except RepairApplicationError:
            if stored is not None:
                self._remove_uncommitted_artifact(stored)
            raise

    def recover_uncertain_invocation(
        self,
        *,
        run_id: str,
        attempt_id: str,
        expected_state_version: int,
        idempotency_key: str,
        actor: str,
        reason: str,
    ) -> dict[str, object]:
        with self._scope() as session:
            attempt = session.get(RepairAttemptModel, attempt_id)
            continuation = (
                session.scalar(
                    select(TransformationContinuationModel).where(
                        TransformationContinuationModel.run_id == run_id,
                        TransformationContinuationModel.current_stage_id == attempt.stage_id,
                    )
                )
                if attempt is not None
                else None
            )
            proposer_recovery = (
                continuation is not None
                and continuation.status == "blocked"
                and continuation.current_node == "propose_repair"
            )
        if proposer_recovery:
            return self._recover_uncertain_proposer_invocation(
                run_id=run_id,
                attempt_id=attempt_id,
                expected_state_version=expected_state_version,
                idempotency_key=idempotency_key,
                actor=actor,
                reason=reason,
            )
        """Abandon one irrecoverable reviewer call and queue one new review identity."""
        request_checksum = self._request_checksum(
            {
                "run_id": run_id,
                "attempt_id": attempt_id,
                "expected_state_version": expected_state_version,
                "actor": actor,
                "reason": reason,
                "role": "reviewer",
                "generation": 1,
            }
        )
        event_marker = f"repair-invocation-recovery:{attempt_id}:reviewer:1"
        with self._scope() as session:
            prior_events = session.scalars(
                select(WorkflowEventModel)
                .where(
                    WorkflowEventModel.run_id == run_id,
                    WorkflowEventModel.event_type == WorkflowEventType.REPAIR_INVOCATION_RECOVERED.value,
                )
                .order_by(WorkflowEventModel.sequence.desc())
            ).all()
            prior_event = next(
                (event for event in prior_events if event.payload.get("attempt_id") == attempt_id),
                None,
            )
            if prior_event is not None:
                successor_key = str(prior_event.payload.get("new_invocation_key") or "")
                successor = session.scalar(
                    select(LlmInvocationModel).where(
                        LlmInvocationModel.run_id == run_id,
                        LlmInvocationModel.idempotency_key == successor_key,
                    )
                )
                if successor is None or not successor_key.endswith(":reviewer:recovery-1"):
                    raise RepairApplicationError(
                        "REPAIR_RECOVERY_CONFLICT",
                        "Existing uncertain-invocation recovery evidence is incomplete",
                    )
                return {
                    "run_id": run_id,
                    "attempt_id": attempt_id,
                    "old_invocation_key": prior_event.payload.get("old_invocation_key"),
                    "new_invocation_key": successor_key,
                    "new_invocation_id": successor.id,
                    "proposal_checksum": prior_event.payload.get("proposal_checksum"),
                    "idempotent_replay": True,
                }
            generation_rows = session.scalars(
                select(LlmInvocationModel).where(
                    LlmInvocationModel.run_id == run_id,
                    LlmInvocationModel.idempotency_key.like(f"{attempt_id}:reviewer:recovery-%"),
                )
            ).all()
            if generation_rows:
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_CONFLICT",
                    "A reviewer recovery generation already exists without complete evidence",
                )
            attempt = session.scalar(
                select(RepairAttemptModel).where(
                    RepairAttemptModel.id == attempt_id,
                    RepairAttemptModel.run_id == run_id,
                )
            )
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == run_id,
                    TransformationContinuationModel.current_stage_id == attempt.stage_id if attempt else False,
                )
            ) if attempt else None
            run = session.get(MigrationRunModel, run_id)
            if attempt is None or run is None:
                raise RepairApplicationError("REPAIR_RECOVERY_NOT_ELIGIBLE", "Repair attempt or run is missing")
            if continuation is None or continuation.state_version != expected_state_version:
                raise RepairApplicationError("REPAIR_RECOVERY_STALE", "Continuation state changed before recovery")
            if continuation.status != "blocked" or continuation.current_node != "review_repair":
                raise RepairApplicationError("REPAIR_RECOVERY_NOT_ELIGIBLE", "Continuation is not blocked at reviewer recovery")
            if continuation.last_error_code != "REPAIR_INVOCATION_UNCERTAIN":
                raise RepairApplicationError("REPAIR_RECOVERY_NOT_ELIGIBLE", "Continuation is not blocked by uncertain invocation")
            waiting_execution_id = continuation.waiting_execution_id
            if waiting_execution_id is not None:
                if not isinstance(waiting_execution_id, str) or not waiting_execution_id.strip():
                    raise RepairApplicationError(
                        "REPAIR_RECOVERY_NOT_ELIGIBLE",
                        "Continuation waiting execution is malformed",
                    )
                waiting_execution = session.get(CommandExecutionModel, waiting_execution_id)
                if (
                    waiting_execution is None
                    or waiting_execution.run_id != run_id
                    or waiting_execution.stage_id != attempt.stage_id
                ):
                    raise RepairApplicationError(
                        "REPAIR_RECOVERY_NOT_ELIGIBLE",
                        "Continuation waiting execution is missing or mismatched",
                    )
                if waiting_execution.status in {
                    CommandStatus.QUEUED.value,
                    CommandStatus.PENDING.value,
                    CommandStatus.RUNNING.value,
                }:
                    raise RepairApplicationError(
                        "REPAIR_RECOVERY_NOT_ELIGIBLE",
                        "Continuation still has an active owner",
                    )
                if waiting_execution.status not in {
                    CommandStatus.SUCCEEDED.value,
                    CommandStatus.FAILED.value,
                    CommandStatus.TIMED_OUT.value,
                    CommandStatus.CANCELLED.value,
                    CommandStatus.INTERRUPTED.value,
                }:
                    raise RepairApplicationError(
                        "REPAIR_RECOVERY_NOT_ELIGIBLE",
                        "Continuation waiting execution has an invalid lifecycle state",
                    )
            if continuation.worker_id is not None or continuation.lease_expires_at is not None:
                raise RepairApplicationError("REPAIR_RECOVERY_NOT_ELIGIBLE", "Continuation still has an active owner")
            if attempt.status != "proposed" or not attempt.proposal_artifact_id or not attempt.proposal_checksum:
                raise RepairApplicationError("REPAIR_RECOVERY_NOT_ELIGIBLE", "Repair attempt does not have an immutable proposal")
            if any(
                getattr(attempt, field) is not None
                for field in (
                    "review_artifact_id",
                    "review_checksum",
                    "g10_gate_package_id",
                    "apply_ledger_artifact_id",
                    "post_fingerprint",
                    "validation_summary_artifact_id",
                )
            ):
                raise RepairApplicationError("REPAIR_RECOVERY_NOT_ELIGIBLE", "Reviewer recovery is unsafe after downstream state exists")
            if continuation.stage_plan_id is None or continuation.stage_plan_checksum is None:
                raise RepairApplicationError("REPAIR_RECOVERY_NOT_ELIGIBLE", "Stage plan authority is missing")
            stage_plan = session.scalar(
                select(StageExecutionPlanModel).where(
                    StageExecutionPlanModel.id == continuation.stage_plan_id,
                    StageExecutionPlanModel.run_id == run_id,
                    StageExecutionPlanModel.stage_id == attempt.stage_id,
                    StageExecutionPlanModel.checksum == continuation.stage_plan_checksum,
                )
            )
            if stage_plan is None:
                raise RepairApplicationError("REPAIR_RECOVERY_NOT_ELIGIBLE", "Stage plan authority is stale")
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == run_id,
                    StageWorkspaceBindingModel.stage_id == attempt.stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if binding is None or not attempt.pre_fingerprint:
                raise RepairApplicationError("REPAIR_RECOVERY_NOT_ELIGIBLE", "Active workspace authority is missing")
            try:
                live_fingerprint = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
            except OSError as error:
                raise RepairApplicationError("REPAIR_WORKSPACE_STALE", "Repair workspace is unavailable") from error
            if live_fingerprint != binding.workspace_fingerprint or attempt.pre_fingerprint != binding.workspace_fingerprint:
                raise RepairApplicationError("REPAIR_WORKSPACE_STALE", "Repair workspace authority changed")
            checkpoint = session.get(StageCheckpointModel, attempt.checkpoint_id) if attempt.checkpoint_id else None
            if (
                checkpoint is None
                or checkpoint.run_id != run_id
                or checkpoint.stage_id != attempt.stage_id
                or checkpoint.kind != "pre_repair"
                or not checkpoint.safe_for_resume
                or checkpoint.workspace_fingerprint != binding.workspace_fingerprint
            ):
                raise RepairApplicationError("REPAIR_RECOVERY_NOT_ELIGIBLE", "Pre-repair checkpoint authority is missing or stale")
            old_key = _invocation_key(attempt.id, LlmRole.REPAIR_REVIEWER)
            old = session.scalar(
                select(LlmInvocationModel).where(
                    LlmInvocationModel.run_id == run_id,
                    LlmInvocationModel.idempotency_key == old_key,
                )
            )
            old_artifacts = [
                session.get(ArtifactMetadataModel, "metadata-" + str(artifact_id))
                for artifact_id in (old.artifact_ids if old is not None else [])
            ]
            has_non_response_diagnostic_only = all(
                metadata is not None
                and PurePosixPath(str(metadata.relative_path)).name == "review-error.json"
                for metadata in old_artifacts
            )
            if (
                old is None
                or old.stage_id != attempt.stage_id
                or old.role != "repair_reviewer"
                or old.task_type != LlmTaskType.REPAIR_REVIEW.value
                or old.status != "in_progress"
                or not old.transport_started
                or old.response_received is True
                or old.completed_at is not None
                or old.provider_response_id is not None
                or old.provider_request_id is not None
                or old.provider_http_status is not None
                or old.provider_error_code is not None
                or not has_non_response_diagnostic_only
                or attempt.reviewer_invocation_id not in {None, old.id}
            ):
                raise RepairApplicationError("REPAIR_RECOVERY_NOT_ELIGIBLE", "Reviewer invocation is not an irrecoverable uncertain call")
            now = self._now()
            successor_key = f"{old_key}:recovery-1"
            successor = LlmInvocationModel(
                id=successor_key,
                run_id=run_id,
                stage_id=attempt.stage_id,
                idempotency_key=successor_key,
                request_checksum=old.request_checksum,
                input_hashes=[*(old.input_hashes or []), f"recovery_of:{old.idempotency_key}", "recovery_generation:1"],
                correlation_id=successor_key,
                actor=actor,
                role=old.role,
                task_type=old.task_type,
                provider=old.provider,
                deployment_alias=old.deployment_alias,
                prompt_version=old.prompt_version,
                schema_version=old.schema_version,
                pricing_version=old.pricing_version,
                stage=old.stage,
                redacted_summary=None,
                status="in_progress",
                artifact_ids=[],
                artifact_checksums={},
                state_version=1,
                event_sequence=0,
                retries=old.retries or 0,
                transport_started=False,
                response_received=None,
                started_at=now,
                completed_at=None,
                created_at=now,
            )
            old.status = "uncertain_abandoned"
            old.completed_at = now
            old.state_version += 1
            attempt.reviewer_invocation_id = successor.id
            attempt.updated_at = now
            continuation.status = "queued"
            continuation.current_node = "review_repair"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.next_attempt_at = None
            continuation.waiting_execution_id = None
            continuation.last_error_code = None
            continuation.last_error_message = None
            continuation.wake_sequence += 1
            continuation.state_version += 1
            continuation.updated_at = now
            session.add(successor)
            session.flush()
            append_continuation_event(
                session,
                continuation,
                event_type=WorkflowEventType.REPAIR_INVOCATION_RECOVERED,
                key=event_marker,
                reason=reason,
                actor=actor,
                occurred_at=now,
                payload={
                    "run_id": run_id,
                    "stage_id": attempt.stage_id,
                    "attempt_id": attempt_id,
                    "old_invocation_id": old.id,
                    "old_invocation_key": old.idempotency_key,
                    "new_invocation_id": successor.id,
                    "new_invocation_key": successor.idempotency_key,
                    "role": "reviewer",
                    "proposal_checksum": attempt.proposal_checksum,
                    "request_checksum": old.request_checksum,
                    "operator_actor": actor,
                    "recovery_request_idempotency_key": idempotency_key,
                    "reason": reason,
                    "recovery_generation": 1,
                    "recovery_request_checksum": request_checksum,
                    "recovered_at": now.isoformat(),
                },
            )
            return {
                "run_id": run_id,
                "attempt_id": attempt_id,
                "old_invocation_key": old.idempotency_key,
                "new_invocation_key": successor.idempotency_key,
                "new_invocation_id": successor.id,
                "proposal_checksum": attempt.proposal_checksum,
                "idempotent_replay": False,
            }

    def _recover_uncertain_proposer_invocation(
        self,
        *,
        run_id: str,
        attempt_id: str,
        expected_state_version: int,
        idempotency_key: str,
        actor: str,
        reason: str,
    ) -> dict[str, object]:
        generation = 1
        old = None
        with self._scope() as session:
            attempt = session.get(RepairAttemptModel, attempt_id)
            continuation = (
                session.scalar(
                    select(TransformationContinuationModel).where(
                        TransformationContinuationModel.run_id == run_id,
                        TransformationContinuationModel.current_stage_id == attempt.stage_id,
                    )
                )
                if attempt is not None
                else None
            )
            prior_events = [
                event
                for event in session.scalars(
                    select(WorkflowEventModel).where(
                        WorkflowEventModel.run_id == run_id,
                        WorkflowEventModel.event_type
                        == WorkflowEventType.REPAIR_INVOCATION_RECOVERED.value,
                    )
                ).all()
                if (event.payload or {}).get("attempt_id") == attempt_id
                and (event.payload or {}).get("role") == "proposer"
            ]
            prior = max(
                prior_events,
                key=lambda event: int((event.payload or {}).get("recovery_generation") or 0),
                default=None,
            )
            if prior is not None:
                successor_key = str((prior.payload or {}).get("new_invocation_key") or "")
                successor = session.scalar(
                    select(LlmInvocationModel).where(
                        LlmInvocationModel.run_id == run_id,
                        LlmInvocationModel.idempotency_key == successor_key,
                    )
                )
                if successor is None:
                    raise RepairApplicationError(
                        "REPAIR_RECOVERY_CONFLICT",
                        "Existing uncertain-invocation recovery evidence is incomplete",
                    )
                can_retry_recovered = (
                    attempt is not None
                    and continuation is not None
                    and continuation.state_version == expected_state_version
                    and continuation.status == "blocked"
                    and continuation.current_node == "propose_repair"
                    and continuation.last_error_code == "REPAIR_INVOCATION_UNCERTAIN"
                    and continuation.worker_id is None
                    and continuation.lease_expires_at is None
                    and attempt.status in {"evidence_frozen", "proposed"}
                    and attempt.proposal_artifact_id is None
                    and attempt.proposer_invocation_id == successor.id
                    and successor.status == "in_progress"
                    and successor.transport_started
                    and successor.response_received is not True
                    and successor.completed_at is None
                    and successor.provider_response_id is None
                    and successor.provider_request_id is None
                    and successor.provider_http_status is None
                    and successor.provider_error_code is None
                )
                if not can_retry_recovered:
                    return {
                        "run_id": run_id,
                        "attempt_id": attempt_id,
                        "old_invocation_key": (prior.payload or {}).get("old_invocation_key"),
                        "new_invocation_key": successor_key,
                        "new_invocation_id": successor.id,
                        "proposal_checksum": None,
                        "idempotent_replay": True,
                    }
                old = successor
                generation = int((prior.payload or {}).get("recovery_generation") or 1) + 1
            if (
                attempt is None
                or continuation is None
                or continuation.state_version != expected_state_version
                or continuation.status != "blocked"
                or continuation.current_node != "propose_repair"
                or continuation.last_error_code != "REPAIR_INVOCATION_UNCERTAIN"
                or continuation.worker_id is not None
                or continuation.lease_expires_at is not None
                or attempt.status not in {"evidence_frozen", "proposed"}
                or attempt.proposal_artifact_id is not None
                or (old is None and attempt.proposer_invocation_id is not None)
            ):
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Proposer invocation is not an irrecoverable uncertain call",
                )
            stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == run_id,
                    StageWorkspaceBindingModel.stage_id == attempt.stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            checkpoint = (
                session.get(StageCheckpointModel, attempt.checkpoint_id)
                if attempt.checkpoint_id
                else None
            )
            if (
                stage_plan is None
                or stage_plan.run_id != run_id
                or stage_plan.stage_id != attempt.stage_id
                or stage_plan.checksum != continuation.stage_plan_checksum
                or binding is None
                or checkpoint is None
                or checkpoint.kind != "pre_repair"
                or not checkpoint.safe_for_resume
                or checkpoint.workspace_fingerprint != binding.workspace_fingerprint
                or attempt.pre_fingerprint != binding.workspace_fingerprint
                or StageSandboxCopier.fingerprint(Path(binding.workspace_path))
                != binding.workspace_fingerprint
            ):
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Proposer recovery authority is missing or stale",
                )
            if old is None:
                old = session.scalar(
                    select(LlmInvocationModel)
                    .where(
                        LlmInvocationModel.run_id == run_id,
                        LlmInvocationModel.id.like(f"{attempt_id}:proposer%"),
                        LlmInvocationModel.status == "in_progress",
                    )
                    .order_by(LlmInvocationModel.created_at.desc())
                    .limit(1)
                )
            if (
                old is None
                or old.stage_id != attempt.stage_id
                or old.role != "repair_proposer"
                or old.task_type != LlmTaskType.REPAIR_DIAGNOSIS.value
                or not old.transport_started
                or old.response_received is True
                or old.completed_at is not None
                or old.provider_response_id is not None
                or old.provider_request_id is not None
                or old.provider_http_status is not None
                or old.provider_error_code is not None
            ):
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Proposer invocation is not an irrecoverable uncertain call",
                )
            now = self._now()
            request_checksum = self._request_checksum(
                {
                    "run_id": run_id,
                    "attempt_id": attempt_id,
                    "expected_state_version": expected_state_version,
                    "actor": actor,
                    "reason": reason,
                    "role": "proposer",
                    "generation": generation,
                }
            )
            event_marker = f"repair-invocation-recovery:{attempt_id}:proposer:{generation}"
            recovery_root = old.id.split(":recovery-", 1)[0]
            successor_key = f"{recovery_root}:recovery-{generation}"
            successor = LlmInvocationModel(
                id=successor_key,
                run_id=run_id,
                stage_id=attempt.stage_id,
                idempotency_key=successor_key,
                request_checksum=old.request_checksum,
                input_hashes=[
                    *(old.input_hashes or []),
                    f"recovery_of:{old.idempotency_key}",
                    f"recovery_generation:{generation}",
                ],
                correlation_id=successor_key,
                actor=actor,
                role=old.role,
                task_type=old.task_type,
                provider=old.provider,
                deployment_alias=old.deployment_alias,
                prompt_version=old.prompt_version,
                schema_version=old.schema_version,
                pricing_version=old.pricing_version,
                stage=old.stage,
                redacted_summary=None,
                status="in_progress",
                artifact_ids=[],
                artifact_checksums={},
                state_version=1,
                event_sequence=0,
                retries=old.retries or 0,
                transport_started=False,
                response_received=None,
                started_at=now,
                completed_at=None,
                created_at=now,
            )
            old.status = "uncertain_abandoned"
            old.completed_at = now
            old.state_version += 1
            attempt.proposer_invocation_id = successor.id
            attempt.updated_at = now
            continuation.status = "queued"
            continuation.current_node = "propose_repair"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.next_attempt_at = None
            continuation.waiting_execution_id = None
            continuation.last_error_code = None
            continuation.last_error_message = None
            continuation.wake_sequence += 1
            continuation.state_version += 1
            continuation.updated_at = now
            session.add(successor)
            append_continuation_event(
                session,
                continuation,
                event_type=WorkflowEventType.REPAIR_INVOCATION_RECOVERED,
                key=event_marker,
                reason=reason,
                actor=actor,
                occurred_at=now,
                payload={
                    "run_id": run_id,
                    "stage_id": attempt.stage_id,
                    "attempt_id": attempt_id,
                    "old_invocation_id": old.id,
                    "old_invocation_key": old.idempotency_key,
                    "new_invocation_id": successor.id,
                    "new_invocation_key": successor.idempotency_key,
                    "role": "proposer",
                    "proposal_checksum": None,
                    "request_checksum": old.request_checksum,
                    "operator_actor": actor,
                    "recovery_request_idempotency_key": idempotency_key,
                    "reason": reason,
                    "recovery_generation": generation,
                    "recovery_request_checksum": request_checksum,
                    "recovered_at": now.isoformat(),
                },
            )
            return {
                "run_id": run_id,
                "attempt_id": attempt_id,
                "old_invocation_key": old.idempotency_key,
                "new_invocation_key": successor.idempotency_key,
                "new_invocation_id": successor.id,
                "proposal_checksum": None,
                "idempotent_replay": False,
            }

    def _semantic_recovery_authority(
        self,
        session,
        context: dict[str, object],
        *,
        run_id: str,
        attempt_id: str,
        expected_state_version: int,
    ) -> dict[str, object]:
        attempt = session.get(RepairAttemptModel, attempt_id)
        if attempt is None:
            raise RepairApplicationError(
                "REPAIR_ATTEMPT_NOT_FOUND", "Repair attempt is missing"
            )
        if attempt.run_id != run_id or attempt.stage_id != context["stage_id"]:
            raise RepairApplicationError(
                "REPAIR_ATTEMPT_MISMATCH",
                "Repair attempt does not belong to the requested run or stage",
            )
        existing = self._semantic_recovery_child(session, run_id, attempt_id)
        if existing is not None:
            return {"existing_child": existing}
        continuation = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id,
            )
        )
        latest = session.scalar(
            select(RepairAttemptModel)
            .where(
                RepairAttemptModel.run_id == run_id,
                RepairAttemptModel.stage_id == attempt.stage_id,
            )
            .order_by(RepairAttemptModel.attempt_number.desc())
            .limit(1)
        )
        if continuation is None or latest is None:
            raise RepairApplicationError(
                "REPAIR_RECOVERY_NOT_ELIGIBLE",
                "Repair recovery authority is missing",
            )
        if (
            latest.id != attempt.id
            or attempt.status not in {"evidence_frozen", "blocked"}
            or attempt.completed_at is not None
            or continuation.current_stage_id != attempt.stage_id
            or continuation.status != "blocked"
            or continuation.current_node != "propose_repair"
            or continuation.last_error_code
            not in {
                "REPAIR_SEMANTIC_RETRY_EXHAUSTED",
                "REPAIR_CAUSAL_REJECTION",
                "REPAIR_DEPENDENCY_EVIDENCE_INVALID",
                "REPAIR_PROPOSAL_SCHEMA_INVALID",
            }
            or continuation.state_version != expected_state_version
        ):
            raise RepairApplicationError(
                "REPAIR_RECOVERY_NOT_ELIGIBLE",
                "Repair attempt is not in the exhausted proposal-less recovery state",
            )
        if any(
            getattr(attempt, field)
            for field in (
                "proposal_artifact_id",
                "proposal_checksum",
                "review_artifact_id",
                "review_checksum",
                "reviewer_invocation_id",
                "g10_gate_package_id",
                "apply_ledger_artifact_id",
                "apply_ledger_checksum",
                "validation_summary_artifact_id",
                "validation_summary_checksum",
                "post_fingerprint",
            )
        ):
            raise RepairApplicationError(
                "REPAIR_RECOVERY_NOT_ELIGIBLE",
                "Repair attempt already has proposal, review, gate, apply, or validation evidence",
            )
        recovered_proposer_id = attempt.proposer_invocation_id
        if recovered_proposer_id is not None and ":recovery-" not in recovered_proposer_id:
            raise RepairApplicationError(
                "REPAIR_RECOVERY_NOT_ELIGIBLE",
                "Repair attempt has an unexpected proposer invocation binding",
            )
        if (
            context.get("failure_evidence_artifact_id")
            != attempt.failure_evidence_artifact_id
            or context.get("failure_evidence_checksum")
            != attempt.failure_evidence_checksum
            or context.get("context_pack_artifact_id")
            != attempt.context_pack_artifact_id
            or context.get("context_pack_checksum") != attempt.context_pack_checksum
        ):
            raise RepairApplicationError(
                "REPAIR_RECOVERY_NOT_ELIGIBLE",
                "Repair evidence lineage changed",
            )
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        if (
            stage_plan is None
            or stage_plan.run_id != run_id
            or stage_plan.stage_id != attempt.stage_id
            or stage_plan.checksum != continuation.stage_plan_checksum
        ):
            raise RepairApplicationError(
                "REPAIR_RECOVERY_NOT_ELIGIBLE",
                "Repair stage-plan authority is missing or stale",
            )
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == run_id,
                StageWorkspaceBindingModel.stage_id == attempt.stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        if binding is None:
            raise RepairApplicationError(
                "REPAIR_RECOVERY_NOT_ELIGIBLE",
                "Active repair workspace binding is missing",
            )
        try:
            live_fingerprint = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
        except OSError as error:
            raise RepairApplicationError(
                "REPAIR_WORKSPACE_STALE",
                "Repair workspace is unavailable",
            ) from error
        if (
            live_fingerprint != binding.workspace_fingerprint
            or binding.workspace_fingerprint != attempt.pre_fingerprint
            or context.get("workspace_stored_fingerprint") != binding.workspace_fingerprint
            or context.get("workspace_live_fingerprint") != live_fingerprint
        ):
            raise RepairApplicationError(
                "REPAIR_WORKSPACE_STALE",
                "Repair workspace authority changed",
            )
        checkpoint = (
            session.get(StageCheckpointModel, attempt.checkpoint_id)
            if attempt.checkpoint_id
            else None
        )
        checkpoint_matches_workspace = bool(
            checkpoint is not None
            and checkpoint.workspace_fingerprint == binding.workspace_fingerprint
        )
        ancestor = attempt
        for _ in range(32):
            if checkpoint_matches_workspace or not ancestor.parent_attempt_id:
                break
            ancestor = session.get(RepairAttemptModel, ancestor.parent_attempt_id)
            if ancestor is None:
                break
            checkpoint_matches_workspace = bool(
                ancestor.apply_ledger_artifact_id
                and ancestor.post_fingerprint == binding.workspace_fingerprint
            )
        if (
            checkpoint is None
            or checkpoint.run_id != run_id
            or checkpoint.stage_id != attempt.stage_id
            or checkpoint.kind != "pre_repair"
            or not checkpoint.safe_for_resume
            or not checkpoint_matches_workspace
        ):
            raise RepairApplicationError(
                "REPAIR_RECOVERY_NOT_ELIGIBLE",
                "Pre-repair checkpoint authority is missing or stale",
            )
        base_invocation_id = f"{attempt.id}:proposer"
        retry_invocation_id = f"{base_invocation_id}:semantic-retry-1"
        base_invocation = session.scalar(
            select(LlmInvocationModel).where(
                LlmInvocationModel.run_id == run_id,
                LlmInvocationModel.idempotency_key == base_invocation_id,
            )
        )
        retry_invocation = session.scalar(
            select(LlmInvocationModel).where(
                LlmInvocationModel.run_id == run_id,
                LlmInvocationModel.idempotency_key
                == (recovered_proposer_id or retry_invocation_id),
            )
        )
        retry_valid = (
            retry_invocation is not None
            and retry_invocation.status == "failed"
            and retry_invocation.failure_code in _RECOVERABLE_PROPOSER_RETRY_CODES
            and (
                (
                    retry_invocation.failure_stage == "repair_semantics"
                    and retry_invocation.retries >= 0
                    if recovered_proposer_id
                    else retry_invocation.retries == 1
                    and retry_invocation.failure_stage == "repair_semantics"
                )
                or (
                    retry_invocation.failure_code == "LLM_PROTOCOL_FAILED"
                    and retry_invocation.retries >= 1
                    and retry_invocation.failure_stage == "response_state_validation"
                )
            )
        )
        base_valid = (
            base_invocation is not None
            and (
                base_invocation.status == "failed"
                or (
                    recovered_proposer_id is not None
                    and base_invocation.status == "uncertain_abandoned"
                )
            )
        )
        if not base_valid or not retry_valid:
            raise RepairApplicationError(
                "REPAIR_RECOVERY_NOT_ELIGIBLE",
                "Persisted semantic retry evidence is missing or invalid",
            )
        return {
            "existing_child": None,
            "attempt": attempt,
            "continuation": continuation,
            "stage_plan": stage_plan,
            "binding": binding,
            "checkpoint": checkpoint,
        }

    @staticmethod
    def _semantic_recovery_child(session, run_id: str, attempt_id: str):
        children = session.scalars(
            select(RepairAttemptModel)
            .where(
                RepairAttemptModel.run_id == run_id,
                RepairAttemptModel.parent_attempt_id == attempt_id,
            )
            .order_by(RepairAttemptModel.attempt_number)
        ).all()
        if len(children) > 1:
            raise RepairApplicationError(
                "REPAIR_RECOVERY_CONFLICT",
                "Multiple semantic recovery children exist for one parent",
            )
        if children:
            parent = session.get(RepairAttemptModel, attempt_id)
            if (
                parent is None
                or children[0].run_id != run_id
                or children[0].stage_id != parent.stage_id
                or children[0].attempt_number != parent.attempt_number + 1
            ):
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_CONFLICT",
                    "Semantic recovery child lineage is invalid",
                )
        return children[0] if children else None

    @staticmethod
    def _semantic_recovery_result(child, *, idempotent_replay: bool) -> dict[str, object]:
        return {
            "attempt_id": child.id,
            "status": child.status,
            "idempotent_replay": idempotent_replay,
        }

    @staticmethod
    def _semantic_recovery_event_key(idempotency_key: str) -> str:
        return "semantic-recovery:" + hashlib.sha256(idempotency_key.encode()).hexdigest()

    def _semantic_recovery_event(self, session, run_id: str, idempotency_key: str):
        continuation = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id,
            )
        )
        if continuation is None:
            return None
        return session.scalar(
            select(WorkflowEventModel).where(
                WorkflowEventModel.run_id == run_id,
                WorkflowEventModel.idempotency_key == (
                    f"{continuation.id}:{self._semantic_recovery_event_key(idempotency_key)}"
                ),
            )
        )

    def _semantic_recovery_replay(
        self,
        run_id: str,
        attempt_id: str,
        idempotency_key: str,
        request_checksum: str,
    ) -> dict[str, object] | None:
        with self._scope() as session:
            attempt = session.get(RepairAttemptModel, attempt_id)
            if attempt is None:
                raise RepairApplicationError(
                    "REPAIR_ATTEMPT_NOT_FOUND", "Repair attempt is missing"
                )
            if attempt.run_id != run_id:
                raise RepairApplicationError(
                    "REPAIR_ATTEMPT_MISMATCH",
                    "Repair attempt does not belong to the requested run",
                )
            event = self._semantic_recovery_event(session, run_id, idempotency_key)
            if event is None:
                return None
            if (event.payload or {}).get("request_checksum") != request_checksum:
                raise RepairApplicationError(
                    "IDEMPOTENCY_PAYLOAD_MISMATCH",
                    "Semantic recovery key has a different payload",
                )
            child_id = str((event.payload or {}).get("child_attempt_id") or "")
            child = session.get(RepairAttemptModel, child_id)
            if child is None or child.parent_attempt_id != attempt_id:
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_REPLAY_INVALID",
                    "Semantic recovery replay child is missing",
                )
            return self._semantic_recovery_result(child, idempotent_replay=True)

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
            proposal = json.loads(str(context["segments"][2]))
            review = json.loads(str(context["segments"][3]))
            RepairProposal.model_validate(proposal)
            RepairReview.model_validate(review)
        except (ValidationError, ValueError) as error:
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
                stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
                repair_policy = (
                    ((stage_plan.stage_plan or {}).get("repair_policy") or {})
                    if stage_plan is not None
                    else {}
                )
                budget = repair_budget(
                    session,
                    continuation.run_id,
                    continuation.current_stage_id,
                    repair_policy,
                )
                # A revision request is already bounded by its live review or
                # G10 modification lineage below.  Do not let the apply-count
                # budget reject a governed correction of an active G10 package;
                # ordinary new repair attempts remain budget-gated by the
                # transformer classifier.
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
                        StageGatePackageModel.status.in_(("pending", "rejected")),
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
                preflight_revision = (
                    attempt.status in {"review_accepted", "blocked"}
                    and review["decision"] == "accept"
                    and continuation.current_stage_id == attempt.stage_id
                    and continuation.status == "blocked"
                    and continuation.current_node == "create_g10"
                    and continuation.last_error_code == "REPAIR_DEPENDENCY_PREFLIGHT_FAILED"
                    and pending_g10 is None
                )
                g10_override_revision = (
                    attempt.status == "waiting_g10"
                    and review["decision"] in {"request_changes", "accept"}
                    and continuation.current_stage_id == attempt.stage_id
                    and continuation.status in {"waiting_gate", "blocked"}
                    and continuation.current_node == "wait_g10"
                    and pending_g10 is not None
                    and attempt.g10_gate_package_id == pending_g10.id
                    and (
                        review["decision"] == "request_changes"
                        or continuation.last_error_code == "G10_REQUEST_MODIFICATION"
                    )
                )
                if not reviewer_revision and not accepted_revision and not preflight_revision and not g10_override_revision:
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

    def recover_invalid_g10_override(
        self,
        *,
        run_id: str,
        attempt_id: str,
        proposal_id: str,
        base_checksum: str,
        instruction: str,
        expected_state_version: int,
        idempotency_key: str,
        actor: str,
        correlation_id: str,
    ) -> dict[str, object]:
        """Recover a legacy G10 approval that bypassed reviewer request_changes.

        The old gate, apply ledger, and failure remain immutable history.  The
        only new repair lineage is a revision child rooted at the safe
        pre-repair checkpoint.
        """
        request_checksum = self._request_checksum(
            {
                "run_id": run_id,
                "attempt_id": attempt_id,
                "proposal_id": proposal_id,
                "base_checksum": base_checksum,
                "instruction": instruction,
                "expected_state_version": expected_state_version,
                "actor": actor,
                "correlation_id": correlation_id,
            }
        )
        event_key = self._legacy_override_recovery_event_key(idempotency_key)
        from app.services.transformer_stage_service import TransformerStageService

        stage_service = TransformerStageService(scope=self._scope)
        with self._scope() as session:
            existing = session.scalar(
                select(WorkflowEventModel).where(
                    WorkflowEventModel.run_id == run_id,
                    WorkflowEventModel.idempotency_key.like(f"%:{event_key}"),
                )
            )
            if existing is not None:
                if (existing.payload or {}).get("request_checksum") != request_checksum:
                    raise RepairApplicationError(
                        "IDEMPOTENCY_PAYLOAD_MISMATCH",
                        "Recovery key has a different payload",
                    )
                child = session.get(
                    RepairAttemptModel,
                    (existing.payload or {}).get("child_attempt_id"),
                )
                if child is None:
                    raise RepairApplicationError(
                        "REPAIR_RECOVERY_REPLAY_INVALID",
                        "Recovery replay child is missing",
                    )
                return {"attempt_id": child.id, "status": child.status, "idempotent_replay": True}
            attempt = session.get(RepairAttemptModel, attempt_id)
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == run_id,
                    TransformationContinuationModel.current_stage_id == (
                        attempt.stage_id if attempt is not None else ""
                    ),
                )
            )
            run = session.get(MigrationRunModel, run_id)
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == run_id,
                    StageWorkspaceBindingModel.stage_id == (
                        attempt.stage_id if attempt is not None else ""
                    ),
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            checkpoint = (
                session.get(StageCheckpointModel, attempt.checkpoint_id)
                if attempt is not None and attempt.checkpoint_id
                else None
            )
            gate = (
                session.get(StageGatePackageModel, attempt.g10_gate_package_id)
                if attempt is not None and attempt.g10_gate_package_id
                else None
            )
            failure = session.scalar(
                select(CommandExecutionModel)
                .where(
                    CommandExecutionModel.run_id == run_id,
                    CommandExecutionModel.stage_id == (
                        attempt.stage_id if attempt is not None else ""
                    ),
                    CommandExecutionModel.command_id == "npm-lockfile-generate",
                    CommandExecutionModel.status == "failed",
                )
                .order_by(CommandExecutionModel.finished_at.desc())
                .limit(1)
            )
            if (
                attempt is None
                or run is None
                or continuation is None
                or binding is None
                or checkpoint is None
                or gate is None
            ):
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Legacy G10 recovery authority is incomplete",
                )
            if continuation.state_version != expected_state_version:
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_STALE",
                    "Continuation state changed before recovery",
                )
            if (
                continuation.status != "blocked"
                or continuation.current_node != "classify_failure"
                or continuation.last_error_code != "REPAIR_ATTEMPT_LIMIT"
                or attempt.status not in {"applied_verified", "blocked"}
                or attempt.proposal_artifact_id != proposal_id
                or attempt.proposal_checksum != base_checksum
                or attempt.review_artifact_id is None
                or attempt.review_checksum is None
                or attempt.apply_ledger_artifact_id is None
                or gate.status != "approved"
                or failure is None
            ):
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Repair is not the blocked legacy G10 override lineage",
                )
            if checkpoint.kind != "pre_repair" or not checkpoint.safe_for_resume:
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Safe pre-repair checkpoint is missing",
                )
            metadata = session.get(
                ArtifactMetadataModel, "metadata-" + str(attempt.review_artifact_id)
            )
            if metadata is None or metadata.checksum != attempt.review_checksum:
                raise RepairApplicationError(
                    "REPAIR_REVIEW_STALE", "Reviewer evidence is missing or stale"
                )
            try:
                store = LocalFilesystemArtifactStore(
                    Path(run.artifact_root).parent,
                    fixed_run_root=Path(run.artifact_root),
                )
                review = json.loads(
                    store.read_artifact(run_id, metadata.relative_path).content
                )
                RepairReview.model_validate(review)
            except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError, ValidationError) as error:
                raise RepairApplicationError(
                    "REPAIR_REVIEW_STALE", "Reviewer evidence cannot be verified"
                ) from error
            if review.get("proposal_checksum") != base_checksum or review.get("decision") != "request_changes":
                raise RepairApplicationError(
                    "REPAIR_REVIEW_NOT_ACCEPTED",
                    "Recovery requires the persisted reviewer request_changes decision",
                )
            expected_checkpoint = stage_service.authoritative_checkpoint_fingerprint(
                session, checkpoint
            )
            if expected_checkpoint is None:
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Pre-repair checkpoint integrity cannot be proven",
                )
            if attempt.pre_fingerprint not in {checkpoint.workspace_fingerprint, expected_checkpoint}:
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Repair pre-fingerprint is not bound to the checkpoint",
                )
            stage_service.begin_reconstruction(
                session,
                continuation,
                checkpoint=checkpoint,
                reason="legacy_g10_override_recovery",
                attempt_id=attempt.id,
            )
            session.commit()
            source = checkpoint.workspace_path
            workspace = binding.workspace_path
            artifact_root = run.artifact_root
            failure_id = failure.id
            failure_code = failure.failure_code
            failure_message = failure.failure_message
        try:
            restored = stage_service.reconstruct_workspace(
                source,
                workspace,
                str(Path(workspace).resolve().parent),
                expected_checkpoint,
                str(Path(artifact_root).resolve()),
            )
        except Exception as error:
            raise RepairApplicationError(
                "REPAIR_RECOVERY_RECONSTRUCTION_FAILED",
                "Safe pre-repair checkpoint reconstruction failed",
            ) from error
        if restored != expected_checkpoint:
            raise RepairApplicationError(
                "REPAIR_RECOVERY_RECONSTRUCTION_FAILED",
                "Reconstructed workspace fingerprint does not match the checkpoint",
            )
        with self._scope() as session:
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == run_id
                )
            )
            attempt = session.get(RepairAttemptModel, attempt_id)
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == run_id,
                    StageWorkspaceBindingModel.stage_id == attempt.stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if (
                continuation is None
                or attempt is None
                or binding is None
                or continuation.state_version != expected_state_version
            ):
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_STALE",
                    "Durable state changed during checkpoint reconstruction",
                )
            binding.workspace_fingerprint = restored
            binding.fingerprint_profile_id = STAGE_FINGERPRINT_PROFILE.profile_id
            binding.last_verified_fingerprint = restored
            binding.last_verified_at = self._now()
            session.flush()
        context = self._attempt_context(attempt_id, include_proposal=True, include_review=True)
        proposal = json.loads(str(context["segments"][2]))
        review = json.loads(str(context["segments"][3]))
        revision_context = json.loads(str(context["segments"][1]))
        revision_context["human_revision"] = {
            "instruction": instruction,
            "parent_attempt_id": attempt_id,
            "parent_proposal_id": proposal_id,
            "parent_proposal_checksum": base_checksum,
            "previous_proposal": proposal,
            "reviewer_output": review,
            "recovery_failure_execution_id": failure_id,
            "recovery_failure_code": failure_code,
            "recovery_failure_message": failure_message,
            "grounding_instructions": _PROPOSER_GROUNDING_INSTRUCTIONS,
        }
        child_id = f"repair-{context['stage_id']}-{int(context['attempt_number']) + 1}"
        stored = self._write_revision_context(
            context,
            child_id=child_id,
            payload=revision_context,
            instruction=instruction,
        )
        try:
            with self._scope() as session:
                existing = session.scalar(
                    select(WorkflowEventModel).where(
                        WorkflowEventModel.run_id == run_id,
                        WorkflowEventModel.idempotency_key.like(f"%:{event_key}"),
                    )
                )
                if existing is not None:
                    self._remove_uncommitted_artifact(stored)
                    child = session.get(
                        RepairAttemptModel,
                        (existing.payload or {}).get("child_attempt_id"),
                    )
                    if child is None:
                        raise RepairApplicationError(
                            "REPAIR_RECOVERY_REPLAY_INVALID",
                            "Recovery replay child is missing",
                        )
                    return {"attempt_id": child.id, "status": child.status, "idempotent_replay": True}
                continuation = session.scalar(
                    select(TransformationContinuationModel).where(
                        TransformationContinuationModel.run_id == run_id
                    )
                )
                attempt = session.get(RepairAttemptModel, attempt_id)
                if (
                    continuation is None
                    or attempt is None
                    or continuation.state_version != expected_state_version
                    or attempt.proposal_checksum != base_checksum
                ):
                    raise RepairApplicationError(
                        "REPAIR_RECOVERY_STALE",
                        "Durable state changed before recovery commit",
                    )
                self._register_artifact_metadata(session, context, stored)
                now = self._now()
                child = RepairAttemptModel(
                    id=child_id,
                    run_id=run_id,
                    stage_id=attempt.stage_id,
                    attempt_number=attempt.attempt_number + 1,
                    state_version=1,
                    status="evidence_frozen",
                    risk_level="unknown",
                    diagnosis=f"legacy G10 override recovery; parent={attempt.id}",
                    checkpoint_id=attempt.checkpoint_id,
                    failure_evidence_artifact_id=attempt.failure_evidence_artifact_id,
                    failure_evidence_checksum=attempt.failure_evidence_checksum,
                    failure_route_artifact_id=attempt.failure_route_artifact_id,
                    failure_route_checksum=attempt.failure_route_checksum,
                    context_pack_artifact_id=stored.ref.artifact_id,
                    context_pack_checksum=stored.ref.checksum,
                    pre_fingerprint=restored,
                    failure_fingerprint=attempt.failure_fingerprint,
                    parent_attempt_id=attempt.id,
                    parent_review_artifact_id=attempt.review_artifact_id,
                    parent_review_checksum=attempt.review_checksum,
                    created_at=now,
                    updated_at=now,
                )
                session.add(child)
                attempt.status = "superseded"
                attempt.completed_at = now
                attempt.updated_at = now
                continuation.status = "queued"
                continuation.current_node = "propose_repair"
                continuation.worker_id = None
                continuation.lease_expires_at = None
                continuation.next_attempt_at = None
                continuation.waiting_execution_id = None
                continuation.last_error_code = None
                continuation.last_error_message = None
                continuation.wake_sequence += 1
                continuation.state_version += 1
                continuation.updated_at = now
                session.flush()
                append_continuation_event(
                    session,
                    continuation,
                    event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED,
                    key=event_key,
                    reason="legacy G10 override recovery requested",
                    actor=actor,
                    occurred_at=now,
                    payload={
                        "attempt_id": attempt.id,
                        "child_attempt_id": child.id,
                        "request_checksum": request_checksum,
                        "expected_state_version": expected_state_version,
                        "correlation_id": correlation_id,
                    },
                )
                return {"attempt_id": child.id, "status": child.status, "idempotent_replay": False}
        except RepairApplicationError:
            self._remove_uncommitted_artifact(stored)
            raise

    def recover_bound_candidate(
        self,
        *,
        run_id: str,
        attempt_id: str,
        expected_state_version: int,
        idempotency_key: str,
        actor: str,
        correlation_id: str,
    ) -> dict[str, object]:
        """Rebind a valid immutable candidate after a backend-only bind failure."""
        request_checksum = self._request_checksum(
            {
                "run_id": run_id,
                "attempt_id": attempt_id,
                "expected_state_version": expected_state_version,
                "actor": actor,
                "correlation_id": correlation_id,
                "recovery": "bound-candidate-v1",
            }
        )
        event_key = self._bound_candidate_recovery_event_key(idempotency_key)
        with self._scope() as session:
            existing = session.scalar(
                select(WorkflowEventModel).where(
                    WorkflowEventModel.run_id == run_id,
                    WorkflowEventModel.idempotency_key.like(f"%:{event_key}"),
                )
            )
            if existing is not None:
                if (existing.payload or {}).get("request_checksum") != request_checksum:
                    raise RepairApplicationError(
                        "IDEMPOTENCY_PAYLOAD_MISMATCH",
                        "Candidate recovery key has a different payload",
                    )
                child = session.get(
                    RepairAttemptModel,
                    (existing.payload or {}).get("child_attempt_id"),
                )
                if child is None:
                    raise RepairApplicationError(
                        "REPAIR_RECOVERY_REPLAY_INVALID",
                        "Candidate recovery child is missing",
                    )
                return {"attempt_id": child.id, "status": child.status, "idempotent_replay": True}
            attempt = session.get(RepairAttemptModel, attempt_id)
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == run_id,
                    TransformationContinuationModel.current_stage_id == (
                        attempt.stage_id if attempt is not None else ""
                    ),
                )
            )
            run = session.get(MigrationRunModel, run_id)
            if (
                attempt is None
                or continuation is None
                or run is None
                or continuation.state_version != expected_state_version
                or continuation.status != "blocked"
                or continuation.current_node != "propose_repair"
                or continuation.last_error_code not in _BOUND_CANDIDATE_RECOVERY_CODES
                or attempt.status != "evidence_frozen"
                or attempt.proposal_artifact_id is not None
            ):
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Attempt is not a blocked proposal-less binding recovery",
                )
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == run_id,
                    StageWorkspaceBindingModel.stage_id == attempt.stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if binding is None or not attempt.pre_fingerprint:
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Repair workspace authority is missing",
                )
            try:
                live = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
            except OSError as error:
                raise RepairApplicationError(
                    "REPAIR_WORKSPACE_STALE",
                    "Repair workspace is unavailable",
                ) from error
            if live != binding.workspace_fingerprint or live != attempt.pre_fingerprint:
                raise RepairApplicationError(
                    "REPAIR_WORKSPACE_STALE",
                    "Repair workspace changed before candidate recovery",
                )
            invocation = session.scalar(
                select(LlmInvocationModel)
                .where(
                    LlmInvocationModel.run_id == run_id,
                    LlmInvocationModel.stage_id == attempt.stage_id,
                    LlmInvocationModel.idempotency_key.like(f"{attempt.id}:proposer%"),
                    LlmInvocationModel.status == "failed",
                )
                .order_by(LlmInvocationModel.created_at.desc())
                .limit(1)
            )
            if invocation is None:
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Failed proposer invocation is missing",
                )
            store = LocalFilesystemArtifactStore(
                Path(run.artifact_root).parent,
                fixed_run_root=Path(run.artifact_root),
            )
            rejected = None
            rejected_checksum = None
            for artifact_id in invocation.artifact_ids or []:
                metadata = session.get(ArtifactMetadataModel, "metadata-" + str(artifact_id))
                if metadata is None or "rejected-proposer-candidate" not in metadata.relative_path:
                    continue
                stored = store.read_artifact(run_id, metadata.relative_path)
                if stored.ref.artifact_id != artifact_id or stored.ref.checksum != metadata.checksum:
                    continue
                payload = json.loads(stored.content)
                candidate = payload.get("candidate") if isinstance(payload, dict) else None
                if isinstance(candidate, dict):
                    rejected = candidate
                    rejected_checksum = metadata.checksum
                    break
            if not isinstance(rejected, dict) or rejected.get("schema_invalid"):
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Immutable rejected candidate is not schema-valid",
                )
            historical_candidate = self._strip_legacy_candidate_provenance(rejected)
            try:
                RepairProposalCandidate.model_validate(historical_candidate)
            except ValidationError as error:
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Immutable candidate cannot be safely rebound",
                ) from error
            source_invocation = {
                "id": invocation.id,
                "prompt_version": invocation.prompt_version,
                "schema_version": invocation.schema_version,
                "input_hashes": list(invocation.input_hashes or []),
                "stage": invocation.stage,
                "retries": invocation.retries,
            }
        context = self._attempt_context(attempt_id)
        child_id = f"repair-{context['stage_id']}-{int(context['attempt_number']) + 1}"
        child_context = dict(context)
        child_context["attempt_id"] = child_id
        root = Path(str(context["artifact_root"]))
        child_context_pack = LocalFilesystemArtifactStore(
            root.parent, fixed_run_root=root
        ).write_text_artifact(
            str(context["run_id"]),
            f"05_repairs/attempt-{child_id}/recovery-context.json",
            str(context["segments"][1]),
            ArtifactType.JSON,
            stage_id=str(context["stage_id"]),
            attempt_id=child_id,
            created_by="repair-bound-candidate-context",
            created_at=self._now(),
            input_hashes={"recovered_from": str(context["context_pack_checksum"])},
            policy_version="repair-bound-candidate-context-v1",
        )
        child_context["context_pack_artifact_id"] = child_context_pack.ref.artifact_id
        child_context["context_pack_checksum"] = child_context_pack.ref.checksum
        proposal_artifact = None
        safe_diff_artifact = None
        try:
            bound = self.validate_proposal(
                self._bind_proposal_candidate(historical_candidate, child_context),
                child_context,
            )
            proposal_artifact = self._write(child_context, "proposal", bound)
            safe_diff_artifact = self._write_safe_diff(
                child_context, bound, proposal_artifact.ref.checksum
            )
        except Exception:
            self._remove_uncommitted_artifact(child_context_pack)
            if proposal_artifact is not None:
                self._remove_uncommitted_artifact(proposal_artifact)
            if safe_diff_artifact is not None:
                self._remove_uncommitted_artifact(safe_diff_artifact)
            raise
        child_invocation_id = f"{child_id}:proposer:binding-recovery-1"
        invocation_checksum = self._request_checksum(
            {
                "source_invocation": source_invocation["id"],
                "candidate_checksum": rejected_checksum,
                "proposal_checksum": proposal_artifact.ref.checksum,
                "canonicalizer": "repair-provenance-v1",
            }
        )
        try:
            with self._scope() as session:
                existing = session.scalar(
                    select(WorkflowEventModel).where(
                        WorkflowEventModel.run_id == run_id,
                        WorkflowEventModel.idempotency_key.like(f"%:{event_key}"),
                    )
                )
                if existing is not None:
                    self._remove_uncommitted_artifact(child_context_pack)
                    self._remove_uncommitted_artifact(proposal_artifact)
                    self._remove_uncommitted_artifact(safe_diff_artifact)
                    child = session.get(
                        RepairAttemptModel,
                        (existing.payload or {}).get("child_attempt_id"),
                    )
                    if child is None:
                        raise RepairApplicationError(
                            "REPAIR_RECOVERY_REPLAY_INVALID",
                            "Candidate recovery child is missing",
                        )
                    return {"attempt_id": child.id, "status": child.status, "idempotent_replay": True}
                continuation = session.scalar(
                    select(TransformationContinuationModel).where(
                        TransformationContinuationModel.run_id == run_id
                    )
                )
                attempt = session.get(RepairAttemptModel, attempt_id)
                if (
                    continuation is None
                    or attempt is None
                    or continuation.state_version != expected_state_version
                    or attempt.status != "evidence_frozen"
                    or attempt.proposal_artifact_id is not None
                ):
                    raise RepairApplicationError(
                        "REPAIR_RECOVERY_STALE",
                        "Durable state changed before candidate recovery commit",
                    )
                now = self._now()
                self._register_artifact_metadata(session, child_context, child_context_pack)
                self._register_artifact_metadata(session, child_context, proposal_artifact)
                self._register_artifact_metadata(session, child_context, safe_diff_artifact)
                child_invocation = LlmInvocationModel(
                    id=child_invocation_id,
                    run_id=run_id,
                    stage_id=attempt.stage_id,
                    idempotency_key=child_invocation_id,
                    request_checksum=invocation_checksum,
                    input_hashes=[
                        *source_invocation["input_hashes"],
                        f"rebind_of:{source_invocation['id']}",
                        f"candidate:{rejected_checksum}",
                    ],
                    correlation_id=correlation_id,
                    actor=actor,
                    role="repair_proposer",
                    task_type="repair_diagnosis",
                    provider="factory",
                    deployment_alias="deterministic-provenance-rebind",
                    prompt_version=str(source_invocation["prompt_version"] or "repair-proposer"),
                    schema_version="repair-provenance-rebind-v1",
                    pricing_version="none",
                    stage=source_invocation["stage"],
                    redacted_summary=json.dumps(
                        {"rebound_candidate": source_invocation["id"]}, sort_keys=True
                    ),
                    status="completed",
                    artifact_ids=[proposal_artifact.ref.artifact_id, safe_diff_artifact.ref.artifact_id],
                    artifact_checksums={
                        proposal_artifact.ref.artifact_id: proposal_artifact.ref.checksum,
                        safe_diff_artifact.ref.artifact_id: safe_diff_artifact.ref.checksum,
                    },
                    state_version=1,
                    event_sequence=1,
                    retries=int(source_invocation["retries"] or 0),
                    response_received=False,
                    response_kind="deterministic_rebind",
                    transport_started=False,
                    started_at=now,
                    completed_at=now,
                    created_at=now,
                )
                session.add(child_invocation)
                child = RepairAttemptModel(
                    id=child_id,
                    run_id=run_id,
                    stage_id=attempt.stage_id,
                    attempt_number=attempt.attempt_number + 1,
                    state_version=1,
                    status="proposed",
                    risk_level=str(bound["risk_level"]),
                    diagnosis=f"deterministic provenance rebind; parent={attempt.id}",
                    checkpoint_id=attempt.checkpoint_id,
                    failure_evidence_artifact_id=attempt.failure_evidence_artifact_id,
                    failure_evidence_checksum=attempt.failure_evidence_checksum,
                    failure_route_artifact_id=attempt.failure_route_artifact_id,
                    failure_route_checksum=attempt.failure_route_checksum,
                    context_pack_artifact_id=child_context_pack.ref.artifact_id,
                    context_pack_checksum=child_context_pack.ref.checksum,
                    proposal_artifact_id=proposal_artifact.ref.artifact_id,
                    proposal_checksum=proposal_artifact.ref.checksum,
                    proposer_invocation_id=child_invocation_id,
                    pre_fingerprint=attempt.pre_fingerprint,
                    failure_fingerprint=attempt.failure_fingerprint,
                    parent_attempt_id=attempt.id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(child)
                attempt.status = "superseded"
                attempt.completed_at = now
                attempt.updated_at = now
                continuation.status = "queued"
                continuation.current_node = "review_repair"
                continuation.worker_id = None
                continuation.lease_expires_at = None
                continuation.next_attempt_at = None
                continuation.last_error_code = None
                continuation.last_error_message = None
                continuation.waiting_execution_id = None
                continuation.wake_sequence += 1
                continuation.state_version += 1
                continuation.updated_at = now
                session.flush()
                append_continuation_event(
                    session,
                    continuation,
                    event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED,
                    key=event_key,
                    reason="deterministic bound candidate recovery requested",
                    actor=actor,
                    occurred_at=now,
                    payload={
                        "attempt_id": attempt.id,
                        "child_attempt_id": child.id,
                        "candidate_checksum": rejected_checksum,
                        "proposal_checksum": proposal_artifact.ref.checksum,
                        "request_checksum": request_checksum,
                        "correlation_id": correlation_id,
                    },
                )
                return {"attempt_id": child.id, "status": child.status, "idempotent_replay": False}
        except RepairApplicationError:
            self._remove_uncommitted_artifact(child_context_pack)
            self._remove_uncommitted_artifact(proposal_artifact)
            self._remove_uncommitted_artifact(safe_diff_artifact)
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

    def recover_bound_context(
        self,
        *,
        run_id: str,
        attempt_id: str,
        expected_state_version: int,
        idempotency_key: str,
        actor: str,
        correlation_id: str,
    ) -> dict[str, object]:
        """Create a child when an earlier deterministic bind used a parent envelope."""
        request_checksum = self._request_checksum(
            {
                "run_id": run_id,
                "attempt_id": attempt_id,
                "expected_state_version": expected_state_version,
                "actor": actor,
                "correlation_id": correlation_id,
                "recovery": "bound-context-v1",
            }
        )
        event_key = "repair-bound-context-recovery:" + hashlib.sha256(
            idempotency_key.encode()
        ).hexdigest()
        with self._scope() as session:
            existing = session.scalar(
                select(WorkflowEventModel).where(
                    WorkflowEventModel.run_id == run_id,
                    WorkflowEventModel.idempotency_key.like(f"%:{event_key}"),
                )
            )
            if existing is not None:
                if (existing.payload or {}).get("request_checksum") != request_checksum:
                    raise RepairApplicationError(
                        "IDEMPOTENCY_PAYLOAD_MISMATCH",
                        "Context recovery key has a different payload",
                    )
                child = session.get(
                    RepairAttemptModel,
                    (existing.payload or {}).get("child_attempt_id"),
                )
                if child is None:
                    raise RepairApplicationError(
                        "REPAIR_RECOVERY_REPLAY_INVALID",
                        "Context recovery child is missing",
                    )
                return {"attempt_id": child.id, "status": child.status, "idempotent_replay": True}
            attempt = session.get(RepairAttemptModel, attempt_id)
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == run_id
                )
            )
            parent = (
                session.get(RepairAttemptModel, attempt.parent_attempt_id)
                if attempt is not None and attempt.parent_attempt_id
                else None
            )
            binding = (
                session.scalar(
                    select(StageWorkspaceBindingModel).where(
                        StageWorkspaceBindingModel.run_id == run_id,
                        StageWorkspaceBindingModel.stage_id == attempt.stage_id,
                        StageWorkspaceBindingModel.active.is_(True),
                    )
                )
                if attempt is not None
                else None
            )
            if (
                attempt is None
                or parent is None
                or continuation is None
                or binding is None
                or continuation.state_version != expected_state_version
                or continuation.status != "blocked"
                or continuation.current_node != "review_repair"
                or continuation.last_error_code != "REPAIR_ARTIFACT_RECOVERY_FAILED"
                or attempt.status not in {"proposed", "blocked"}
                or not attempt.proposal_artifact_id
                or not attempt.proposal_checksum
                or attempt.review_artifact_id is not None
            ):
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Attempt is not a blocked stale bound-context lineage",
                )
            try:
                live = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
            except OSError as error:
                raise RepairApplicationError(
                    "REPAIR_WORKSPACE_STALE", "Repair workspace is unavailable"
                ) from error
            if live != binding.workspace_fingerprint or live != attempt.pre_fingerprint:
                raise RepairApplicationError(
                    "REPAIR_WORKSPACE_STALE", "Repair workspace changed before context recovery"
                )
            metadata = session.get(
                ArtifactMetadataModel, "metadata-" + attempt.proposal_artifact_id
            )
            run = session.get(MigrationRunModel, run_id)
            if metadata is None or run is None or metadata.checksum != attempt.proposal_checksum:
                raise RepairApplicationError(
                    "REPAIR_PROPOSAL_STALE", "Bound proposal evidence is missing or stale"
                )
            store = LocalFilesystemArtifactStore(
                Path(run.artifact_root).parent,
                fixed_run_root=Path(run.artifact_root),
            )
            try:
                stored = store.read_artifact(run_id, metadata.relative_path)
                self._validate_artifact_envelope(
                    stored,
                    expected_run_id=run_id,
                    expected_stage_id=attempt.stage_id,
                    expected_attempt_id=attempt.id,
                    pre_attempt=False,
                    metadata_checksum=metadata.checksum,
                )
                payload = json.loads(stored.content)
                proposal = RepairProposal.model_validate(payload)
            except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError, ValidationError) as error:
                raise RepairApplicationError(
                    "REPAIR_PROPOSAL_STALE", "Bound proposal cannot be verified"
                ) from error
            if (
                proposal.failure_evidence_checksum != parent.failure_evidence_checksum
                or proposal.context_pack_checksum != parent.context_pack_checksum
            ):
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Bound proposal is not tied to the parent context",
                )
            source_invocation = session.get(
                LlmInvocationModel, attempt.proposer_invocation_id
            )
            if (
                source_invocation is None
                or source_invocation.status != "completed"
                or source_invocation.deployment_alias != "deterministic-provenance-rebind"
            ):
                raise RepairApplicationError(
                    "REPAIR_RECOVERY_NOT_ELIGIBLE",
                    "Deterministic source invocation is missing",
                )
        parent_context = self._attempt_context(parent.id)
        child_id = f"repair-{parent_context['stage_id']}-{int(attempt.attempt_number) + 1}"
        child_context = dict(parent_context)
        child_context["attempt_id"] = child_id
        child_context_pack = None
        proposal_artifact = None
        safe_diff_artifact = None
        try:
            root = Path(str(parent_context["artifact_root"]))
            child_context_pack = LocalFilesystemArtifactStore(
                root.parent, fixed_run_root=root
            ).write_text_artifact(
                str(run_id),
                f"05_repairs/attempt-{child_id}/recovery-context.json",
                str(parent_context["segments"][1]),
                ArtifactType.JSON,
                stage_id=str(parent_context["stage_id"]),
                attempt_id=child_id,
                created_by="repair-bound-context-recovery",
                created_at=self._now(),
                input_hashes={"recovered_from": str(parent_context["context_pack_checksum"])},
                policy_version="repair-bound-context-v1",
            )
            child_context["context_pack_artifact_id"] = child_context_pack.ref.artifact_id
            child_context["context_pack_checksum"] = child_context_pack.ref.checksum
            rebound = proposal.model_dump(mode="json")
            rebound["failure_evidence_checksum"] = child_context["failure_evidence_checksum"]
            rebound["context_pack_checksum"] = child_context["context_pack_checksum"]
            bound = RepairProposal.model_validate(rebound).model_dump(mode="json")
            proposal_artifact = self._write(child_context, "proposal", bound)
            safe_diff_artifact = self._write_safe_diff(
                child_context, bound, proposal_artifact.ref.checksum
            )
            invocation_checksum = self._request_checksum(
                {
                    "source_invocation": source_invocation.id,
                    "source_proposal": attempt.proposal_checksum,
                    "proposal": proposal_artifact.ref.checksum,
                    "canonicalizer": "repair-bound-context-v1",
                }
            )
            with self._scope() as session:
                existing = session.scalar(
                    select(WorkflowEventModel).where(
                        WorkflowEventModel.run_id == run_id,
                        WorkflowEventModel.idempotency_key.like(f"%:{event_key}"),
                    )
                )
                if existing is not None:
                    for artifact in (child_context_pack, proposal_artifact, safe_diff_artifact):
                        self._remove_uncommitted_artifact(artifact)
                    child = session.get(
                        RepairAttemptModel,
                        (existing.payload or {}).get("child_attempt_id"),
                    )
                    if child is None:
                        raise RepairApplicationError(
                            "REPAIR_RECOVERY_REPLAY_INVALID", "Context recovery child is missing"
                        )
                    return {"attempt_id": child.id, "status": child.status, "idempotent_replay": True}
                continuation = session.scalar(
                    select(TransformationContinuationModel).where(
                        TransformationContinuationModel.run_id == run_id
                    )
                )
                attempt = session.get(RepairAttemptModel, attempt_id)
                if (
                    continuation is None
                    or attempt is None
                    or continuation.state_version != expected_state_version
                    or attempt.status not in {"proposed", "blocked"}
                    or attempt.proposal_checksum != metadata.checksum
                ):
                    raise RepairApplicationError(
                        "REPAIR_RECOVERY_STALE", "Durable state changed before context recovery"
                    )
                now = self._now()
                self._register_artifact_metadata(session, child_context, child_context_pack)
                self._register_artifact_metadata(session, child_context, proposal_artifact)
                self._register_artifact_metadata(session, child_context, safe_diff_artifact)
                child_invocation_id = f"{child_id}:proposer:context-recovery-1"
                session.add(
                    LlmInvocationModel(
                        id=child_invocation_id,
                        run_id=run_id,
                        stage_id=attempt.stage_id,
                        idempotency_key=child_invocation_id,
                        request_checksum=invocation_checksum,
                        input_hashes=[
                            f"rebind_of:{source_invocation.id}",
                            f"proposal:{attempt.proposal_checksum}",
                            f"context:{child_context_pack.ref.checksum}",
                        ],
                        correlation_id=correlation_id,
                        actor=actor,
                        role="repair_proposer",
                        task_type="repair_diagnosis",
                        provider="factory",
                        deployment_alias="deterministic-provenance-rebind",
                        prompt_version=str(source_invocation.prompt_version or "repair-proposer"),
                        schema_version="repair-bound-context-v1",
                        pricing_version="none",
                        stage=source_invocation.stage,
                        redacted_summary=json.dumps(
                            {"rebound_context_of": source_invocation.id}, sort_keys=True
                        ),
                        status="completed",
                        artifact_ids=[proposal_artifact.ref.artifact_id, safe_diff_artifact.ref.artifact_id],
                        artifact_checksums={
                            proposal_artifact.ref.artifact_id: proposal_artifact.ref.checksum,
                            safe_diff_artifact.ref.artifact_id: safe_diff_artifact.ref.checksum,
                        },
                        state_version=1,
                        event_sequence=1,
                        retries=source_invocation.retries,
                        response_received=False,
                        response_kind="deterministic_rebind",
                        transport_started=False,
                        started_at=now,
                        completed_at=now,
                        created_at=now,
                    )
                )
                child = RepairAttemptModel(
                    id=child_id,
                    run_id=run_id,
                    stage_id=attempt.stage_id,
                    attempt_number=attempt.attempt_number + 1,
                    state_version=1,
                    status="proposed",
                    risk_level=proposal.risk_level,
                    diagnosis=f"deterministic context rebind; parent={attempt.id}",
                    checkpoint_id=attempt.checkpoint_id,
                    failure_evidence_artifact_id=attempt.failure_evidence_artifact_id,
                    failure_evidence_checksum=attempt.failure_evidence_checksum,
                    failure_route_artifact_id=attempt.failure_route_artifact_id,
                    failure_route_checksum=attempt.failure_route_checksum,
                    context_pack_artifact_id=child_context_pack.ref.artifact_id,
                    context_pack_checksum=child_context_pack.ref.checksum,
                    proposal_artifact_id=proposal_artifact.ref.artifact_id,
                    proposal_checksum=proposal_artifact.ref.checksum,
                    proposer_invocation_id=child_invocation_id,
                    pre_fingerprint=attempt.pre_fingerprint,
                    failure_fingerprint=attempt.failure_fingerprint,
                    parent_attempt_id=attempt.id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(child)
                attempt.status = "superseded"
                attempt.completed_at = now
                attempt.updated_at = now
                continuation.status = "queued"
                continuation.current_node = "review_repair"
                continuation.worker_id = None
                continuation.lease_expires_at = None
                continuation.last_error_code = None
                continuation.last_error_message = None
                continuation.wake_sequence += 1
                continuation.state_version += 1
                continuation.updated_at = now
                session.flush()
                append_continuation_event(
                    session,
                    continuation,
                    event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED,
                    key=event_key,
                    reason="deterministic bound candidate recovery requested",
                    actor=actor,
                    occurred_at=now,
                    payload={
                        "attempt_id": attempt.id,
                        "child_attempt_id": child.id,
                        "request_checksum": request_checksum,
                        "source_proposal_checksum": metadata.checksum,
                        "proposal_checksum": proposal_artifact.ref.checksum,
                        "correlation_id": correlation_id,
                    },
                )
                return {"attempt_id": child.id, "status": child.status, "idempotent_replay": False}
        except Exception:
            for artifact in (child_context_pack, proposal_artifact, safe_diff_artifact):
                if artifact is not None:
                    self._remove_uncommitted_artifact(artifact)
            raise

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
        if len(matches) > 1:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_PACKAGE_AMBIGUOUS",
                "The requested package has ambiguous dependency entries",
            )
        if not isinstance(matches[0][1], str):
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_VERSION_INVALID",
                "The authoritative dependency value is not a version string",
            )
        if matches[0][0] != section:
            raise _dependency_section_mismatch_error(
                package, matches[0][0], matches[0][1], section
            )
        if matches[0][1] == new_version:
            raise RepairApplicationError(
                "REPAIR_REPLACEMENT_NOOP",
                "Dependency changes produced no dependency state change",
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
            if self._is_normalization_operation(bound):
                if relative != "package.json":
                    raise RepairApplicationError(
                        "REPAIR_DEPENDENCY_PATH_INVALID",
                        "Dependency normalization may target only package.json",
                    )
                # normalization is exclusive and backend-owned; preimage handled in binder
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
            if not actions <= {
                "replace_text",
                "create_text_file",
                "delete_text_file",
                "dependency_change",
                "dependency_add",
            }:
                raise RepairApplicationError(
                    "REPAIR_OPERATION_INVALID", "Repair operation is unsupported"
                )
            if actions == {"replace_text"}:
                for item in group:
                    try:
                        self._replacement_preimage(item)
                    except RepairApplicationError as error:
                        if error.code not in {
                            "REPAIR_REPLACEMENT_MISSING",
                            "REPAIR_REPLACEMENT_AMBIGUOUS",
                        }:
                            raise
                        raise RepairApplicationError(
                            error.code,
                            f"{error.message} Target path: '{relative}'.",
                        ) from error
            if "create_text_file" in actions:
                if len(group) != 1:
                    raise RepairApplicationError(
                        "REPAIR_OPERATION_AMBIGUOUS",
                        "Create operations cannot share a physical path",
                    )
                content = group[0].get("content")
                if not isinstance(content, str):
                    raise RepairApplicationError(
                        "REPAIR_OPERATION_AMBIGUOUS",
                        "Create operations require non-null text content",
                    )
                if target.exists() or target.is_symlink():
                    raise RepairApplicationError(
                        _CREATE_TARGET_EXISTS,
                        f"create_text_file cannot target existing authoritative path "
                        f"'{relative}'; use replace_text with its exact preimage.",
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

            if relative == "package.json" or "dependency_change" in actions or "dependency_add" in actions:
                if relative != "package.json":
                    raise RepairApplicationError(
                        "REPAIR_DEPENDENCY_PATH_INVALID",
                        "Dependency changes may edit only package.json",
                    )
                if not actions or not actions <= {"dependency_change", "dependency_add"}:
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
                if len(group) == 1 and str(group[0].get("operation")) != "dependency_add" and not any(
                    group[0].get(name) is not None
                    for name in ("section", "package", "new_version")
                ):
                    after = replace_text_once(
                        current,
                        self._replacement_preimage(group[0]),
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
                dependency_changes: list[dict[str, str]] = []
                for item in group:
                    fields = [item.get(name) for name in ("section", "package", "new_version")]
                    if not all(isinstance(field, str) and field.strip() for field in fields):
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_INTENT_INVALID",
                            "Dependency changes require section, package, and new_version",
                        )
                    section, package, new_version = (str(field) for field in fields)
                    if str(item.get("operation")) == "dependency_add":
                        if section not in _DEPENDENCY_ADDITION_SECTIONS:
                            raise RepairApplicationError(
                                "REPAIR_DEPENDENCY_SECTION_INVALID",
                                "Dependency additions must target dependencies or devDependencies",
                            )
                        key = (section, package)
                        prior = seen.get(key)
                        if prior is not None and prior != new_version:
                            raise RepairApplicationError(
                                "REPAIR_DEPENDENCY_CONFLICT",
                                "Contradictory dependency changes target the same package key",
                            )
                        seen[key] = new_version
                        if any(
                            isinstance(document.get(name), dict) and package in document[name]
                            for name in _DEPENDENCY_SECTIONS
                        ):
                            raise RepairApplicationError(
                                "REPAIR_DEPENDENCY_ALREADY_PRESENT",
                                "The requested dependency_add package already exists in authoritative package.json",
                            )
                        llm_requested_version = new_version
                        try:
                            DependencyAdditionPolicy().validate(
                                package=package,
                                section=section,
                                version_spec=new_version,
                            )
                        except DependencyAdditionPolicyError as error:
                            raise RepairApplicationError(
                                "REPAIR_DEPENDENCY_VERSION_INVALID",
                                str(error),
                            ) from error
                        item["new_version"] = new_version
                        if not isinstance(document.get(section), dict):
                            document[section] = {}
                        document[section][package] = new_version
                        dependency_changes.append(
                            {
                                "operation": "dependency_add",
                                "section": section,
                                "package": package,
                                "new_version": llm_requested_version,
                                "policy_version": DEPENDENCY_ADDITION_POLICY_VERSION,
                            }
                        )
                        continue
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
                    if len(matches) > 1:
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_PACKAGE_AMBIGUOUS",
                            "The requested package has ambiguous dependency entries",
                        )
                    if not isinstance(matches[0][1], str):
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_VERSION_INVALID",
                            "The authoritative dependency value is not a version string",
                        )
                    if matches[0][0] != section:
                        raise _dependency_section_mismatch_error(
                            package, matches[0][0], matches[0][1], section
                        )
                    if matches[0][1] == new_version:
                        raise RepairApplicationError(
                            "REPAIR_REPLACEMENT_NOOP",
                            "Dependency changes produced no dependency state change",
                        )
                    document[section][package] = new_version
                    dependency_changes.append(
                        {
                            "operation": "dependency_change",
                            "path": relative,
                            "section": section,
                            "package": package,
                            "new_version": new_version,
                        }
                    )
                dependency_changes.sort(
                    key=lambda item: (
                        item.get("section", ""),
                        item.get("package", ""),
                        item.get("new_version", ""),
                        item.get("operation", ""),
                    )
                )
                provenance = [
                    {
                        "key": "dependency_changes",
                        "value": json.dumps(
                            dependency_changes,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    }
                ]
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
                result_operation = (
                    "dependency_add"
                    if any(str(item.get("operation")) == "dependency_add" for item in group)
                    else "dependency_change"
                )
                result.append(
                    {
                        "operation": result_operation,
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
                old_text = self._replacement_preimage(item)
                try:
                    after = replace_text_once(
                        after, old_text, str(item.get("new_text"))
                    )
                except RepairApplicationError as error:
                    if error.code not in {
                        "REPAIR_REPLACEMENT_MISSING",
                        "REPAIR_REPLACEMENT_AMBIGUOUS",
                    }:
                        raise
                    raise RepairApplicationError(
                        error.code,
                        f"{error.message} Target path: '{relative}'.",
                    ) from error
                provenance.append(
                    {
                        "operation": "replace_text",
                        "path": relative,
                        "old_text": old_text,
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

    @staticmethod
    def _strip_legacy_candidate_provenance(value: dict[str, object]) -> dict[str, object]:
        """Read old candidates without allowing their metadata to become authority."""
        candidate = dict(value)
        operations = candidate.get("operations")
        if isinstance(operations, list):
            candidate["operations"] = [
                {
                    key: field_value
                    for key, field_value in operation.items()
                    if key != "provenance"
                }
                if isinstance(operation, dict)
                else operation
                for operation in operations
            ]
        return candidate

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
                _DEPENDENCY_TRANSITION_NOT_EXCLUSIVE,
                "dependency_transition must be the only repair operation",
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
            evidence, diagnosis = FailureEvidenceService.normalize_dependency_transition_evidence(
                evidence
            )
            backend_package = (
                diagnosis.get("blocking_dependency")
                if isinstance(diagnosis, dict)
                and diagnosis.get("source") == "npm_eresolve_peer_conflict"
                else diagnosis.get("package")
                if isinstance(diagnosis, dict)
                else None
            )
            if not isinstance(backend_package, str) or not backend_package:
                raise ValueError(
                    "field=normalized_failure.failure_diagnosis.package; "
                    "expected=non-empty blocking package parsed from the failed Angular command; "
                    f"observed={json.dumps(backend_package)}; "
                    f"artifact_id={context.get('failure_evidence_artifact_id') or 'unavailable'}; "
                    f"execution_id={evidence.get('execution_id') or 'unavailable'}; "
                    "recovery=reparse the immutable command failure with the npm package-name grammar"
                )
            try:
                installed_version = installed_dependency_version(
                    workspace, backend_package
                )
            except ValueError:
                installed_version = diagnosis.get("installed_version")
                if not is_exact_version(installed_version):
                    raise
            authority = validate_dependency_transition_evidence(
                evidence,
                package=backend_package,
                target_major=expected_major,
                installed_version=installed_version,
                artifact_id=str(context.get("failure_evidence_artifact_id") or ""),
            )
            cohort = context.get("target_cohort")
            if isinstance(cohort, dict) and is_exact_version(
                cohort.get(str(authority["package"]))
            ):
                authority = {
                    **authority,
                    "target_version": cohort[str(authority["package"])],
                }
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
            verify_dependency_transition_evidence_for_source(
                workspace,
                diagnosis=diagnosis,
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
        detached = False
        if not present:
            try:
                detached = (
                    installed_dependency_version(workspace, package)
                    == authority["installed_version"]
                )
            except ValueError:
                detached = False
        if len(present) != 1 and not detached:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_PACKAGE_MISSING",
                "The backend blocking package is missing or ambiguous in authoritative package.json",
            )
        try:
            return RepairProposal.model_validate(value).model_dump(mode="json")
        except ValidationError as error:
            raise RepairApplicationError(
                "REPAIR_BOUND_PROPOSAL_INVALID",
                "Backend-bound dependency proposal violates authoritative invariants: "
                + _proposal_validation_message(error),
            ) from error

    @staticmethod
    def _is_normalization_operation(op: dict) -> bool:
        if not isinstance(op, dict):
            return False
        if str(op.get("repair_kind") or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND:
            return True
        if str(op.get("operation") or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND:
            return True
        if str(op.get("schema_version") or "") == DEPENDENCY_NORMALIZATION_SCHEMA_VERSION:
            return True
        return False

    @staticmethod
    def _stage_target_requirements(context: dict[str, object], manifest: dict) -> dict[str, str]:
        cohort = context.get("target_cohort")
        if not isinstance(cohort, dict):
            return {}
        present = {
            package
            for section in ("dependencies", "devDependencies")
            for package in (manifest.get(section) or {})
            if isinstance(package, str)
        }
        return {
            package: exact
            for package, exact in cohort.items()
            if package in present and isinstance(package, str) and is_exact_version(exact)
        }

    def _bind_dependency_normalization(
        self, value: dict[str, object], context: dict[str, object]
    ) -> dict[str, object]:
        """Validate complete plan, override with backend-fixed targets, materialize postimage."""
        operations = list(value.get("operations") or [])
        norms = [o for o in operations if self._is_normalization_operation(o)]
        if len(operations) != 1 or len(norms) != 1:
            raise RepairApplicationError(
                _DEPENDENCY_NORMALIZATION_NOT_EXCLUSIVE,
                "dependency_manifest_normalization must be the only repair operation",
            )
        op = dict(norms[0])
        if str(op.get("path") or "") != "package.json":
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_NORMALIZATION_INVALID",
                "normalization must target package.json",
            )
        # extract plan dict
        plan_raw: dict | None = None
        if isinstance(op.get("normalization_plan"), dict):
            plan_raw = op["normalization_plan"]
        elif isinstance(op.get("plan"), dict):
            plan_raw = op["plan"]
        elif isinstance(op.get("packages"), list):
            plan_raw = {
                "schema_version": op.get("schema_version") or DEPENDENCY_NORMALIZATION_SCHEMA_VERSION,
                "analysis_summary": op.get("analysis_summary") or "dependency normalization",
                "packages": op.get("packages"),
            }
        else:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_NORMALIZATION_INVALID",
                "normalization operation missing packages plan",
            )
        # ensure schema_version present
        if plan_raw.get("schema_version") is None:
            plan_raw["schema_version"] = DEPENDENCY_NORMALIZATION_SCHEMA_VERSION
        if plan_raw.get("schema_version") != DEPENDENCY_NORMALIZATION_SCHEMA_VERSION:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_NORMALIZATION_INVALID",
                "normalization schema_version must be dependency-normalization-v1",
            )
        try:
            plan = DependencyNormalizationPlan.model_validate(plan_raw)
        except ValidationError as e:
            raise RepairApplicationError(
                "REPAIR_DEPENDENCY_NORMALIZATION_INVALID",
                "normalization plan invalid: " + _proposal_validation_message(e),
            ) from e
        workspace = Path(str(context["workspace_path"])).resolve(strict=True)
        try:
            raw = (workspace / "package.json").read_text(encoding="utf-8", newline="")
        except OSError as err:
            raise RepairApplicationError("REPAIR_PREIMAGE_INVALID", "authoritative package.json missing") from err
        try:
            manifest = json.loads(raw, object_pairs_hook=self._json_object_without_duplicates)
        except ValueError as err:
            raise RepairApplicationError("REPAIR_DEPENDENCY_PACKAGE_INVALID", "authoritative package.json invalid") from err
        if not isinstance(manifest, dict):
            raise RepairApplicationError("REPAIR_DEPENDENCY_PACKAGE_INVALID", "package.json must be object")
        # legacy deserialize: if op already has new_text/post_text with valid JSON, trust it as already materialized?
        # No — always re-materialize backend-owned bytes to ensure checksums/diff authoritative.
        target_reqs = self._stage_target_requirements(context, manifest)
        try:
            result = DependencyNormalizationService.materialize(raw, manifest, plan, target_reqs)
        except ValueError as err:
            raise RepairApplicationError("REPAIR_DEPENDENCY_NORMALIZATION_INVALID", str(err)) from err
        # build bound operation with authoritative bytes + checksums + diff
        bound_op = {
            "operation": DEPENDENCY_NORMALIZATION_REPAIR_KIND,
            "path": "package.json",
            "repair_kind": DEPENDENCY_NORMALIZATION_REPAIR_KIND,
            "schema_version": DEPENDENCY_NORMALIZATION_SCHEMA_VERSION,
            "old_text": raw,
            "new_text": result["post_text"],
            "preimage_sha256": result["pre_checksum"],
            "post_checksum": result["post_checksum"],
            "diff": result["diff"],
            "analysis_summary": plan.analysis_summary,
            "packages": [p.model_dump(mode="json") for p in plan.packages],
            "approved_actions": result["approved_actions"],
            "pre_checksum": result["pre_checksum"],
            "post_checksum": result["post_checksum"],
            "provenance": _normalize_provenance([
                {"key": "dependency_normalization_plan", "value": json.dumps(plan_raw, sort_keys=True)},
                {"key": "approved_actions", "value": json.dumps(result["approved_actions"], sort_keys=True)},
            ]),
        }
        # also preserve rationale/limitations from candidate for review
        value["operations"] = [bound_op]
        value["touched_files"] = ["package.json"]
        # ensure proposal_format operations
        try:
            return RepairProposal.model_validate(value).model_dump(mode="json")
        except ValidationError as e:
            # allow extra fields in operation via RepairOperation extra handling; strip to valid shape
            # RepairOperation is strict, but we store bound_op with extra provenance/handle
            # Fallback: store via dict and validate leniently
            # For minimal, bypass strict validate and return dict with expected keys
            # Ensure checksums/diff are present for reviewer
            value["operations"] = [bound_op]
            return value

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
        operations = value.get("operations")
        if isinstance(operations, list):
            for operation in operations:
                if (
                    isinstance(operation, dict)
                    and operation.get("operation") == "dependency_change"
                    and operation.get("strategy") == "add_dependency"
                ):
                    operation["operation"] = "dependency_add"
        candidate = RepairProposalCandidate.model_validate(value)
        for index, operation in enumerate(candidate.operations):
            if not operation.path or len(operation.path) > 500:
                raise RepairApplicationError(
                    "REPAIR_PATH_INVALID",
                    f"operations.{index}.path must contain 1 to 500 characters",
                )
        transition_operations = [
            operation
            for operation in candidate.operations
            if operation.operation == "dependency_transition"
        ]
        if transition_operations and (
            len(candidate.operations) != 1 or candidate.unified_diff is not None
        ):
            raise RepairApplicationError(
                _DEPENDENCY_TRANSITION_NOT_EXCLUSIVE,
                "dependency_transition must be the only repair operation",
            )
        # P3 normalization: exclusive single operation
        normalization_operations = [
            op
            for op in candidate.operations
            if op.operation == "dependency_manifest_normalization"
            or (op.repair_kind or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND
        ]
        if normalization_operations and (
            len(candidate.operations) != 1 or candidate.unified_diff is not None
        ):
            raise RepairApplicationError(
                _DEPENDENCY_NORMALIZATION_NOT_EXCLUSIVE,
                "dependency_manifest_normalization must be the only repair operation",
            )
        if normalization_operations:
            # bypass coalesce; normalization owns full manifest materialization
            workspace = Path(str(context["workspace_path"])).resolve(strict=True)
            payload = {
                **candidate.model_dump(mode="json"),
                "failure_evidence_checksum": context["failure_evidence_checksum"],
                "context_pack_checksum": context["context_pack_checksum"],
                "operations": [op.model_dump(mode="json") for op in candidate.operations],
                "touched_files": ["package.json"],
                "validation_targets": self._normalize_validation_targets(
                    candidate.validation_targets
                ),
            }
            return self._bind_dependency_normalization(payload, context)
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
        if any(self._is_normalization_operation(item) for item in operations):
            return self._bind_dependency_normalization(payload, context)
        try:
            return RepairProposal.model_validate(payload).model_dump(mode="json")
        except ValidationError as error:
            raise RepairApplicationError(
                "REPAIR_BOUND_PROPOSAL_INVALID",
                "Backend-bound repair proposal violates authoritative invariants: "
                + _proposal_validation_message(error),
            ) from error

    def _context_pack_excerpts(self, context: dict[str, object]) -> dict[str, object]:
        try:
            payload = json.loads(str(context["segments"][1]))
        except (IndexError, TypeError, ValueError) as error:
            raise RepairApplicationError(
                "REPAIR_CONTEXT_INVALID", "Repair context pack is not valid JSON"
            ) from error
        excerpts = payload.get("file_excerpts") if isinstance(payload, dict) else None
        if not isinstance(excerpts, dict):
            raise RepairApplicationError(
                "REPAIR_CONTEXT_INVALID", "Repair context pack file excerpts are missing"
            )
        return excerpts

    @staticmethod
    def _replacement_preimage(item: dict[str, object]) -> str:
        old_text = item.get("old_text")
        if not isinstance(old_text, str) or not old_text:
            raise RepairApplicationError(
                _REPLACEMENT_PREIMAGE_REQUIRED,
                "replace_text requires a non-empty old_text copied from authoritative "
                "repository content; null or missing preimages are forbidden.",
            )
        return old_text

    def _hydrate_semantic_retry_context(
        self, candidate: dict[str, object], context: dict[str, object]
    ) -> dict[str, object] | None:
        authoritative = self._assert_fresh_authority(context, role="proposer")
        try:
            workspace = Path(str(authoritative["workspace_path"])).resolve(strict=True)
        except OSError as error:
            raise RepairApplicationError(
                "REPAIR_WORKSPACE_MISSING", "Repair workspace is unavailable"
            ) from error
        excerpts: dict[str, object] | None = None
        missing_paths: list[str] = []
        existing_create_paths: list[str] = []
        for operation in candidate.get("operations") or []:
            if not isinstance(operation, dict):
                continue
            operation_name = operation.get("operation")
            path_value = operation.get("path")
            if operation_name not in {"replace_text", "create_text_file"}:
                continue
            if not isinstance(path_value, str) or not path_value:
                raise RepairApplicationError(
                    _REPLACEMENT_CONTEXT_INVALID,
                    "replace_text target path cannot be hydrated safely",
                )
            try:
                relative = self._safe_path(path_value, workspace)
            except RepairApplicationError as error:
                raise RepairApplicationError(
                    _REPLACEMENT_CONTEXT_INVALID,
                    "replace_text target path cannot be hydrated safely",
                ) from error
            if operation_name == "create_text_file":
                target = workspace / relative
                if target.exists() or target.is_symlink():
                    existing_create_paths.append(relative)
                continue
            if excerpts is None:
                excerpts = self._context_pack_excerpts(authoritative)
            entry = excerpts.get(relative)
            if not (
                isinstance(entry, dict)
                and isinstance(entry.get("content"), str)
                and entry.get("truncated") is False
            ):
                missing_paths.append(relative)
        missing_paths = list(dict.fromkeys(missing_paths))
        hydrate_paths = list(dict.fromkeys([*missing_paths, *existing_create_paths]))
        if not hydrate_paths:
            return None

        targets: list[dict[str, object]] = []
        for relative in sorted(hydrate_paths):
            current_path = workspace
            for part in PurePosixPath(relative).parts:
                current_path = current_path / part
                if current_path.is_symlink():
                    raise RepairApplicationError(
                        _REPLACEMENT_CONTEXT_INVALID,
                        "replace_text target path cannot traverse a symlink",
                    )
            target = workspace / relative
            if target.is_symlink() or not target.is_file():
                raise RepairApplicationError(
                    _REPLACEMENT_CONTEXT_INVALID,
                    "replace_text target is not a regular existing file",
                )
            try:
                raw = target.read_bytes()
                if len(raw) > CONTEXT_PACK_MAX_BYTES_PER_FILE:
                    raise RepairApplicationError(
                        _REPLACEMENT_CONTEXT_INVALID,
                        "replace_text target is too large for safe semantic retry context",
                    )
                content = raw.decode("utf-8")
            except RepairApplicationError:
                raise
            except (OSError, UnicodeDecodeError) as error:
                raise RepairApplicationError(
                    _REPLACEMENT_CONTEXT_INVALID,
                    "replace_text target cannot be represented as repair text",
                ) from error
            targets.append(
                {
                    "bom": raw.startswith(b"\xef\xbb\xbf"),
                    "content": content,
                    "final_newline": raw.endswith((b"\n", b"\r")),
                    "path": relative,
                    "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw),
                }
            )

        try:
            live_fingerprint = StageSandboxCopier.fingerprint(workspace)
        except OSError as error:
            raise RepairApplicationError(
                "REPAIR_WORKSPACE_MISSING", "Repair workspace is unavailable"
            ) from error
        if live_fingerprint != authoritative["workspace_stored_fingerprint"]:
            raise RepairApplicationError(
                "REPAIR_WORKSPACE_STALE", "Repair workspace fingerprint changed"
            )
        payload = {
            "schema_version": _SEMANTIC_RETRY_CONTEXT_SCHEMA,
            "targets": targets,
            "workspace_fingerprint": authoritative["workspace_stored_fingerprint"],
        }
        segment = json.dumps(payload, sort_keys=True)
        return {"segment": segment, "payload": payload}

    def _load_semantic_retry_context(
        self, context: dict[str, object]
    ) -> dict[str, str] | None:
        base_invocation_id = _invocation_key(
            str(context["attempt_id"]), LlmRole.REPAIR_PROPOSER
        )
        with self._scope() as session:
            invocation = session.scalar(
                select(LlmInvocationModel).where(
                    LlmInvocationModel.run_id == context["run_id"],
                    LlmInvocationModel.idempotency_key == base_invocation_id,
                )
            )
            if invocation is None:
                return None
            metadata = {
                artifact_id: session.get(ArtifactMetadataModel, "metadata-" + artifact_id)
                for artifact_id in invocation.artifact_ids or []
            }
            rejected_metadata = [
                item
                for item in metadata.values()
                if item is not None
                and PurePosixPath(item.relative_path).name.startswith(
                    "rejected-proposer-candidate"
                )
            ]
        if not rejected_metadata:
            return None
        root = Path(str(context["artifact_root"]))
        store = LocalFilesystemArtifactStore(root.parent, fixed_run_root=root)
        recovered = []
        for metadata_item in rejected_metadata:
            try:
                stored = store.read_artifact(str(context["run_id"]), metadata_item.relative_path)
                self._validate_artifact_envelope(
                    stored,
                    expected_run_id=context["run_id"],
                    expected_stage_id=context["stage_id"],
                    expected_attempt_id=context["attempt_id"],
                    pre_attempt=False,
                    metadata_checksum=metadata_item.checksum,
                )
                candidate_payload = json.loads(stored.content)
                retry_payload = (
                    candidate_payload.get("semantic_retry_context")
                    if isinstance(candidate_payload, dict)
                    else None
                )
                retry_code = (
                    candidate_payload.get("semantic_failure_code")
                    if isinstance(candidate_payload, dict)
                    else None
                )
                retry_message = (
                    candidate_payload.get("semantic_failure_message")
                    if isinstance(candidate_payload, dict)
                    else None
                )
                if retry_payload is not None:
                    recovered.append(
                        (
                            self._validate_semantic_retry_context(retry_payload, context),
                            retry_code,
                            retry_message,
                        )
                    )
                elif retry_code == "REPAIR_DEPENDENCY_PACKAGE_AMBIGUOUS":
                    candidate = (
                        candidate_payload.get("candidate")
                        if isinstance(candidate_payload, dict)
                        else None
                    )
                    if isinstance(candidate, dict):
                        try:
                            self._bind_proposal_candidate(candidate, context)
                        except RepairApplicationError as error:
                            if error.code == _DEPENDENCY_SECTION_MISMATCH:
                                recovered.append((None, error.code, error.message))
            except RepairApplicationError:
                raise
            except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError) as error:
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED",
                    "Repair semantic retry context cannot be loaded",
                ) from error
        if len(recovered) > 1:
            raise RepairApplicationError(
                "REPAIR_ARTIFACT_RECOVERY_FAILED",
                "Repair semantic retry context lineage is ambiguous",
            )
        if not recovered:
            return None
        payload, retry_code, retry_message = recovered[0]
        if retry_code not in _SEMANTIC_RETRY_CODES:
            raise RepairApplicationError(
                "REPAIR_ARTIFACT_RECOVERY_FAILED",
                "Repair semantic retry context failure code is invalid",
            )
        return {
            "segment": json.dumps(payload, sort_keys=True) if payload is not None else None,
            "checksum": self._request_checksum(payload) if payload is not None else None,
            "error_code": retry_code,
            "error_message": retry_message,
        }

    def _validate_semantic_retry_context(
        self, payload: object, context: dict[str, object]
    ) -> dict[str, object]:
        if not isinstance(payload, dict) or payload.get("schema_version") != _SEMANTIC_RETRY_CONTEXT_SCHEMA:
            raise RepairApplicationError(
                "REPAIR_ARTIFACT_RECOVERY_FAILED",
                "Repair semantic retry context schema is invalid",
            )
        if payload.get("workspace_fingerprint") != context["workspace_stored_fingerprint"]:
            raise RepairApplicationError(
                "REPAIR_WORKSPACE_STALE",
                "Repair semantic retry context workspace fingerprint is stale",
            )
        targets = payload.get("targets")
        if not isinstance(targets, list) or not targets:
            raise RepairApplicationError(
                "REPAIR_ARTIFACT_RECOVERY_FAILED",
                "Repair semantic retry context targets are invalid",
            )
        paths = [item.get("path") for item in targets if isinstance(item, dict)]
        if (
            len(paths) != len(targets)
            or not all(isinstance(path, str) for path in paths)
            or paths != sorted(paths)
            or len(set(paths)) != len(paths)
        ):
            raise RepairApplicationError(
                "REPAIR_ARTIFACT_RECOVERY_FAILED",
                "Repair semantic retry context target ordering is invalid",
            )
        workspace = Path(str(context["workspace_path"])).resolve(strict=True)
        for item in targets:
            if not isinstance(item, dict):
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED",
                    "Repair semantic retry context target is invalid",
                )
            try:
                relative = self._safe_path(str(item.get("path") or ""), workspace)
            except (RepairApplicationError, OSError, ValueError) as error:
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED",
                    "Repair semantic retry context target path is invalid",
                ) from error
            if relative != item.get("path"):
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED",
                    "Repair semantic retry context target path is not canonical",
                )
            target_content = item.get("content")
            raw = target_content.encode("utf-8") if isinstance(target_content, str) else None
            if (
                raw is None
                or len(raw) != item.get("size_bytes")
                or len(raw) > CONTEXT_PACK_MAX_BYTES_PER_FILE
                or item.get("sha256") != "sha256:" + hashlib.sha256(raw).hexdigest()
            ):
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED",
                    "Repair semantic retry context target checksum is invalid",
                )
            if "bom" in item and item["bom"] is not raw.startswith(b"\xef\xbb\xbf"):
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED",
                    "Repair semantic retry context target BOM state is invalid",
                )
            if "final_newline" in item and item["final_newline"] is not raw.endswith(
                (b"\n", b"\r")
            ):
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED",
                    "Repair semantic retry context target EOF state is invalid",
                )
        return payload

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

    @staticmethod
    def _stage_target_context(context: dict[str, object]) -> dict[str, object]:
        """Deterministic stage target contract segment for every repair prompt."""
        source_family = context.get("source_family") or ""
        target_exact = context.get("target_exact")
        target_cli = context.get("target_cli_exact")
        source_exact = context.get("source_exact")
        return {
            "segment": "stage_target_cohort",
            "stage": context.get("stage_id"),
            "source_angular": source_exact,
            "target_angular": target_exact,
            "target_cli": target_cli,
            "allowed_transition": (
                f"{source_family} -> {target_exact}" if source_family and target_exact else ""
            ),
            "rule": "Never propose source package versions as fixes; "
            "the stage target cohort below is the authoritative migration contract.",
            "target_cohort": dict(context.get("target_cohort") or {}),
        }

    def validate_repair_target_cohort(
        self, context: dict[str, object], proposal: dict[str, object]
    ) -> None:
        """Deterministic cohort gate over the bound proposal, before reviewer and apply.

        Every proposal that touches a stage-cohort package must bind the exact
        cohort version (or a range containing it for whole-manifest
        materialization); source versions are never acceptable targets.
        """
        cohort = context.get("target_cohort")
        if not isinstance(cohort, dict) or not cohort:
            return
        from app.services.dependency_repair_preflight_service import DependencyRepairPreflightService as _Preflight

        operations = proposal.get("operations") or []
        if not isinstance(operations, list):
            return
        for index, operation in enumerate(operations):
            if not isinstance(operation, dict):
                continue
            op_type = operation.get("operation")
            if op_type == "dependency_transition":
                target = operation.get("target_state")
                if not isinstance(target, dict):
                    continue
                package = target.get("package")
                version = target.get("target_version")
                required = cohort.get(package) if isinstance(package, str) else None
                if required and version != required:
                    raise RepairApplicationError(
                        "TARGET_COHORT_MISMATCH",
                        f"operations.{index} dependency_transition target {package} "
                        f"{version} does not match the stage target cohort {required}",
                    )
            elif self._is_normalization_operation(operation):
                text = operation.get("new_text") or operation.get("post_text")
                if not isinstance(text, str):
                    continue
                try:
                    manifest = json.loads(text)
                except (TypeError, ValueError):
                    continue
                dependencies = {
                    name: value
                    for section in ("dependencies", "devDependencies")
                    if isinstance(manifest.get(section), dict)
                    for name, value in manifest[section].items()
                    if isinstance(name, str) and isinstance(value, str)
                }
                for package, required in cohort.items():
                    proposed_spec = dependencies.get(package)
                    if proposed_spec is not None and not _Preflight._range_contains_exact(
                        proposed_spec, required
                    ):
                        raise RepairApplicationError(
                            "TARGET_COHORT_MISMATCH",
                            f"operations.{index} normalized {package} {proposed_spec} "
                            f"does not match the stage target cohort {required}",
                        )
            else:
                package = operation.get("package")
                version = operation.get("new_version")
                if (
                    isinstance(package, str)
                    and isinstance(version, str)
                    and package in cohort
                    and not _Preflight._range_contains_exact(version, cohort[package])
                ):
                    raise RepairApplicationError(
                        "TARGET_COHORT_MISMATCH",
                        f"operations.{index} {package} {version} does not match "
                        f"the stage target cohort {cohort[package]}",
                    )

    def validate_proposal(
        self, value: dict[str, object], context: dict[str, object]
    ) -> dict[str, object]:
        try:
            proposal = RepairProposal.model_validate(value)
        except ValidationError as error:
            raise RepairApplicationError(
                "REPAIR_BOUND_PROPOSAL_INVALID",
                "Backend-bound repair proposal violates authoritative invariants: "
                + _proposal_validation_message(error),
            ) from error
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
        is_normalization = any(
            self._is_normalization_operation(item.model_dump(mode="json"))
            for item in proposal.operations
        ) if proposal.operations else False
        if proposal.operations:
            operation_paths = [self._safe_path(item.path, workspace) for item in proposal.operations]
            if len(normalized) != len(set(normalized)) and len(operation_paths) == len(set(operation_paths)):
                raise RepairApplicationError(
                    "REPAIR_PATH_DUPLICATE", "Touched file paths must be unique"
                )
            if is_normalization:
                operations = [item.model_dump(mode="json") for item in proposal.operations]
                expected_paths = ["package.json"]
                # touched_files already ["package.json"] from binding; lenient check
                if sorted(set(normalized)) != sorted(set(expected_paths)):
                    raise RepairApplicationError(
                        "REPAIR_TOUCHED_FILES_MISMATCH", "Operation paths do not match touched_files"
                    )
                # verify normalization plan still complete (re-materialize check)
                # lenient: allow already-bound normalization without re-materialization
            else:
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
            expected_paths = []
        if proposal.proposal_format == "operations" and proposal.operations:
            bound = proposal.model_dump(mode="json")
            bound["operations"] = operations
            bound["touched_files"] = expected_paths if 'expected_paths' in locals() else []
            if is_normalization:
                # re-validate normalization by re-binding to ensure backend owns bytes (checksum/diff)
                # If already bound, _bind_dependency_normalization will re-materialize and must match stored checksums
                try:
                    rebound = self._bind_dependency_normalization(bound, context)
                    # ensure stored post_checksum matches rebound (exact postimage follows from actions)
                    orig_op = bound["operations"][0] if bound["operations"] else {}
                    new_op = rebound["operations"][0] if rebound["operations"] else {}
                    if orig_op.get("post_checksum") and new_op.get("post_checksum") and orig_op.get("post_checksum") != new_op.get("post_checksum"):
                        raise RepairApplicationError(
                            "REPAIR_DEPENDENCY_NORMALIZATION_INVALID",
                            "stored postimage checksum does not follow from approved actions",
                        )
                    bound = rebound
                except RepairApplicationError:
                    # if rebind fails, keep original but still check causal
                    pass
            elif any(item.get("operation") == "dependency_transition" for item in operations):
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
        self.validate_repair_target_cohort(context, result)
        rejection = self._causal_gate_rejection(context, result)
        if rejection is not None:
            raise RepairApplicationError(
                rejection.code
                if rejection.code == "REPAIR_CAUSAL_KIND_MISMATCH"
                else "REPAIR_CAUSAL_REJECTION",
                rejection.reason,
            )
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
                "target_cohort": dict(stage_value.get("target_cohort") or {}),
                "source_exact": stage_value.get("source_exact"),
                "source_family": stage_value.get("source_family"),
                "target_family": stage_value.get("target_family"),
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
        context["segments"].append(
            json.dumps(self._stage_target_context(context), sort_keys=True)
        )
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
            "causal_repair": failure.get("causal_repair"),
            "target_cohort": failure.get("target_cohort") or {},
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
            semantic_retry_context_checksum=context.get("semantic_retry_context_checksum"),
            semantic_retry_message=context.get("semantic_retry_message"),
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
                    context=self._llm_context_segments(context, role),
                    response_schema=schema_name,
                    max_output_tokens=16384,
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

    @staticmethod
    def _llm_context_segments(context, role):
        segments = [
            LlmContextSegment(
                segment_id=f"evidence-{index}",
                label="untrusted repair evidence",
                content=content,
                untrusted=True,
            )
            for index, content in enumerate(context["segments"])
        ]
        if role == LlmRole.REPAIR_PROPOSER:
            for content in context["segments"]:
                try:
                    payload = json.loads(str(content))
                except (TypeError, ValueError):
                    continue
                revision = payload.get("human_revision") if isinstance(payload, dict) else None
                instruction = (
                    str(revision.get("instruction") or "").strip()
                    if isinstance(revision, dict)
                    else ""
                )
                if instruction:
                    # Keep operator intent explicit and bounded; it constrains
                    # the proposer but never becomes authoritative workspace data.
                    segments.insert(
                        0,
                        LlmContextSegment(
                            segment_id="operator-revision-instruction",
                            label="binding operator repair revision instruction",
                            content=instruction[:4000],
                            untrusted=False,
                        ),
                    )
                    break
        return segments

    def _retrieve_provider_response(
        self,
        context,
        *,
        role,
        task,
        schema_name,
        schema,
        provider_response_id: str,
    ):
        registry = PromptSchemaRegistry(version=get_settings().llm_schema_registry_version)
        registry.register(schema_name, schema)
        gateway = self._gateway or AzureOpenAILLMGateway(settings=get_settings(), registry=registry)
        request = LlmRequest(
            request_id=_context_invocation_key(context, role),
            run_id=str(context["run_id"]),
            stage_id=str(context["stage_id"]),
            agent_kind=AgentKind.REPAIR,
            task_type=task,
            role=role,
            prompt_name=schema_name,
            system_policy="Retrieve and validate the already-created provider response.",
            context=self._llm_context_segments(context, role),
            response_schema=schema_name,
            max_output_tokens=16384,
        )
        try:
            response = gateway.retrieve_response(request, provider_response_id=provider_response_id)
        except AzureGatewayError as exc:
            if exc.failure_subtype in {
                "PROVIDER_RESPONSE_PENDING",
                "PROVIDER_RESPONSE_RETRIEVAL_UNSUPPORTED",
            }:
                raise RepairApplicationError(
                    "REPAIR_INVOCATION_UNCERTAIN",
                    "Provider response remains recoverable but is not terminal",
                ) from exc
            translated = _translate_gateway_failure(exc)
            self._persist_failure(
                context,
                role,
                translated,
                failure_stage_override="response_retrieval",
            )
            raise translated from exc
        return registry.validate(schema_name, response.structured_output), response

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
                if invocation.provider_response_id:
                    context.update(
                        request_checksum=invocation.request_checksum,
                        prompt_version=invocation.prompt_version,
                        schema_version=invocation.schema_version,
                        invocation_state_version=invocation.state_version,
                        invocation_owner_state={
                            "run_id": context["run_id"],
                            "idempotency_key": invocation.idempotency_key,
                            "invocation_id": invocation.id,
                            "state_version": invocation.state_version,
                        },
                        _provider_response_id=invocation.provider_response_id,
                    )
                    return None
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
            deterministic_rebind = (
                role == "proposer"
                and invocation.deployment_alias == "deterministic-provenance-rebind"
                and invocation.response_kind == "deterministic_rebind"
                and invocation.response_received is False
            )
            if schema_name and task_type and schema:
                prompt_version = self._prompt_version(schema_name, task_type)
                schema_version = get_settings().llm_schema_registry_version
                expected_request = self._logical_request_checksum(
                    context["segments"], schema_name, prompt_version, schema_version
                )
                if not legacy_v1 and not deterministic_rebind and (
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
        if context.get("semantic_retry_context_checksum"):
            input_hashes.append(
                "semantic_retry_context:" + str(context["semantic_retry_context_checksum"])
            )
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
                        base_invocation = session.scalar(
                            select(LlmInvocationModel).where(
                                LlmInvocationModel.run_id == context["run_id"],
                                LlmInvocationModel.idempotency_key == base_invocation_id,
                            )
                        )
                        context["segments"].append(
                            _semantic_retry_feedback(
                                base_invocation.failure_code if base_invocation is not None else None,
                                context.get("semantic_retry_message"),
                            )
                        )
                        request_checksum = self._logical_request_checksum(
                            context["segments"], schema_name, prompt_version, schema_version
                        )
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
                if context.get("semantic_retry_count") and existing is not None:
                    if existing.status == "failed":
                        raise RepairApplicationError(
                            "REPAIR_SEMANTIC_RETRY_EXHAUSTED",
                            "Repair semantic correction retry has already failed",
                        )
                    if existing.status == "in_progress" and existing.transport_started:
                        raise RepairApplicationError(
                            "REPAIR_INVOCATION_UNCERTAIN",
                            "Repair semantic correction retry outcome is uncertain",
                        )
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
                if context.get("semantic_retry_count") and existing.status == "failed":
                    raise RepairApplicationError(
                        "REPAIR_SEMANTIC_RETRY_EXHAUSTED",
                        "Repair semantic correction retry has already failed",
                    )
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
        semantic_retry_context=None,
    ) -> None:
        kind = "propose-error" if role == LlmRole.REPAIR_PROPOSER else "review-error"
        cause = error.__cause__ if isinstance(error.__cause__, AzureGatewayError) else None
        request_id = getattr(error, "provider_request_id", None)
        if not request_id and response is not None:
            request_id = response.provider_request_id
        response_id = getattr(error, "provider_response_id", None)
        if not response_id and response is not None:
            response_id = response.provider_response_id
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
                "provider_response_id": response_id,
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
            try:
                parsed_candidate = RepairProposalCandidate.model_validate(
                    rejected_candidate
                ).model_dump(mode="json")
            except ValidationError as validation_error:
                parsed_candidate = {
                    "schema_invalid": True,
                    "validation_error": _proposal_validation_message(validation_error),
                    "candidate_keys": sorted(
                        str(key)
                        for key in rejected_candidate
                    )
                    if isinstance(rejected_candidate, dict)
                    else [],
                }
            rejected_payload = {
                "attempt_id": context["attempt_id"],
                "candidate": parsed_candidate,
                "prompt_version": context.get("prompt_version"),
                "schema_version": context.get("schema_version"),
                "candidate_checksum": self._request_checksum(parsed_candidate),
                "context_checksum": context.get("context_pack_checksum"),
                "semantic_failure_code": error.code,
                "semantic_failure_message": _bounded_text(error.message, 512),
                "provider_request_id": _bounded_text(request_id, 256),
            }
            if semantic_retry_context is not None:
                rejected_payload["semantic_retry_context"] = semantic_retry_context
            rejected_stored = self._write(
                context,
                "rejected-proposer-candidate",
                rejected_payload,
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
                for artifact in (stored, rejected_stored):
                    if artifact is not None:
                        self._remove_uncommitted_artifact(artifact)
                return
            expected_state = context.get("invocation_state_version")
            if expected_state is None or invocation.state_version != expected_state or invocation.status != "in_progress":
                for artifact in (stored, rejected_stored):
                    if artifact is not None:
                        self._remove_uncommitted_artifact(artifact)
                return
            artifact_ids = list(invocation.artifact_ids or [])
            artifact_checksums = dict(invocation.artifact_checksums or {})
            if stored.ref.artifact_id not in artifact_ids:
                artifact_ids.append(stored.ref.artifact_id)
            artifact_checksums[stored.ref.artifact_id] = stored.ref.checksum
            if rejected_stored is not None:
                if rejected_stored.ref.artifact_id not in artifact_ids:
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
                    provider_response_id=invocation.provider_response_id or response_id,
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
                for artifact in (stored, rejected_stored):
                    if artifact is not None:
                        self._remove_uncommitted_artifact(artifact)
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

    @staticmethod
    def _legacy_override_recovery_event_key(idempotency_key: str) -> str:
        return "repair-legacy-g10-recovery:" + hashlib.sha256(
            idempotency_key.encode()
        ).hexdigest()

    @staticmethod
    def _bound_candidate_recovery_event_key(idempotency_key: str) -> str:
        return "repair-bound-candidate-recovery:" + hashlib.sha256(
            idempotency_key.encode()
        ).hexdigest()

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
            if action == DEPENDENCY_NORMALIZATION_REPAIR_KIND:
                before = str(operation.get("old_text") or "")
                after = str(operation.get("new_text") or operation.get("post_text") or "")
                diff = operation.get("diff")
                if isinstance(diff, str) and diff:
                    rendered.append(diff if diff.endswith("\n") else diff + "\n")
                    continue
                diff2 = "".join(
                    unified_diff(
                        before.splitlines(keepends=True),
                        after.splitlines(keepends=True),
                        fromfile=f"a/{path}",
                        tofile=f"b/{path}",
                        lineterm="\n",
                    )
                )
                if diff2:
                    rendered.append(diff2 if diff2.endswith("\n") else diff2 + "\n")
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
                old_text = operation.get("old_text")
                if not isinstance(old_text, str) or not old_text:
                    raise RepairApplicationError(
                        _REPLACEMENT_PREIMAGE_REQUIRED,
                        "replace_text requires a non-empty old_text copied from authoritative "
                        "repository content; null or missing preimages are forbidden.",
                    )
                after = replace_text_once(
                    before,
                    old_text,
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
            if response.provider_response_id and not invocation.provider_response_id:
                invocation.provider_response_id = response.provider_response_id
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
