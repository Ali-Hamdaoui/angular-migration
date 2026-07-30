"""Governed repair proposal/review and deterministic semantic validation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.artifact_store import LocalFilesystemArtifactStore
from app.core.config import get_settings
from app.domain.contracts import AgentKind, ArtifactType
from app.llm_gateway import (
    AzureOpenAILLMGateway,
    LlmContextSegment,
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
            session.add(
                ArtifactMetadataModel(
                    id="metadata-" + stored.ref.artifact_id,
                    run_id=attempt.run_id,
                    stage_id=attempt.stage_id,
                    artifact_type=stored.ref.artifact_type.value,
                    relative_path=stored.ref.relative_path,
                    checksum=stored.ref.checksum,
                    created_at=stored.ref.created_at,
                    finalized_at=stored.ref.created_at,
                    immutable=True,
                )
            )
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
