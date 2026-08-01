"""Governed repair proposal/review and deterministic semantic validation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError
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
    StageWorkspaceBindingModel,
    UsageCostRecordModel,
)


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
        recovered = self._recover_completed(context, role="proposer")
        if recovered is not None:
            return recovered
        self._start_invocation(
            context,
            role=LlmRole.REPAIR_PROPOSER,
            task_type=LlmTaskType.REPAIR_DIAGNOSIS,
            schema_name=self.proposer_schema,
            schema=RepairProposalCandidate,
        )
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
        self._persist_call(
            context,
            response,
            stored,
            role="proposer",
            schema_name=self.proposer_schema,
            summary=proposal,
        )
        return proposal

    def review(self, attempt_id: str) -> dict[str, object]:
        context = self._attempt_context(attempt_id, include_proposal=True)
        recovered = self._recover_completed(context, role="reviewer")
        if recovered is not None:
            return recovered
        self._start_invocation(
            context,
            role=LlmRole.REPAIR_REVIEWER,
            task_type=LlmTaskType.REPAIR_REVIEW,
            schema_name=self.reviewer_schema,
            schema=RepairReviewCandidate,
        )
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
        context = self._attempt_context(attempt_id, include_proposal=True)
        try:
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
        self._persist_call(
            context,
            response,
            stored,
            role="reviewer",
            schema_name=self.reviewer_schema,
            summary=review,
        )
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
            if lines[index].startswith("+++ ") or not lines[index].startswith("--- "):
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
            old_path = lines[index][4:].split("\t", 1)[0].removeprefix("a/")
            new_path = lines[index + 1][4:].split("\t", 1)[0].removeprefix("b/")
            old_path = None if old_path == "/dev/null" else self._safe_path(old_path, workspace)
            new_path = None if new_path == "/dev/null" else self._safe_path(new_path, workspace)
            if old_path is None and new_path is None:
                raise RepairApplicationError(
                    "REPAIR_DIFF_INVALID", "Unified diff header pair has no file path"
                )
            paths.append(new_path or old_path)
            index += 2
        if not paths:
            raise RepairApplicationError(
                "REPAIR_TOUCHED_FILES_MISSING", "Unified diff must identify touched files"
            )
        return paths

    @staticmethod
    def _prompt_version(schema_name: str, task_type: LlmTaskType) -> str:
        return PromptRegistry.defaults().get(schema_name, task_type).version

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
            attempt = session.get(RepairAttemptModel, attempt_id)
            if attempt is None:
                raise RepairApplicationError("REPAIR_ATTEMPT_NOT_FOUND", "Repair attempt is missing")
            run = session.get(MigrationRunModel, attempt.run_id)
            binding = session.query(StageWorkspaceBindingModel).filter_by(
                run_id=attempt.run_id, stage_id=attempt.stage_id, active=True
            ).one()
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
            }
            artifact_ids = [attempt.context_pack_artifact_id]
            if include_proposal:
                if not attempt.proposal_artifact_id or not attempt.proposal_checksum:
                    raise RepairApplicationError(
                        "REPAIR_PROPOSAL_MISSING", "Repair proposal is missing"
                    )
                artifact_ids.append(attempt.proposal_artifact_id)
            metadata = {
                item.id.removeprefix("metadata-"): item.relative_path
                for item in session.query(ArtifactMetadataModel)
                .filter(ArtifactMetadataModel.id.in_([f"metadata-{item}" for item in artifact_ids]))
                .all()
            }
        root = Path(str(context["artifact_root"]))
        store = LocalFilesystemArtifactStore(root.parent, fixed_run_root=root)
        artifacts = [
            store.read_artifact(str(context["run_id"]), metadata[artifact_id])
            for artifact_id in artifact_ids
        ]
        context["segments"] = [artifact.content for artifact in artifacts]
        if include_proposal:
            context["proposal_checksum"] = artifacts[-1].ref.checksum
        return context

    def _call(self, context, *, role, task, schema_name, schema, policy):
        if self._gateway is None and not get_settings().llm_enabled:
            raise RepairApplicationError(
                "REPAIR_LLM_DISABLED", "Governed repair requires the configured Azure gateway"
            )
        registry = PromptSchemaRegistry(version=get_settings().llm_schema_registry_version)
        registry.register(schema_name, schema)
        try:
            gateway = self._gateway or AzureOpenAILLMGateway(settings=get_settings(), registry=registry)
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
            self._persist_failure(context, role, translated)
            raise translated from exc

    def _recover_completed(self, context, *, role: str):
        invocation_key = f"{context['attempt_id']}:{role}"
        artifact_field = "proposal_artifact_id" if role == "proposer" else "review_artifact_id"
        with self._scope() as session:
            invocation = (
                session.query(LlmInvocationModel)
                .filter_by(idempotency_key=invocation_key)
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
            attempt = session.get(RepairAttemptModel, context["attempt_id"])
            if attempt is None:
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED",
                    "Repair attempt is missing",
                )
            artifact_id = getattr(attempt, artifact_field)
            if not artifact_id:
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED",
                    "Completed repair LLM invocation has no persisted artifact",
                )
            metadata = session.get(ArtifactMetadataModel, "metadata-" + artifact_id)
            if metadata is None:
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED",
                    "Completed repair artifact is not registered",
                )
            relative_path = metadata.relative_path
        root = Path(str(context["artifact_root"]))
        store = LocalFilesystemArtifactStore(root.parent, fixed_run_root=root)
        try:
            content = store.read_artifact(str(context["run_id"]), relative_path).content
            return json.loads(content)
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError) as exc:
            raise RepairApplicationError(
                "REPAIR_ARTIFACT_RECOVERY_FAILED",
                "Completed repair artifact cannot be loaded",
            ) from exc

    def _start_invocation(
        self, context, *, role: LlmRole, task_type: LlmTaskType, schema_name: str, schema
    ) -> None:
        invocation_id = _invocation_key(str(context["attempt_id"]), role)
        now = self._now()
        request_checksum = "sha256:" + hashlib.sha256(
            json.dumps(context["segments"], sort_keys=True).encode()
        ).hexdigest()
        input_hashes = [
            str(context["failure_evidence_checksum"]),
            str(context["context_pack_checksum"]),
            "schema:"
            + hashlib.sha256(json.dumps(schema.model_json_schema(), sort_keys=True).encode()).hexdigest(),
        ]
        prompt_version = self._prompt_version(schema_name, task_type)
        schema_version = get_settings().llm_schema_registry_version
        try:
            with self._scope() as session:
                session.add(
                    LlmInvocationModel(
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
                    )
                )
        except IntegrityError:
            with self._scope() as session:
                existing = (
                    session.query(LlmInvocationModel)
                    .filter_by(idempotency_key=invocation_id)
                    .one_or_none()
                )
                if existing is None:
                    raise
                existing.request_checksum = request_checksum
                existing.input_hashes = input_hashes
                existing.prompt_version = prompt_version
                existing.schema_version = schema_version
                existing.status = "in_progress"
                existing.transport_started = False
                existing.completed_at = None

    def _mark_transport_started(self, context, role: LlmRole) -> None:
        with self._scope() as session:
            invocation = (
                session.query(LlmInvocationModel)
                .filter_by(idempotency_key=_invocation_key(str(context["attempt_id"]), role))
                .one_or_none()
            )
            if invocation is not None and invocation.status == "in_progress":
                invocation.transport_started = True

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
            self._register_artifact_metadata(session, context, stored)
            invocation = (
                session.query(LlmInvocationModel)
                .filter_by(idempotency_key=_invocation_key(str(context["attempt_id"]), role))
                .one_or_none()
            )
            if invocation is None:
                return
            invocation.status = "failed"
            invocation.artifact_ids = list(
                dict.fromkeys([*(invocation.artifact_ids or []), stored.ref.artifact_id])
            )
            invocation.artifact_checksums = {
                **(invocation.artifact_checksums or {}),
                stored.ref.artifact_id: stored.ref.checksum,
            }
            invocation.failure_code = error.code
            invocation.failure_stage = (
                failure_stage_override or getattr(error, "failure_stage", None) or "local"
            )
            invocation.failure_subtype = getattr(error, "failure_subtype", None)
            invocation.provider_http_status = getattr(cause, "provider_status", None)
            invocation.provider_error_code = getattr(cause, "provider_code", None)
            invocation.sanitized_provider_message = _bounded_text(
                getattr(cause, "provider_message", None)
            )
            if request_id and not invocation.provider_request_id:
                invocation.provider_request_id = request_id
            invocation.response_received = response_received
            invocation.response_content_type = getattr(cause, "response_content_type", None)
            invocation.response_bytes = getattr(cause, "response_bytes", None)
            invocation.response_sha256 = getattr(cause, "response_sha256", None)
            invocation.response_kind = getattr(cause, "response_kind", None) or (
                "json" if response is not None else None
            )
            invocation.transport_started = transport_started
            invocation.retryable = getattr(error, "retryable", None)
            invocation.retries = (invocation.retries or 0) + retries
            invocation.transport_exception_type = (
                type(error.__cause__).__name__ if error.__cause__ else None
            )
            invocation.completed_at = now

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
            attempt = session.get(RepairAttemptModel, context["attempt_id"])
            invocation_id = _invocation_key(attempt.id, role)
            now = self._now()
            invocation = (
                session.query(LlmInvocationModel)
                .filter_by(idempotency_key=invocation_id)
                .one_or_none()
            )
            if invocation is None:
                invocation = LlmInvocationModel(
                    id=invocation_id,
                    run_id=attempt.run_id,
                    stage_id=attempt.stage_id,
                    idempotency_key=invocation_id,
                    request_checksum="sha256:" + hashlib.sha256(
                        json.dumps(context["segments"], sort_keys=True).encode()
                    ).hexdigest(),
                    input_hashes=[
                        str(attempt.failure_evidence_checksum),
                        str(attempt.context_pack_checksum),
                    ],
                    correlation_id=invocation_id,
                    actor="transformer",
                    role=response.role.value,
                    task_type=response.task_type.value,
                    provider="azure_openai",
                    deployment_alias=response.model_deployment_alias,
                    prompt_version=response.prompt_version
                    or self._prompt_version(schema_name, response.task_type),
                    schema_version=response.schema_version or get_settings().llm_schema_registry_version,
                    pricing_version=response.pricing_version or get_settings().llm_pricing_version,
                    stage="repair",
                    redacted_summary=json.dumps(summary, sort_keys=True),
                    status="completed",
                    artifact_ids=[stored.ref.artifact_id],
                    artifact_checksums={stored.ref.artifact_id: stored.ref.checksum},
                    state_version=1,
                    event_sequence=0,
                    retries=response.usage.retry_count,
                    provider_request_id=response.provider_request_id,
                    started_at=now,
                    completed_at=now,
                    created_at=now,
                )
                session.add(invocation)
            else:
                invocation.status = "completed"
                invocation.failure_code = None
                invocation.role = response.role.value
                invocation.task_type = response.task_type.value
                invocation.deployment_alias = response.model_deployment_alias
                invocation.prompt_version = response.prompt_version or self._prompt_version(
                    schema_name, response.task_type
                )
                invocation.schema_version = (
                    response.schema_version or get_settings().llm_schema_registry_version
                )
                invocation.pricing_version = (
                    response.pricing_version or get_settings().llm_pricing_version
                )
                invocation.redacted_summary = json.dumps(summary, sort_keys=True)
                invocation.artifact_ids = [stored.ref.artifact_id]
                invocation.artifact_checksums = {stored.ref.artifact_id: stored.ref.checksum}
                invocation.retries = (invocation.retries or 0) + (response.usage.retry_count or 0)
                if response.provider_request_id and not invocation.provider_request_id:
                    invocation.provider_request_id = response.provider_request_id
                invocation.transport_started = True
                invocation.response_received = True
                invocation.completed_at = now
                started_at = invocation.started_at
                if started_at is not None and started_at.tzinfo is not None:
                    invocation.latency_ms = max(
                        0, int((now - started_at).total_seconds() * 1000)
                    )
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
