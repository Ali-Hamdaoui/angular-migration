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
    ANGULAR_UPDATE_V2_RENDERER,
    ANGULAR_UPDATE_V3_RENDERER,
    AuthorizationCheckResult,
    AuthorizationDecision,
    AuthorizationRequest,
    AuthorizationResult,
    CancellationPolicy,
    CommandTemplate,
    CommandTemplateStatus,
    DEFAULT_COMMAND_TEMPLATES,
    NPM_DEPENDENCY_INSTALL_RENDERER,
    NPM_DEPENDENCY_UNINSTALL_RENDERER,
    NPM_RUNTIME_DEPENDENCY_INSTALL_RENDERER,
    NPM_ANGULAR_LOCKFILE_NORMALIZE_RENDERER,
    NetworkProfile,
    command_arguments_match,
)
from app.domain.contracts import (
    CommandTemplateDto,
    CommandTemplateListDto,
    CommandPolicyValidateRequestDto,
    CommandPolicyValidateResponseDto,
    WorkflowEventType,
)
from app.services.path_validation_service import is_portable_absolute_path
from app.services.dependency_closure_service import (
    compatible_reinstall_bundle,
    compatible_reinstall_section,
    installed_dependency_version,
    is_exact_version,
    validate_dependency_transition_evidence,
    verify_dependency_transition_evidence_for_source,
)
from app.services.failure_evidence_service import FailureEvidenceService
from app.services.repair_application_service import (
    BlockingDependencyCandidate,
    TargetStateCandidate,
)
from app.state.event_sequencer import append_workflow_event


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

        now = datetime.now(UTC)
        existing_pairs = {
            (row.id, row.version)
            for row in session.query(CommandTemplateModel).all()
        }
        for tpl in DEFAULT_COMMAND_TEMPLATES:
            if (tpl.template_id, tpl.version) in existing_pairs:
                continue
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
        session.flush()
        return self.list_templates(session).templates

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
        *,
        supersedes_authorization_id: str | None = None,
        repair_transition_attempt_id: str | None = None,
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

            # 4. Arguments match template (version-bound when specified)
            if request.template_id and request.template_version is not None:
                version_template = self.registry.find_registered_template(
                    session, template_id=request.template_id, command_id=request.command_id,
                    version=request.template_version,
                )
                match_args = tuple(version_template.arguments) if version_template else tuple(template.arguments)
            else:
                match_args = tuple(template.arguments)
            if not command_arguments_match(match_args, tuple(request.arguments)):
                checks.append(AuthorizationCheckResult(
                    passed=False,
                    rule_name="arguments_match_template",
                    reason=f"arguments {request.arguments} do not match template {match_args}",
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
        plan_check = self._check_plan_membership(
            session,
            request,
            supersedes_authorization_id=supersedes_authorization_id,
            repair_transition_attempt_id=repair_transition_attempt_id,
        )
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
        event_type = (
            WorkflowEventType.COMMAND_AUTHORIZATION_ACCEPTED
            if decision.value == "accepted"
            else WorkflowEventType.COMMAND_AUTHORIZATION_REJECTED
        )
        event = append_workflow_event(
            session,
            run_id=request.run_id,
            stage_id=request.stage_id,
            event_type=event_type.value,
            idempotency_key=request.idempotency_key,
            actor=request.requested_by or "system",
            reason=f"command authorization {decision.value}",
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
                "artifact_checksums": ({audit.artifact_ids[0]: stored.ref.checksum} if audit.artifact_ids else {}),
                "supersedes_authorization_id": supersedes_authorization_id,
            },
            occurred_at=now,
        )
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
            idempotency_key=audit.idempotency_key,
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
        *,
        supersedes_authorization_id: str | None = None,
        repair_transition_attempt_id: str | None = None,
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
        command_refs = [ref for ref in refs if ref.get("command_id") == request.command_id]
        planned = next(
            (
                ref for ref in command_refs
                if ref.get("template_id") == request.template_id
                and ref.get("template_version") == request.template_version
                and ref.get("executable") == request.executable
                and list(ref.get("arguments") or []) == list(request.arguments)
            ),
            command_refs[0] if len(command_refs) == 1 else None,
        )
        repair_transition = bool(
            repair_transition_attempt_id
            and self._valid_repair_dependency_transition(
                session,
                request,
                supersedes_authorization_id=repair_transition_attempt_id,
            )
        )
        if planned is None:
            if not repair_transition:
                return reject("COMMAND_NOT_IN_APPROVED_PLAN", "command template is not in the approved plan")
        elif planned.get("working_directory_alias") != request.working_directory_alias:
            return reject("WORKSPACE_NOT_APPROVED", "workspace alias does not match the approved planned command")
        if request.cwd_alias is not None and request.cwd_alias != request.working_directory_alias:
            return reject("WORKSPACE_NOT_APPROVED", "cwd alias does not match the approved workspace alias")
        if planned is not None and planned.get("network_profile") != request.network_profile:
            return reject("NETWORK_PROFILE_NOT_ALLOWED", "network profile is not explicitly permitted by the plan")
        command_matches_plan = (
            planned is not None
            and (
                planned.get("executable") != request.executable
                or list(planned.get("arguments") or []) != list(request.arguments)
                or planned.get("shell", False) is not False
                or request.template_id is None
            )
        ) is False
        if not command_matches_plan and supersedes_authorization_id and self._valid_angular_update_supersession(
            session,
            request,
            planned,
            supersedes_authorization_id,
        ):
            command_matches_plan = True
        if not command_matches_plan:
            if not repair_transition:
                return reject("COMMAND_NOT_IN_APPROVED_PLAN", "structured command does not match the approved planned command")
            command_matches_plan = True
        if request.shell is not False:
            return reject("SHELL_EXECUTION_FORBIDDEN", "shell execution is forbidden")
        if planned is not None and planned.get("timeout_seconds") != request.timeout_seconds:
            return reject("COMMAND_NOT_IN_APPROVED_PLAN", "timeout does not match the approved planned command")
        if planned is not None and planned.get("cancellation_policy") is not None and planned.get("cancellation_policy") != request.cancellation_policy:
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
            if is_portable_absolute_path(str(request.working_directory)) and not candidate_input.is_absolute():
                return reject("WORKSPACE_CONFINEMENT_VIOLATION", "working directory uses an absolute path from another host")
            candidate = (root / candidate_input).resolve(strict=False) if not candidate_input.is_absolute() else candidate_input.resolve(strict=False)
            candidate.relative_to(root)
        except (OSError, ValueError, RuntimeError, TypeError):
            return reject("WORKSPACE_CONFINEMENT_VIOLATION", "working directory is outside the run-owned workspace")
        return AuthorizationCheckResult(True, "plan_membership")

    @staticmethod
    def _valid_angular_update_supersession(
        session: Session,
        request: CommandPolicyValidateRequestDto,
        planned: dict[str, Any],
        superseded_authorization_id: str,
    ) -> bool:
        """Allow only the immutable v2->v3 stage retry transition."""
        from app.repositories.models.workflow import CommandAuthorizationAuditModel

        if (
            request.command_id != "angular-update-exact"
            or request.template_id != ANGULAR_UPDATE_V3_RENDERER.template_id
            or request.template_version != 3
            or planned.get("template_id") != ANGULAR_UPDATE_V2_RENDERER.template_id
            or planned.get("template_version") != 2
        ):
            return False
        parent = session.get(CommandAuthorizationAuditModel, superseded_authorization_id)
        if (
            parent is None
            or parent.run_id != request.run_id
            or parent.stage_id != request.stage_id
            or parent.plan_id != request.plan_id
            or parent.plan_version != request.plan_version
            or parent.command_id != request.command_id
            or parent.template_id != ANGULAR_UPDATE_V2_RENDERER.template_id
            or parent.template_version != 2
            or list(parent.arguments or []) != list(planned.get("arguments") or [])
        ):
            return False
        try:
            expected_v2 = ANGULAR_UPDATE_V2_RENDERER.render_arguments(
                planned.get("parameter_bindings") or {}
            )
            expected_v3 = ANGULAR_UPDATE_V3_RENDERER.render_arguments(
                planned.get("parameter_bindings") or {}
            )
        except (TypeError, ValueError):
            return False
        return (
            tuple(parent.arguments or []) == expected_v2
            and tuple(request.arguments) == expected_v3
        )

    @staticmethod
    def _valid_repair_dependency_transition(
        session: Session,
        request: CommandPolicyValidateRequestDto,
        supersedes_authorization_id: str | None,
    ) -> bool:
        """Allow only the detach/update/reattach commands bound to an applied repair.

        The superseded id is the RepairAttemptModel id of an applied attempt
        whose committed proposal artifact is exactly one dependency_transition
        operation; the requested command must match the renderer bound to the
        proposal's blocking package and target version. Install commands are
        authorized only for packages and exact versions owned by the
        backend-approved transition bundle resolved from the active workspace.
        """
        from app.artifact_store import (
            ArtifactNotFoundError,
            ArtifactStoreError,
            LocalFilesystemArtifactStore,
        )
        from app.repositories.models.workflow import (
            ArtifactMetadataModel,
            MigrationRunModel,
            RepairAttemptModel,
            StageWorkspaceBindingModel,
            TransformationContinuationModel,
        )
        from app.repositories.planning_models import StageExecutionPlanModel

        attempt = session.get(RepairAttemptModel, supersedes_authorization_id)
        if (
            attempt is None
            or attempt.run_id != request.run_id
            or attempt.stage_id != request.stage_id
            or attempt.status not in {
                "approved_pending_execution",
                "executing",
                "uninstall",
                "angular_update",
                "reinstall",
                "npm_ci",
                "dependency_closure",
            }
            or not attempt.proposal_artifact_id
            or not attempt.proposal_checksum
        ):
            return False
        metadata = session.get(ArtifactMetadataModel, "metadata-" + attempt.proposal_artifact_id)
        run = session.get(MigrationRunModel, request.run_id)
        if metadata is None or run is None or not run.artifact_root:
            return False
        try:
            store = LocalFilesystemArtifactStore(
                Path(run.artifact_root), fixed_run_root=Path(run.artifact_root)
            )
            stored = store.read_artifact(request.run_id, metadata.relative_path)
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, TypeError, ValueError):
            return False
        if (
            stored.ref.checksum != attempt.proposal_checksum
            or stored.envelope is None
            or stored.envelope.run_id != request.run_id
            or stored.envelope.stage_id != request.stage_id
            or stored.envelope.attempt_id != attempt.id
        ):
            return False
        try:
            proposal = json.loads(stored.content)
        except (json.JSONDecodeError, TypeError):
            return False
        if not isinstance(proposal, dict):
            return False
        operations = proposal.get("operations")
        if not isinstance(operations, list) or len(operations) != 1:
            return False
        operation = operations[0]
        if not isinstance(operation, dict) or operation.get("operation") != "dependency_transition":
            return False
        if operation.get("schema_version") != "transformer-repair-v2":
            return False
        if operation.get("repair_kind") != "dependency_transition":
            return False
        if operation.get("strategy") != "detach_update_reattach":
            return False
        if operation.get("failure_type") != "peer_dependency_conflict":
            return False
        blocking = operation.get("blocking_dependency")
        target = operation.get("target_state")
        try:
            blocking_candidate = BlockingDependencyCandidate.model_validate(blocking)
            target_candidate = TargetStateCandidate.model_validate(target)
        except (TypeError, ValueError):
            return False
        if target_candidate.package != blocking_candidate.package:
            return False
        blocking_package = blocking_candidate.package
        target_version = target_candidate.target_version
        target_major = target_candidate.angular_major
        if not is_exact_version(target_version) or not isinstance(target_major, int):
            return False

        evidence_metadata = session.get(
            ArtifactMetadataModel, "metadata-" + str(attempt.failure_evidence_artifact_id)
        )
        if (
            evidence_metadata is None
            or evidence_metadata.checksum != attempt.failure_evidence_checksum
        ):
            return False
        try:
            evidence = json.loads(
                LocalFilesystemArtifactStore(
                    Path(run.artifact_root).parent,
                    fixed_run_root=Path(run.artifact_root),
                ).read_artifact(request.run_id, evidence_metadata.relative_path).content
            )
            evidence, diagnosis = FailureEvidenceService.normalize_dependency_transition_evidence(
                evidence
            )
            authority = validate_dependency_transition_evidence(
                evidence,
                package=blocking_package,
                target_major=target_major,
                installed_version=blocking_candidate.installed_version,
                artifact_id=attempt.failure_evidence_artifact_id,
            )
            if (
                blocking_candidate.installed_version != authority["installed_version"]
                or {
                    item.package: item.version_range
                    for item in blocking_candidate.required_peer_ranges
                }
                != authority["peer_ranges"]
                or target_version != authority["target_version"]
            ):
                return False
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, TypeError, ValueError):
            return False

        continuation = session.scalar(
            select(TransformationContinuationModel)
            .where(TransformationContinuationModel.run_id == request.run_id)
            .order_by(TransformationContinuationModel.created_at.desc())
            .limit(1)
        )
        stage_plan = (
            session.get(StageExecutionPlanModel, continuation.stage_plan_id)
            if continuation is not None
            else None
        )
        stage_data = (stage_plan.stage_plan or {}) if stage_plan is not None else {}
        angular_ref = next(
            (
                ref
                for group in (stage_data.get("commands") or {}).values()
                for ref in group
                if ref.get("command_id") == "angular-update-exact"
            ),
            None,
        )
        planned_alias = angular_ref.get("working_directory_alias") if angular_ref is not None else None
        if planned_alias is not None and request.working_directory_alias != planned_alias:
            return False

        angular_bindings = (angular_ref or {}).get("parameter_bindings") or {}
        target_exact = angular_bindings.get("target_exact") or stage_data.get("target_exact")
        if not is_exact_version(target_exact):
            return False
        if not isinstance(target_major, int) or not target_exact.startswith(f"{target_major}."):
            return False
        if request.command_id == NPM_DEPENDENCY_UNINSTALL_RENDERER.command_id:
            try:
                binding = session.scalar(
                    select(StageWorkspaceBindingModel).where(
                        StageWorkspaceBindingModel.run_id == request.run_id,
                        StageWorkspaceBindingModel.stage_id == request.stage_id,
                        StageWorkspaceBindingModel.active.is_(True),
                    )
                )
                if binding is None:
                    return False
                workspace = Path(binding.workspace_path).resolve(strict=False)
                verify_dependency_transition_evidence_for_source(
                    workspace,
                    diagnosis=diagnosis,
                    package=blocking_package,
                    installed_version=blocking_candidate.installed_version,
                    peer_ranges=authority["peer_ranges"],
                )
            except (KeyError, TypeError, ValueError, OSError):
                return False

        if request.command_id == NPM_ANGULAR_LOCKFILE_NORMALIZE_RENDERER.command_id:
            try:
                binding = session.scalar(
                    select(StageWorkspaceBindingModel).where(
                        StageWorkspaceBindingModel.run_id == request.run_id,
                        StageWorkspaceBindingModel.stage_id == request.stage_id,
                        StageWorkspaceBindingModel.active.is_(True),
                    )
                )
                if binding is None:
                    return False
                patch = installed_dependency_version(
                    Path(binding.workspace_path).resolve(strict=True), "@angular/core"
                )
                return (
                    request.template_id == NPM_ANGULAR_LOCKFILE_NORMALIZE_RENDERER.template_id
                    and request.template_version == 2
                    and request.executable == "npm"
                    and tuple(request.arguments)
                    == NPM_ANGULAR_LOCKFILE_NORMALIZE_RENDERER.render_arguments(
                        {"target_angular_patch": patch}
                    )
                )
            except (KeyError, TypeError, ValueError, OSError):
                return False

        try:
            if request.command_id == NPM_DEPENDENCY_UNINSTALL_RENDERER.command_id:
                return (
                    request.template_id == NPM_DEPENDENCY_UNINSTALL_RENDERER.template_id
                    and request.template_version == 1
                    and request.executable == "npm"
                    and tuple(request.arguments)
                    == NPM_DEPENDENCY_UNINSTALL_RENDERER.render_arguments(
                        {"package": blocking_package}
                    )
                )
            if request.command_id in {
                NPM_DEPENDENCY_INSTALL_RENDERER.command_id,
                NPM_RUNTIME_DEPENDENCY_INSTALL_RENDERER.command_id,
            }:
                try:
                    binding = session.scalar(
                        select(StageWorkspaceBindingModel).where(
                            StageWorkspaceBindingModel.run_id == request.run_id,
                            StageWorkspaceBindingModel.stage_id == request.stage_id,
                            StageWorkspaceBindingModel.active.is_(True),
                        )
                    )
                    if binding is None:
                        return False
                    bundle = compatible_reinstall_bundle(
                        blocking_package, target_major, Path(binding.workspace_path)
                    )
                    approved_arguments = {
                        (
                            NPM_RUNTIME_DEPENDENCY_INSTALL_RENDERER
                            if compatible_reinstall_section(member.package) == "dependencies"
                            else NPM_DEPENDENCY_INSTALL_RENDERER
                        ).render_arguments(
                            {
                                "package": member.package,
                                "target_version": member.exact_version,
                            }
                        )
                        for member in bundle.members
                    }
                except (KeyError, TypeError, ValueError, OSError):
                    return False
                return (
                    request.template_id
                    == (
                        NPM_RUNTIME_DEPENDENCY_INSTALL_RENDERER.template_id
                        if request.command_id == NPM_RUNTIME_DEPENDENCY_INSTALL_RENDERER.command_id
                        else NPM_DEPENDENCY_INSTALL_RENDERER.template_id
                    )
                    and request.template_version == 1
                    and request.executable == "npm"
                    and tuple(request.arguments) in approved_arguments
                )
            if request.command_id == ANGULAR_UPDATE_V3_RENDERER.command_id:
                if (
                    angular_ref is None
                    or angular_ref.get("template_id") != ANGULAR_UPDATE_V3_RENDERER.template_id
                    or angular_ref.get("template_version") != 3
                ):
                    return False
                expected = ANGULAR_UPDATE_V3_RENDERER.render_arguments(
                    angular_ref.get("parameter_bindings") or {}
                )
                return (
                    request.template_id == ANGULAR_UPDATE_V3_RENDERER.template_id
                    and request.template_version == 3
                    and request.executable == "npx"
                    and tuple(request.arguments) == expected
                )
        except (TypeError, ValueError):
            return False
        return False
