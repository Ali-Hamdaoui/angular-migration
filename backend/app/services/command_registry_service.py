"""Command registry and policy engine application services for G01.

StructuredCommandRegistry and CommandPolicyEngine are the sole pre-execution
authorization path. Every command must be validated through these services
before process creation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4
from typing import Any
from pathlib import Path
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.command import (
    AuthorizationCheckResult,
    AuthorizationDecision,
    AuthorizationRequest,
    AuthorizationResult,
    CancellationPolicy,
    CommandTemplate,
    CommandTemplateStatus,
    DEFAULT_COMMAND_TEMPLATES,
    NetworkProfile,
)
from app.domain.contracts import (
    CommandTemplateDto,
    CommandTemplateListDto,
    CommandPolicyValidateRequestDto,
    CommandPolicyValidateResponseDto,
    WorkflowEventType,
)


class CommandRegistryError(ValueError):
    """Raised when a registry operation fails."""
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class CommandPolicyError(ValueError):
    """Raised when a policy evaluation fails."""
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: dict[str, Any] = {}


@dataclass(frozen=True)
class CommandRegistryService:
    """Structured command template registry with seeding and query support."""

    policy_version: str = "s3-f01-v1"

    def list_templates(self, session: Session, *, run_id: str | None = None) -> CommandTemplateListDto:
        """Return all active command templates."""
        from app.repositories.models.workflow import CommandTemplateModel

        stmt = select(CommandTemplateModel).order_by(CommandTemplateModel.command_id)
        rows = list(session.scalars(stmt))
        templates = [self._model_to_dto(r) for r in rows] if rows else self._default_templates()
        return CommandTemplateListDto(templates=templates, total=len(templates))

    def get_template(self, session: Session, template_id: str) -> CommandTemplateDto | None:
        """Get a single template by ID."""
        from app.repositories.models.workflow import CommandTemplateModel

        row = session.get(CommandTemplateModel, template_id)
        if row is None:
            return None
        return self._model_to_dto(row)

    def find_template_by_command_id(self, session: Session, command_id: str) -> CommandTemplateDto | None:
        """Find the active template for a given command_id."""
        from app.repositories.models.workflow import CommandTemplateModel

        row = session.scalar(
            select(CommandTemplateModel)
            .where(CommandTemplateModel.command_id == command_id)
            .where(CommandTemplateModel.status == CommandTemplateStatus.ACTIVE.value)
            .limit(1)
        )
        if row is None:
            return None
        return self._model_to_dto(row)

    def find_registered_template(
        self, session: Session, *, template_id: str, command_id: str, version: int
    ) -> CommandTemplateDto | None:
        """Load the immutable template version named by an approved plan."""
        from app.repositories.models.workflow import CommandTemplateModel

        row = session.scalar(
            select(CommandTemplateModel)
            .where(CommandTemplateModel.id == template_id)
            .where(CommandTemplateModel.command_id == command_id)
            .where(CommandTemplateModel.version == version)
            .where(CommandTemplateModel.status == CommandTemplateStatus.ACTIVE.value)
        )
        return self._model_to_dto(row) if row is not None else None

    def seed_defaults(self, session: Session) -> list[CommandTemplateDto]:
        """Seed default command templates if the registry is empty."""
        from app.repositories.models.workflow import CommandTemplateModel

        existing = session.scalar(select(CommandTemplateModel).limit(1))
        if existing is not None:
            return self.list_templates(session).templates

        now = datetime.now(UTC)
        seeded: list[CommandTemplateDto] = []
        for tpl in DEFAULT_COMMAND_TEMPLATES:
            row = CommandTemplateModel(
                id=tpl.template_id,
                command_id=tpl.command_id,
                executable=tpl.executable,
                arguments=list(tpl.arguments),
                executable_aliases=list(tpl.executable_aliases),
                description=tpl.description,
                status=tpl.status.value,
                version=tpl.version,
                allowed_env_vars=list(tpl.allowed_env_vars),
                max_output_bytes=tpl.max_output_bytes,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            seeded.append(self._model_to_dto(row))
        session.flush()
        return seeded

    @staticmethod
    def _model_to_dto(row: Any) -> CommandTemplateDto:
        return CommandTemplateDto(
            template_id=row.id,
            command_id=row.command_id,
            executable=row.executable,
            arguments=list(row.arguments) if row.arguments else [],
            executable_aliases=list(row.executable_aliases) if row.executable_aliases else [],
            description=row.description or "",
            status=row.status or "active",
            version=row.version or 1,
            allowed_env_vars=list(row.allowed_env_vars) if row.allowed_env_vars else [],
            max_output_bytes=row.max_output_bytes,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _default_templates(self) -> list[CommandTemplateDto]:
        """Fallback when the DB table is empty."""
        return [
            CommandTemplateDto(
                template_id=t.template_id,
                command_id=t.command_id,
                executable=t.executable,
                arguments=list(t.arguments),
                executable_aliases=list(t.executable_aliases),
                description=t.description,
                status=t.status.value,
                version=t.version,
                allowed_env_vars=list(t.allowed_env_vars),
                max_output_bytes=t.max_output_bytes,
            )
            for t in DEFAULT_COMMAND_TEMPLATES
        ]


@dataclass(frozen=True)
class CommandPolicyEngineService:
    """Policy engine that authorizes or rejects command execution.

    Applies the following checks conjunctively:
    - Command is registered in the structured registry.
    - Executable matches the template.
    - Arguments match the template (no arbitrary args).
    - shell=false is enforced.
    - Network profile is allowed.
    - Cancellation policy is supported.
    - Timeout is within allowed range.
    - If plan membership is required, the command_id appears in the plan.
    """

    registry: CommandRegistryService = field(default_factory=CommandRegistryService)
    policy_version: str = "s3-f01-v1"

    def validate(
        self,
        session: Session,
        request: CommandPolicyValidateRequestDto,
    ) -> CommandPolicyValidateResponseDto:
        """Run all policy checks and return an authorization decision."""
        from app.repositories.models.workflow import CommandAuthorizationAuditModel, MigrationRunModel

        correlation_id = request.correlation_id or uuid4().hex
        run = session.get(MigrationRunModel, request.run_id)
        if run is not None and run.state_version != request.expected_state_version:
            error = CommandPolicyError(
                "STALE_STATE_VERSION",
                "The run snapshot is stale; refresh the authoritative run snapshot and retry.",
            )
            error.details = {
                "run_id": request.run_id,
                "requested_state_version": request.expected_state_version,
                "current_state_version": run.state_version,
                "correlation_id": correlation_id,
                "guidance": "Refresh the run snapshot before retrying.",
            }
            raise error

        payload_hash = self._request_payload_hash(request)
        existing = session.scalar(select(CommandAuthorizationAuditModel).where(
            CommandAuthorizationAuditModel.run_id == request.run_id,
            CommandAuthorizationAuditModel.idempotency_key == request.idempotency_key,
        ))
        if existing is not None:
            if existing.request_payload_hash != payload_hash:
                error = CommandPolicyError("IDEMPOTENCY_KEY_REUSED", "The idempotency key is already bound to a different request payload.")
                error.details = {"run_id": request.run_id, "idempotency_key": request.idempotency_key, "correlation_id": correlation_id}
                raise error
            return self._response_from_audit(existing, replay=True)

        authorization_id = f"authz-{uuid4().hex[:12]}"
        checks: list[AuthorizationCheckResult] = []
        reasons: list[str] = []

        # 1. Shell enforcement
        checks.append(self._check_shell_enforcement(request))
        if not checks[-1].passed:
            reasons.append(checks[-1].reason or "shell execution rejected")

        # 2. Template lookup
        template = self.registry.find_template_by_command_id(session, request.command_id)
        if template is None:
            checks.append(AuthorizationCheckResult(
                passed=False,
                rule_name="command_registered",
                reason=f"command_id '{request.command_id}' is not registered",
            ))
            reasons.append(f"command_id '{request.command_id}' is not registered")
        else:
            checks.append(AuthorizationCheckResult(passed=True, rule_name="command_registered"))

            if request.template_id is None or request.template_version is None:
                checks.append(AuthorizationCheckResult(
                    passed=False, rule_name="registered_template_version",
                    reason="TEMPLATE_VERSION_REQUIRED: exact registered template id and version are required",
                ))
                reasons.append("TEMPLATE_VERSION_REQUIRED: exact registered template id and version are required")
            elif self.registry.find_registered_template(
                session, template_id=request.template_id, command_id=request.command_id,
                version=request.template_version,
            ) is None:
                checks.append(AuthorizationCheckResult(
                    passed=False, rule_name="registered_template_version",
                    reason="TEMPLATE_VERSION_NOT_FOUND: exact registered template version was not found",
                ))
                reasons.append("TEMPLATE_VERSION_NOT_FOUND: exact registered template version was not found")

            # 3. Executable matches template
            allowed = set(template.executable_aliases + [template.executable])
            if request.executable not in allowed:
                checks.append(AuthorizationCheckResult(
                    passed=False,
                    rule_name="executable_matches_template",
                    reason=f"executable '{request.executable}' not in allowed set: {allowed}",
                ))
                reasons.append("executable mismatch")
            else:
                checks.append(AuthorizationCheckResult(passed=True, rule_name="executable_matches_template"))

            # 4. Arguments match template (exact match)
            if list(template.arguments) != request.arguments:
                checks.append(AuthorizationCheckResult(
                    passed=False,
                    rule_name="arguments_match_template",
                    reason=f"arguments {request.arguments} do not match template {template.arguments}",
                ))
                reasons.append("argument mismatch")
            else:
                checks.append(AuthorizationCheckResult(passed=True, rule_name="arguments_match_template"))

        # 5. Network profile allowed
        net_check = self._check_network_profile(request.network_profile)
        checks.append(net_check)
        if not net_check.passed:
            reasons.append(net_check.reason or "network profile rejected")

        # 6. Cancellation policy
        cancel_check = self._check_cancellation_policy(request.cancellation_policy)
        checks.append(cancel_check)
        if not cancel_check.passed:
            reasons.append(cancel_check.reason or "cancellation policy rejected")

        # 7. Timeout within range
        timeout_check = self._check_timeout(request.timeout_seconds)
        checks.append(timeout_check)
        if not timeout_check.passed:
            reasons.append(timeout_check.reason or "timeout rejected")

        # 8. Plan membership if required
        plan_check = self._check_plan_membership(session, request)
        checks.append(plan_check)
        if not plan_check.passed:
            reasons.append(plan_check.reason or "plan membership rejected")

        decision = AuthorizationDecision.REJECTED if reasons else AuthorizationDecision.ACCEPTED
        response = CommandPolicyValidateResponseDto(
            authorization_id=authorization_id,
            run_id=request.run_id,
            stage_id=request.stage_id,
            command_id=request.command_id,
            executable=request.executable,
            arguments=request.arguments,
            cwd_alias=request.cwd_alias or "",
            plan_id=request.plan_id,
            execution_profile_id=request.execution_profile_id,
            decision=decision.value,
            reasons=reasons,
            policy_version=self.policy_version,
            expected_state_version=request.expected_state_version,
            authoritative_state_version=run.state_version if run is not None else request.expected_state_version,
            artifact_id=None,
            correlation_id=correlation_id,
            request_payload_hash=payload_hash,
        )

        # Persist authorization audit record
        from app.repositories.models.workflow import CommandAuthorizationAuditModel
        now = datetime.now(UTC)
        audit = CommandAuthorizationAuditModel(
            id=authorization_id,
            run_id=request.run_id,
            stage_id=request.stage_id,
            command_id=request.command_id,
            executable=request.executable,
            arguments=request.arguments,
            decision=decision.value,
            reasons=reasons,
            policy_version=self.policy_version,
            idempotency_key=request.idempotency_key,
            request_payload_hash=payload_hash,
            expected_state_version=request.expected_state_version,
            template_id=request.template_id,
            template_version=request.template_version,
            plan_id=request.plan_id,
            plan_version=request.plan_version,
            execution_profile_id=request.execution_profile_id,
            workspace_alias=request.working_directory_alias or request.cwd_alias,
            network_profile=request.network_profile,
            correlation_id=correlation_id,
            actor=request.requested_by,
            artifact_ids=[],
            state_version=run.state_version if run is not None else request.expected_state_version,
            created_at=now,
        )
        session.add(audit)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            existing = session.scalar(select(CommandAuthorizationAuditModel).where(
                CommandAuthorizationAuditModel.run_id == request.run_id,
                CommandAuthorizationAuditModel.idempotency_key == request.idempotency_key,
            ))
            if existing is None:
                raise
            if existing.request_payload_hash != payload_hash:
                raise CommandPolicyError("IDEMPOTENCY_KEY_REUSED", "The idempotency key is already bound to a different request payload.")
            return self._response_from_audit(existing, replay=True)

        # Finalize sanitized evidence before the decision can be returned.
        if run is not None and run.artifact_root:
            from app.artifact_store import LocalFilesystemArtifactStore
            from app.domain.contracts import ArtifactType
            from app.repositories.models import ArtifactMetadataModel
            evidence = {
                "evidence_schema_version": 1,
                "authorization_decision_id": authorization_id,
                "run_id": request.run_id,
                "stage_id": request.stage_id,
                "plan_id": request.plan_id,
                "plan_version": request.plan_version,
                "command_template_id": request.template_id,
                "command_template_version": request.template_version,
                "command_id": request.command_id,
                "sanitized_arguments": list(request.arguments),
                "execution_profile_id": request.execution_profile_id,
                "workspace_alias": request.working_directory_alias or request.cwd_alias,
                "network_profile": request.network_profile,
                "expected_state_version": request.expected_state_version,
                "authoritative_state_version": audit.state_version,
                "result": decision.value,
                "error_codes": [reason.split(":", 1)[0] for reason in reasons],
                "safe_reasons": reasons,
                "correlation_id": correlation_id,
                "idempotency_key": request.idempotency_key,
                "request_payload_hash": payload_hash,
                "decision_timestamp": now.isoformat(),
            }
            store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
            stored = store.write_text_artifact(run.id, f"04_workflow_state/authorization/{authorization_id}.json", json.dumps(evidence, sort_keys=True), ArtifactType.JSON, stage_id=request.stage_id, created_by="command-policy-engine", created_at=now, input_hashes={"request": payload_hash}, policy_version=self.policy_version)
            session.add(ArtifactMetadataModel(id=f"metadata-{stored.ref.artifact_id}", run_id=run.id, stage_id=request.stage_id, artifact_type=stored.ref.artifact_type.value, relative_path=stored.ref.relative_path, checksum=stored.ref.checksum, created_at=now))
            audit.artifact_ids = [stored.ref.artifact_id]

        # Emit authorization event
        from app.repositories.models.workflow import WorkflowEventModel
        latest = session.scalar(
            select(WorkflowEventModel)
            .where(WorkflowEventModel.run_id == request.run_id)
            .order_by(WorkflowEventModel.sequence.desc())
            .limit(1)
        )
        event_type = (
            WorkflowEventType.COMMAND_AUTHORIZATION_ACCEPTED
            if decision.value == "accepted"
            else WorkflowEventType.COMMAND_AUTHORIZATION_REJECTED
        )
        event = WorkflowEventModel(
            id=f"event-{uuid4().hex[:12]}",
            run_id=request.run_id,
            stage_id=request.stage_id,
            event_type=event_type.value,
            idempotency_key=request.idempotency_key,
            actor=request.requested_by or "system",
            reason=f"command authorization {decision.value}",
            sequence=(latest.sequence + 1) if latest else 1,
            payload={
                "authorization_id": authorization_id,
                "command_id": request.command_id,
                "stage_id": request.stage_id,
                "plan_id": request.plan_id,
                "plan_version": request.plan_version,
                "template_id": request.template_id,
                "template_version": request.template_version,
                "execution_profile_id": request.execution_profile_id,
                "workspace_alias": request.working_directory_alias or request.cwd_alias,
                "network_profile": request.network_profile,
                "decision": decision.value,
                "reasons": reasons,
                "policy_version": self.policy_version,
                "state_version": audit.state_version,
                "correlation_id": correlation_id,
                "request_payload_hash": payload_hash,
                "artifact_ids": list(audit.artifact_ids),
                "artifact_checksums": ({audit.artifact_ids[0]: session.get(ArtifactMetadataModel, f"metadata-{audit.artifact_ids[0]}").checksum} if audit.artifact_ids else {}),
            },
            occurred_at=now,
        )
        session.add(event)
        session.flush()

        return self._response_from_audit(audit, replay=False)

    @staticmethod
    def _request_payload_hash(request: CommandPolicyValidateRequestDto) -> str:
        payload = request.model_dump(mode="json", exclude={"correlation_id"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _response_from_audit(audit, *, replay: bool) -> CommandPolicyValidateResponseDto:
        return CommandPolicyValidateResponseDto(
            authorization_id=audit.id, run_id=audit.run_id, stage_id=audit.stage_id,
            plan_id=audit.plan_id, command_id=audit.command_id, executable=audit.executable,
            arguments=list(audit.arguments or []), execution_profile_id=audit.execution_profile_id or "source-runtime-profile",
            decision=audit.decision, reasons=list(audit.reasons or []), policy_version=audit.policy_version,
            idempotent_replay=replay, expected_state_version=audit.expected_state_version,
            authoritative_state_version=audit.state_version, artifact_id=(audit.artifact_ids or [None])[0],
            correlation_id=audit.correlation_id, request_payload_hash=audit.request_payload_hash,
            decision_timestamp=audit.created_at,
        )

    def _check_shell_enforcement(self, request: CommandPolicyValidateRequestDto) -> AuthorizationCheckResult:
        """Reject any request attempting shell execution."""
        if request.shell is not False:
            return AuthorizationCheckResult(
                passed=False,
                rule_name="shell_enforcement",
                reason="SHELL_EXECUTION_FORBIDDEN: shell execution is forbidden",
            )
        return AuthorizationCheckResult(passed=True, rule_name="shell_enforcement")

    def _check_network_profile(self, profile: str) -> AuthorizationCheckResult:
        allowed = {p.value for p in NetworkProfile} | {"approved-registries-only"}
        if profile not in allowed:
            return AuthorizationCheckResult(
                passed=False,
                rule_name="network_profile",
                reason=f"network profile '{profile}' is not allowed",
            )
        return AuthorizationCheckResult(passed=True, rule_name="network_profile")

    def _check_cancellation_policy(self, policy: str) -> AuthorizationCheckResult:
        allowed = {p.value for p in CancellationPolicy}
        if policy not in allowed:
            return AuthorizationCheckResult(
                passed=False,
                rule_name="cancellation_policy",
                reason=f"cancellation policy '{policy}' is not supported",
            )
        return AuthorizationCheckResult(passed=True, rule_name="cancellation_policy")

    def _check_timeout(self, timeout_seconds: int) -> AuthorizationCheckResult:
        if timeout_seconds <= 0:
            return AuthorizationCheckResult(
                passed=False,
                rule_name="timeout",
                reason="timeout must be greater than zero",
            )
        if timeout_seconds > 3600:
            return AuthorizationCheckResult(
                passed=False,
                rule_name="timeout",
                reason="timeout exceeds maximum of 3600 seconds",
            )
        return AuthorizationCheckResult(passed=True, rule_name="timeout")

    def _check_plan_membership(
        self,
        session: Session,
        request: CommandPolicyValidateRequestDto,
    ) -> AuthorizationCheckResult:
        """Verify every client-supplied binding against the current approved plan."""
        from app.repositories.models.workflow import MigrationRunModel
        from app.repositories.planning_models import MigrationPlanModel, StageExecutionPlanModel

        def reject(code: str, message: str) -> AuthorizationCheckResult:
            return AuthorizationCheckResult(False, "plan_membership", f"{code}: {message}")

        run = session.get(MigrationRunModel, request.run_id)
        if run is None:
            return reject("PLAN_NOT_FOUND", "run record is unavailable")
        if run.status in {"CANCELLED", "COMPLETED", "FAILED", "CANCELLING", "CANCEL_REQUESTED"}:
            return reject("RUN_NOT_EXECUTABLE", "run is not in an executable state")
        if not request.stage_id or not request.plan_id or request.plan_version is None:
            return reject("PLAN_NOT_FOUND", "run, stage, approved plan id, and version must be supplied")

        migration_plan = session.scalar(
            select(MigrationPlanModel)
            .where(MigrationPlanModel.id == request.plan_id)
            .where(MigrationPlanModel.run_id == request.run_id)
        )
        if migration_plan is None or migration_plan.run_id != request.run_id or migration_plan.version != request.plan_version:
            return reject("PLAN_NOT_FOUND", "approved stage execution plan is unavailable")
        plan = session.scalar(
            select(StageExecutionPlanModel)
            .where(StageExecutionPlanModel.migration_plan_id == migration_plan.id)
            .where(StageExecutionPlanModel.run_id == request.run_id)
            .where(StageExecutionPlanModel.stage_id == request.stage_id)
            .where(StageExecutionPlanModel.version == request.plan_version)
        )
        if plan is None:
            return reject("PLAN_NOT_FOUND", "authoritative migration plan is unavailable or mismatched")
        if plan.status not in {"approved", "executable", "approved_for_execution"} or migration_plan.status not in {"approved", "executable", "approved_for_execution"}:
            return reject("PLAN_NOT_APPROVED", "plan is not approved for execution")

        stage_data = plan.stage_plan or {}
        if stage_data.get("stage_id") != request.stage_id or stage_data.get("execution_profile_id") != request.execution_profile_id:
            return reject("EXECUTION_PROFILE_NOT_APPROVED", "stage or execution profile does not match the approved plan")
        if stage_data.get("plan_version") != request.plan_version:
            return reject("PLAN_NOT_FOUND", "stage plan version is not authoritative")

        refs = [ref for group in (stage_data.get("commands") or {}).values() for ref in group]
        planned = next((ref for ref in refs if ref.get("command_id") == request.command_id), None)
        if planned is None:
            return reject("COMMAND_NOT_IN_APPROVED_PLAN", "command template is not in the approved plan")
        if planned.get("working_directory_alias") != request.working_directory_alias:
            return reject("WORKSPACE_NOT_APPROVED", "workspace alias does not match the approved planned command")
        if request.cwd_alias is not None and request.cwd_alias != request.working_directory_alias:
            return reject("WORKSPACE_NOT_APPROVED", "cwd alias does not match the approved workspace alias")
        if planned.get("network_profile") != request.network_profile:
            return reject("NETWORK_PROFILE_NOT_ALLOWED", "network profile is not explicitly permitted by the plan")
        if (
            planned.get("executable") != request.executable
            or list(planned.get("arguments") or []) != list(request.arguments)
            or planned.get("shell", False) is not False
            or request.template_id is None
        ):
            return reject("COMMAND_NOT_IN_APPROVED_PLAN", "structured command does not match the approved planned command")
        if request.shell is not False:
            return reject("SHELL_EXECUTION_FORBIDDEN", "shell execution is forbidden")
        if planned.get("timeout_seconds") != request.timeout_seconds:
            return reject("COMMAND_NOT_IN_APPROVED_PLAN", "timeout does not match the approved planned command")
        if planned.get("cancellation_policy") is not None and planned.get("cancellation_policy") != request.cancellation_policy:
            return reject("COMMAND_NOT_IN_APPROVED_PLAN", "cancellation policy does not match the approved planned command")

        aliases = run.workspace_aliases or {}
        alias = request.working_directory_alias
        if not alias or alias not in aliases:
            return reject("WORKSPACE_NOT_APPROVED", "workspace alias is not approved for this run")
        if not request.working_directory:
            return reject("WORKSPACE_CONFINEMENT_VIOLATION", "canonical working directory is required")
        try:
            root = Path(str(aliases[alias])).resolve(strict=False)
            candidate_input = Path(request.working_directory)
            candidate = (root / candidate_input).resolve(strict=False) if not candidate_input.is_absolute() else candidate_input.resolve(strict=False)
            candidate.relative_to(root)
        except (OSError, ValueError, RuntimeError, TypeError):
            return reject("WORKSPACE_CONFINEMENT_VIOLATION", "working directory is outside the run-owned workspace")
        return AuthorizationCheckResult(True, "plan_membership")
