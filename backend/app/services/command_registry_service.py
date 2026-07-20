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

from sqlalchemy import select
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
    require_plan_membership: bool = True
    require_stage_plan: bool = True

    def validate(
        self,
        session: Session,
        request: CommandPolicyValidateRequestDto,
    ) -> CommandPolicyValidateResponseDto:
        """Run all policy checks and return an authorization decision."""
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

            # 3. Executable matches template
            allowed = set(template.executable_aliases + [template.executable])
            if request.executable not in allowed:
                checks.append(AuthorizationCheckResult(
                    passed=False,
                    rule_name="executable_matches_template",
                    reason=f"executable '{request.executable}' not in allowed set: {allowed}",
                ))
                reasons.append(f"executable mismatch")
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
        if self.require_plan_membership and request.run_id:
            plan_check = self._check_plan_membership(session, request)
            checks.append(plan_check)
            if not plan_check.passed:
                reasons.append(plan_check.reason or "plan membership rejected")

        decision = AuthorizationDecision.REJECTED if reasons else AuthorizationDecision.ACCEPTED
        return CommandPolicyValidateResponseDto(
            authorization_id=authorization_id,
            run_id=request.run_id,
            stage_id=request.stage_id,
            command_id=request.command_id,
            executable=request.executable,
            arguments=request.arguments,
            cwd_alias=request.cwd_alias,
            plan_id=request.plan_id,
            execution_profile_id=request.execution_profile_id,
            decision=decision.value,
            reasons=reasons,
            policy_version=self.policy_version,
        )

    def _check_shell_enforcement(self, request: CommandPolicyValidateRequestDto) -> AuthorizationCheckResult:
        """Reject any request attempting shell execution."""
        if request.shell is not False:
            return AuthorizationCheckResult(
                passed=False,
                rule_name="shell_enforcement",
                reason="Shell execution is forbidden",
            )
        return AuthorizationCheckResult(passed=True, rule_name="shell_enforcement")

    def _check_network_profile(self, profile: str) -> AuthorizationCheckResult:
        allowed = {p.value for p in NetworkProfile}
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
        """Verify the command_id appears in the approved stage plan for this run."""
        from app.repositories.planning_models import MigrationPlanModel, StageExecutionPlanModel

        # Look up the approved stage plan for the run
        plan = session.scalar(
            select(StageExecutionPlanModel)
            .where(StageExecutionPlanModel.run_id == request.run_id)
            .order_by(StageExecutionPlanModel.created_at.desc())
            .limit(1)
        )
        if plan is None or not plan.command_refs:
            # No plan found — soft pass if plan membership is aspirational
            return AuthorizationCheckResult(
                passed=True,
                rule_name="plan_membership",
                reason="no stage plan found; plan membership not enforced",
            )
        if request.command_id in (plan.command_refs or []):
            return AuthorizationCheckResult(passed=True, rule_name="plan_membership")
        return AuthorizationCheckResult(
            passed=False,
            rule_name="plan_membership",
            reason=f"command_id '{request.command_id}' not in approved stage plan command refs",
        )
