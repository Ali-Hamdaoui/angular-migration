"""Governed repair proposal/review and deterministic semantic validation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

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

_DETERMINISTIC_LOCAL_FAILURE_CODES = {
    "LLM_PROMPT_POLICY_MISSING",
    "LLM_SCHEMA_POLICY_MISSING",
    "LLM_CONFIGURATION_INVALID",
}


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


class RepairOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: str = Field(
        pattern="^(replace_text|create_text_file|delete_text_file|dependency_change)$"
    )
    path: str = Field(min_length=1, max_length=500)
    preimage_sha256: str | None = None
    old_text: str | None = None
    new_text: str | None = None
    content: str | None = None


class RepairProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_evidence_checksum: str
    context_pack_checksum: str
    proposal_format: str = Field(pattern="^(operations|unified_diff)$")
    operations: list[RepairOperation] = Field(max_length=32)
    unified_diff: str | None = Field(default=None, max_length=100_000)
    touched_files: list[str] = Field(min_length=1, max_length=32)
    rationale: list[str] = Field(min_length=1, max_length=16)
    risk_level: str = Field(pattern="^(low|medium|high)$")
    validation_targets: list[str] = Field(min_length=1, max_length=16)
    limitations: list[str] = Field(max_length=16)


class RepairReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_checksum: str
    decision: str = Field(pattern="^(accept|request_changes|reject)$")
    findings: list[str] = Field(max_length=32)
    policy_checks: list[str] = Field(min_length=1, max_length=32)
    risk_assessment: str = Field(min_length=1, max_length=2000)
    required_validation_targets: list[str] = Field(min_length=1, max_length=16)
    limitations: list[str] = Field(max_length=16)


class RepairApplicationService:
    proposer_schema = "repair_proposer_v1"
    reviewer_schema = "repair_reviewer_v1"
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
        output, response = self._call(
            context,
            role=LlmRole.REPAIR_PROPOSER,
            task=LlmTaskType.REPAIR_DIAGNOSIS,
            schema_name=self.proposer_schema,
            schema=RepairProposal,
            policy=(
                "Author one minimal repair candidate from untrusted evidence. Never emit commands, "
                "lockfile edits, path escapes, secrets, or policy bypasses."
            ),
        )
        proposal = self.validate_proposal(output, context)
        stored = self._write(context, "proposal", proposal)
        self._persist_call(context, response, stored, role="proposer", summary=proposal)
        return proposal

    def review(self, attempt_id: str) -> dict[str, object]:
        context = self._attempt_context(attempt_id, include_proposal=True)
        recovered = self._recover_completed(context, role="reviewer")
        if recovered is not None:
            return recovered
        output, response = self._call(
            context,
            role=LlmRole.REPAIR_REVIEWER,
            task=LlmTaskType.REPAIR_REVIEW,
            schema_name=self.reviewer_schema,
            schema=RepairReview,
            policy=(
                "Review the supplied proposal against policy. Never author operations, a diff, "
                "replacement code, commands, or a different proposal."
            ),
        )
        review = RepairReview.model_validate(output).model_dump(mode="json")
        if review["proposal_checksum"] != context["proposal_checksum"]:
            raise RepairApplicationError("REPAIR_REVIEW_STALE", "Reviewer bound a different proposal")
        stored = self._write(context, "review", review)
        self._persist_call(context, response, stored, role="reviewer", summary=review)
        return review

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
        context["segments"] = [
            store.read_artifact(str(context["run_id"]), metadata[artifact_id]).content
            for artifact_id in artifact_ids
        ]
        return context

    def _call(self, context, *, role, task, schema_name, schema, policy):
        if self._gateway is None and not get_settings().llm_enabled:
            raise RepairApplicationError(
                "REPAIR_LLM_DISABLED", "Governed repair requires the configured Azure gateway"
            )
        registry = PromptSchemaRegistry(version=get_settings().llm_schema_registry_version)
        registry.register(schema_name, schema)
        gateway = self._gateway or AzureOpenAILLMGateway(settings=get_settings(), registry=registry)
        try:
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
            if translated.code in _DETERMINISTIC_LOCAL_FAILURE_CODES:
                self._persist_deterministic_failure(context, role, translated)
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
            if invocation.status != "completed":
                raise RepairApplicationError(
                    "REPAIR_ARTIFACT_RECOVERY_FAILED",
                    "Completed repair LLM invocation is not finalized",
                )
            attempt = session.get(RepairAttemptModel, context["attempt_id"])
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

    def _persist_deterministic_failure(self, context, role, error: RepairLlmError) -> None:
        kind = "propose-error" if role == LlmRole.REPAIR_PROPOSER else "review-error"
        stored = self._write(
            context,
            kind,
            {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
                "failure_stage": error.failure_stage,
                "provider_status": error.provider_status,
                "provider_request_id": error.provider_request_id,
                "failure_subtype": error.failure_subtype,
            },
        )
        with self._scope() as session:
            self._register_artifact_metadata(session, context, stored)

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
            created_by=f"repair-{kind}",
            created_at=self._now(),
            input_hashes={
                "failure": str(context["failure_evidence_checksum"]),
                "context": str(context["context_pack_checksum"]),
            },
            policy_version=f"repair-{kind}-v1",
        )

    def _persist_call(self, context, response, stored, *, role, summary):
        with self._scope() as session:
            attempt = session.get(RepairAttemptModel, context["attempt_id"])
            invocation_id = f"{attempt.id}:{role}"
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
                prompt_version=response.prompt_version or f"repair-{role}-v1",
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
                started_at=self._now(),
                completed_at=self._now(),
                created_at=self._now(),
            )
            session.add(invocation)
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
                    created_at=self._now(),
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
            attempt.updated_at = self._now()

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
