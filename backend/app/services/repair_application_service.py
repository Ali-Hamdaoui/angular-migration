"""Governed repair proposal/review and deterministic semantic validation."""

from __future__ import annotations

import hashlib
import json
import re
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
)
from app.core.config import get_settings
from app.domain.contracts import AgentKind, ArtifactType
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
    LlmInvocationModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageExecutionPlanModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    UsageCostRecordModel,
)
from app.services.stage_preparation_primitives import StageSandboxCopier


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

_UNIFIED_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _unified_diff_header_path(line: str, path_prefix: str) -> str:
    return line[4:].split("\t", 1)[0].strip().removeprefix(path_prefix)


def _bounded_text(value: object, limit: int = 240) -> str | None:
    if value is None:
        return None
    return str(value).replace("\r", " ").replace("\n", " ")[:limit]


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

    operation: Literal["replace_text", "create_text_file", "delete_text_file", "dependency_change"]
    path: str = Field(min_length=1, max_length=500)
    old_text: str | None = None
    new_text: str | None = None
    content: str | None = None


class RepairOperation(RepairOperationCandidate):
    preimage_sha256: str | None = None


class RepairProposalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_format: Literal["operations", "unified_diff"]
    operations: list[RepairOperationCandidate] = Field(max_length=32)
    unified_diff: str | None = Field(default=None, max_length=100_000)
    rationale: list[str] = Field(min_length=1, max_length=16)
    risk_level: Literal["low", "medium", "high"]
    validation_targets: list[str] = Field(min_length=1, max_length=16)
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
    required_validation_targets: list[str] = Field(min_length=1, max_length=16)
    limitations: list[str] = Field(max_length=16)


class RepairReview(RepairReviewCandidate):
    proposal_checksum: str


class RepairApplicationService:
    proposer_schema = "repair_proposer_candidate_v2"
    reviewer_schema = "repair_reviewer_candidate_v2"
    supported_validation_targets = frozenset({"build", "test", "lint"})
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
        context = self._attempt_context(attempt_id)
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
                    "lockfile edits, path escapes, secrets, or policy bypasses."
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
            )
            raise
        stored = self._write(context, "proposal", proposal)
        try:
            self._persist_call(
                context,
                response,
                stored,
                role="proposer",
                schema_name=self.proposer_schema,
                summary=proposal,
            )
        except RepairApplicationError as error:
            self._remove_uncommitted_artifact(stored)
            self._persist_failure(
                context, LlmRole.REPAIR_PROPOSER, error,
                failure_stage_override="authority_check", response=response,
            )
            raise
        return proposal

    def review(self, attempt_id: str) -> dict[str, object]:
        context = self._attempt_context(attempt_id, include_proposal=True)
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
                    "replacement code, commands, or a different proposal."
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

    def _bind_proposal_candidate(self, value: dict[str, object], context: dict[str, object]):
        candidate = RepairProposalCandidate.model_validate(value)
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
        operations = []
        for operation in candidate.operations:
            bound = operation.model_dump(mode="json")
            relative = self._safe_path(operation.path, workspace)
            bound["path"] = relative
            if operation.operation == "create_text_file":
                bound["preimage_sha256"] = None
            else:
                target = workspace / relative
                bound["preimage_sha256"] = (
                    "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
                    if target.is_file() and not target.is_symlink()
                    else None
                )
            operations.append(bound)
        touched_files = (
            [operation["path"] for operation in operations]
            if operations
            else self._unified_diff_touched_files(candidate.unified_diff, workspace)
        )
        return RepairProposal.model_validate(
            {
                **candidate.model_dump(mode="json"),
                "failure_evidence_checksum": context["failure_evidence_checksum"],
                "context_pack_checksum": context["context_pack_checksum"],
                "operations": operations,
                "touched_files": touched_files,
                "validation_targets": self._normalize_validation_targets(
                    candidate.validation_targets
                ),
            }
        ).model_dump(mode="json")

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
        if any(value not in self.supported_validation_targets for value in normalized):
            raise RepairApplicationError(
                "REPAIR_VALIDATION_TARGET_INVALID",
                "Repair validation targets must use backend-supported names",
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
        if len(normalized) != len(set(normalized)):
            raise RepairApplicationError("REPAIR_PATH_DUPLICATE", "Touched file paths must be unique")
        operation_paths = []
        for operation in proposal.operations:
            relative = self._safe_path(operation.path, workspace)
            operation_paths.append(relative)
            target = workspace / relative
            if operation.operation == "create_text_file":
                if target.exists() or operation.content is None:
                    raise RepairApplicationError(
                        "REPAIR_PREIMAGE_INVALID", "Create operation target or content is invalid"
                    )
            else:
                if not target.is_file() or target.is_symlink():
                    raise RepairApplicationError(
                        "REPAIR_PREIMAGE_INVALID", "Repair target must be a regular existing file"
                    )
                try:
                    target.read_text(encoding="utf-8")
                except UnicodeDecodeError as error:
                    raise RepairApplicationError(
                        "REPAIR_BINARY_FORBIDDEN", "Repair target is not UTF-8 text"
                    ) from error
                actual = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
                if operation.preimage_sha256 != actual:
                    raise RepairApplicationError(
                        "REPAIR_PREIMAGE_STALE", "Repair target preimage checksum changed"
                    )
            if operation.operation == "dependency_change" and relative != "package.json":
                raise RepairApplicationError(
                    "REPAIR_DEPENDENCY_PATH_INVALID",
                    "Dependency changes may edit only package.json",
                )
            if relative == "package.json" and operation.operation != "dependency_change":
                raise RepairApplicationError(
                    "REPAIR_DEPENDENCY_OPERATION_REQUIRED",
                    "package.json changes require the controlled dependency operation",
                )
            if operation.operation == "dependency_change":
                raise RepairApplicationError(
                    "REPAIR_DEPENDENCY_COMMAND_MISSING",
                    "The accepted stage plan has no registered lockfile-generation command",
                )
            if operation.operation in {"replace_text", "dependency_change"} and (
                operation.old_text is None or operation.new_text is None
            ):
                raise RepairApplicationError(
                    "REPAIR_OPERATION_INVALID", "replace_text needs old_text and new_text"
                )
        if proposal.operations and sorted(operation_paths) != sorted(normalized):
            raise RepairApplicationError(
                "REPAIR_TOUCHED_FILES_MISMATCH", "Operation paths do not match touched_files"
            )
        return proposal.model_dump(mode="json")

    def _attempt_context(self, attempt_id: str, *, include_proposal: bool = False):
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
            context = {
                "attempt_id": attempt.id,
                "run_id": attempt.run_id,
                "stage_id": attempt.stage_id,
                "artifact_root": run.artifact_root,
                "workspace_path": binding.workspace_path,
                "failure_evidence_checksum": attempt.failure_evidence_checksum,
                "context_pack_checksum": attempt.context_pack_checksum,
                "context_pack_artifact_id": attempt.context_pack_artifact_id,
                "proposal_checksum": attempt.proposal_checksum,
                "proposal_artifact_id": attempt.proposal_artifact_id,
                "proposer_invocation_id": attempt.proposer_invocation_id,
                "reviewer_invocation_id": attempt.reviewer_invocation_id,
                "failure_evidence_artifact_id": attempt.failure_evidence_artifact_id,
                "attempt_number": attempt.attempt_number,
                "attempt_status": attempt.status,
                "parent_attempt_id": attempt.parent_attempt_id,
                "run_state_version": run.state_version,
                "continuation_state_version": continuation.state_version if continuation else None,
                "stage_plan_id": stage_plan.id if stage_plan else (continuation.stage_plan_id if continuation else None),
                "stage_plan_checksum": stage_plan.checksum if stage_plan else (continuation.stage_plan_checksum if continuation else None),
                "stage_plan_state_version": stage_plan.state_version if stage_plan else None,
                "workspace_binding_id": binding.id,
                "workspace_stored_fingerprint": binding.workspace_fingerprint,
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
            for artifact_id, expected in expected_checksums.items():

                if metadata[artifact_id].checksum != expected:
                    raise RepairApplicationError("REPAIR_ARTIFACT_RECOVERY_FAILED", "Repair artifact checksum binding is stale")
        root = Path(str(context["artifact_root"]))
        store = LocalFilesystemArtifactStore(root.parent, fixed_run_root=root)
        artifacts = [store.read_artifact(str(context["run_id"]), metadata[artifact_id].relative_path) for artifact_id in artifact_ids]
        for artifact in artifacts:
            envelope = artifact.envelope
            if (
                artifact.ref.checksum != metadata[artifact.ref.artifact_id].checksum
                or envelope is None
                or envelope.run_id != context["run_id"]
                or envelope.stage_id != context["stage_id"]
                or envelope.attempt_id != context["attempt_id"]
            ):
                raise RepairApplicationError("REPAIR_ARTIFACT_RECOVERY_FAILED", "Repair artifact envelope binding is stale")
        workspace = Path(str(context["workspace_path"]))
        try:
            context["workspace_live_fingerprint"] = StageSandboxCopier.fingerprint(workspace)
        except OSError as error:
            raise RepairApplicationError("REPAIR_WORKSPACE_MISSING", "Repair workspace is unavailable") from error
        if context["workspace_live_fingerprint"] != context["workspace_stored_fingerprint"]:
            raise RepairApplicationError("REPAIR_WORKSPACE_STALE", "Repair workspace fingerprint changed")
        context["segments"] = [artifact.content for artifact in artifacts]
        if include_proposal:
            context["proposal_checksum"] = artifacts[-1].ref.checksum
            context["proposal_artifact_id"] = artifacts[-1].ref.artifact_id
            context["authority_snapshot"] = self._authority_snapshot(context)
        context["authority_snapshot"] = self._authority_snapshot(context)
        return context

    @staticmethod
    def _authority_snapshot(context: dict[str, object]) -> dict[str, object]:
        return {
            key: context.get(key)
            for key in (
                "run_id", "run_state_version", "continuation_state_version", "stage_id",
                "stage_plan_id", "stage_plan_checksum", "stage_plan_state_version",
                "attempt_id", "attempt_number", "attempt_status", "parent_attempt_id",
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
                    request_id=f"{context['attempt_id']}:{role.value}",
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
        invocation_key = f"{context['attempt_id']}:{role}"
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
            if attempt is None or attempt.run_id != context["run_id"]:
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
        invocation_id = _invocation_key(str(context["attempt_id"]), role)
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
        try:
            with self._scope() as session:
                existing = session.scalar(
                    select(LlmInvocationModel).where(
                        LlmInvocationModel.run_id == context["run_id"],
                        LlmInvocationModel.idempotency_key == invocation_id,
                    )
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
                        retries=0,
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
                    LlmInvocationModel.idempotency_key == _invocation_key(str(context["attempt_id"]), role),
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
        now = self._now()
        with self._scope() as session:
            invocation = session.scalar(
                select(LlmInvocationModel).where(
                    LlmInvocationModel.run_id == context["run_id"],
                    LlmInvocationModel.idempotency_key == _invocation_key(str(context["attempt_id"]), role),
                )
            )
            if invocation is None:
                self._remove_uncommitted_artifact(stored)
                return
            expected_state = context.get("invocation_state_version")
            if expected_state is None or invocation.state_version != expected_state or invocation.status != "in_progress":
                self._remove_uncommitted_artifact(stored)
                return
            artifact_ids = list(dict.fromkeys([*(invocation.artifact_ids or []), stored.ref.artifact_id]))
            artifact_checksums = {**(invocation.artifact_checksums or {}), stored.ref.artifact_id: stored.ref.checksum}
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
                return
            self._register_artifact_metadata(session, context, stored)
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

    def _persist_call(self, context, response, stored, *, role, schema_name, summary):
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
            invocation_id = _invocation_key(attempt.id, role)
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
            invocation_id = _invocation_key(attempt.id, role)
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
            invocation.artifact_ids = list(dict.fromkeys([*(invocation.artifact_ids or []), stored.ref.artifact_id]))
            invocation.artifact_checksums = {**(invocation.artifact_checksums or {}), stored.ref.artifact_id: stored.ref.checksum}
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
