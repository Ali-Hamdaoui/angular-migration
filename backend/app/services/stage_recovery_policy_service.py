"""Pure, generic safety policy for stage recovery decisions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RecoveryFailureClass(str, Enum):
    ENVIRONMENT_TRANSIENT = "ENVIRONMENT_TRANSIENT"
    ENVIRONMENT_PERMANENT = "ENVIRONMENT_PERMANENT"
    DEPENDENCY_INCOMPATIBLE = "DEPENDENCY_INCOMPATIBLE"
    TARGET_COHORT_INCOMPLETE = "TARGET_COHORT_INCOMPLETE"
    LOCK_RESOLUTION_FAILED = "LOCK_RESOLUTION_FAILED"
    STALE_WORKSPACE_BINDING = "STALE_WORKSPACE_BINDING"
    STALE_GATE_BINDING = "STALE_GATE_BINDING"
    COMMAND_INTERRUPTED = "COMMAND_INTERRUPTED"
    COMMAND_AUTHORITY_MISMATCH = "COMMAND_AUTHORITY_MISMATCH"
    SOURCE_REGRESSION = "SOURCE_REGRESSION"
    STAGE_PLAN_AUTHORITY_STALE = "STAGE_PLAN_AUTHORITY_STALE"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


class RecoveryAction(str, Enum):
    RETRY_COMMAND = "RETRY_COMMAND"
    RECOVER_STAGE = "RECOVER_STAGE"
    REEXECUTE_FROM_G07 = "REEXECUTE_FROM_G07"
    RECREATE_GATE = "RECREATE_GATE"
    REQUEST_REPAIR = "REQUEST_REPAIR"
    ESCALATE_UNKNOWN = "ESCALATE_UNKNOWN"
    DENY = "DENY"


@dataclass(frozen=True)
class StageRecoveryPolicyContext:
    """Structured state used by the policy; message text is intentionally inert."""

    run_id: str = ""
    stage_id: str = ""
    stage_status: str = "blocked"
    failure_code: str | None = None
    failure_message: str | None = None
    failure_class: RecoveryFailureClass | str = RecoveryFailureClass.UNKNOWN_FAILURE
    evidence_refs: tuple[str, ...] = ()
    checkpoint_present: bool = False
    checkpoint_safe: bool = False
    workspace_authority_valid: bool = False
    active_command: bool = False
    active_gate: str | None = None
    gate_binding_stale: bool = False
    stage_output_invalid: bool = False
    introduced_by_migration: bool = False
    command_id: str | None = None
    plan_authority_stale: bool = False
    commands_executed: bool = False
    command_authority_mismatch: bool = False


@dataclass(frozen=True)
class StageRecoveryPolicyDecision:
    allowed: bool
    action: RecoveryAction
    reason_code: str
    evidence_refs: tuple[str, ...] = ()


class UnknownFailureRecommendation(BaseModel):
    """Bounded LLM analysis output; it is never an approval or command."""

    model_config = ConfigDict(extra="forbid")

    failure_class: str = Field(min_length=1, max_length=64)
    probable_root_cause: str = Field(min_length=1, max_length=1000)
    proposed_owner: Literal["environment", "dependency", "source", "factory", "unknown"]
    recommended_action: str = Field(min_length=1, max_length=128)
    evidence_used: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)


class StageRecoveryPolicyService:
    """Select a sanctioned recovery transition without executing it.

    LLM analysis is permitted only after this deterministic policy returns
    ``ESCALATE_UNKNOWN``. It cannot approve recovery, alter compatibility,
    override gates, or decide checkpoint safety.
    """

    _RECOVERABLE_STATES = frozenset({"blocked", "cancelled", "waiting_gate"})

    def decide(self, context: StageRecoveryPolicyContext) -> StageRecoveryPolicyDecision:
        refs = tuple(context.evidence_refs)
        if context.stage_status not in self._RECOVERABLE_STATES:
            return self._deny("RECOVERY_STAGE_STATE_UNSAFE", refs)
        if not context.checkpoint_present or not context.checkpoint_safe:
            return self._deny("RECOVERY_CHECKPOINT_UNSAFE", refs)
        if not context.workspace_authority_valid:
            return self._deny("RECOVERY_WORKSPACE_AUTHORITY_STALE", refs)
        if context.active_command:
            return self._deny("RECOVERY_COMMAND_ACTIVE", refs)

        failure_class = self._normalize_class(context.failure_class)
        if failure_class is RecoveryFailureClass.STAGE_PLAN_AUTHORITY_STALE:
            if not context.plan_authority_stale:
                return self._deny("STAGE_PLAN_AUTHORITY_EVIDENCE_MISSING", refs)
            if context.commands_executed or context.stage_output_invalid:
                return self._deny("STAGE_PLAN_AUTHORITY_REFRESH_UNSAFE", refs)
            return self._allow(
                RecoveryAction.REEXECUTE_FROM_G07,
                "STAGE_PLAN_AUTHORITY_REFRESH_ALLOWED",
                refs,
            )
        if failure_class is RecoveryFailureClass.COMMAND_AUTHORITY_MISMATCH:
            if not context.command_authority_mismatch:
                return self._deny("COMMAND_AUTHORITY_EVIDENCE_MISSING", refs)
            if context.commands_executed or context.stage_output_invalid:
                return self._deny("COMMAND_AUTHORITY_REFRESH_UNSAFE", refs)
            return self._allow(
                RecoveryAction.REEXECUTE_FROM_G07,
                "COMMAND_AUTHORITY_REFRESH_ALLOWED",
                refs,
            )
        if failure_class is RecoveryFailureClass.STALE_GATE_BINDING:
            if not context.active_gate or not context.gate_binding_stale:
                return self._deny("STALE_GATE_EVIDENCE_MISSING", refs)
            return self._allow(RecoveryAction.RECREATE_GATE, "STALE_GATE_RECREATE_ALLOWED", refs)
        if failure_class is RecoveryFailureClass.UNKNOWN_FAILURE:
            return StageRecoveryPolicyDecision(
                allowed=False,
                action=RecoveryAction.ESCALATE_UNKNOWN,
                reason_code="UNKNOWN_FAILURE_REVIEW_REQUIRED",
                evidence_refs=refs,
            )
        if failure_class is RecoveryFailureClass.ENVIRONMENT_PERMANENT:
            return self._deny("ENVIRONMENT_PERMANENT_REQUIRES_OPERATOR", refs)
        if failure_class in {
            RecoveryFailureClass.ENVIRONMENT_TRANSIENT,
            RecoveryFailureClass.COMMAND_INTERRUPTED,
        }:
            action = (
                RecoveryAction.REEXECUTE_FROM_G07
                if context.stage_status == "cancelled"
                else RecoveryAction.RETRY_COMMAND
                if context.command_id
                else RecoveryAction.RECOVER_STAGE
            )
            return self._allow(action, "TRANSIENT_COMMAND_RECOVERY_ALLOWED", refs)
        if failure_class in {
            RecoveryFailureClass.DEPENDENCY_INCOMPATIBLE,
            RecoveryFailureClass.TARGET_COHORT_INCOMPLETE,
            RecoveryFailureClass.LOCK_RESOLUTION_FAILED,
        }:
            action = (
                RecoveryAction.REEXECUTE_FROM_G07
                if context.stage_output_invalid and context.introduced_by_migration
                else RecoveryAction.REQUEST_REPAIR
            )
            return self._allow(action, "DEPENDENCY_RECOVERY_GOVERNED", refs)
        if failure_class is RecoveryFailureClass.STALE_WORKSPACE_BINDING:
            return self._allow(RecoveryAction.RECOVER_STAGE, "WORKSPACE_RECOVERY_GOVERNED", refs)
        if failure_class is RecoveryFailureClass.SOURCE_REGRESSION:
            action = (
                RecoveryAction.REEXECUTE_FROM_G07
                if context.stage_output_invalid and context.introduced_by_migration
                else RecoveryAction.REQUEST_REPAIR
            )
            return self._allow(action, "SOURCE_REGRESSION_GOVERNED", refs)
        return StageRecoveryPolicyDecision(
            allowed=False,
            action=RecoveryAction.ESCALATE_UNKNOWN,
            reason_code="UNKNOWN_FAILURE_REVIEW_REQUIRED",
            evidence_refs=refs,
        )

    def decide_llm_recommendation(
        self,
        context: StageRecoveryPolicyContext,
        recommendation: UnknownFailureRecommendation,
    ) -> StageRecoveryPolicyDecision:
        """Validate an unknown-failure analysis, then re-run deterministic policy."""
        failure_class = self._normalize_class(recommendation.failure_class)
        if (
            failure_class is RecoveryFailureClass.UNKNOWN_FAILURE
            or recommendation.recommended_action
            not in {action.value for action in RecoveryAction}
        ):
            return StageRecoveryPolicyDecision(
                False,
                RecoveryAction.ESCALATE_UNKNOWN,
                "LLM_RECOMMENDATION_UNSUPPORTED",
                tuple(context.evidence_refs),
            )
        return self.decide(replace(context, failure_class=failure_class))

    @staticmethod
    def _normalize_class(value: RecoveryFailureClass | str) -> RecoveryFailureClass:
        try:
            return value if isinstance(value, RecoveryFailureClass) else RecoveryFailureClass(str(value))
        except ValueError:
            return RecoveryFailureClass.UNKNOWN_FAILURE

    @staticmethod
    def _allow(action: RecoveryAction, reason_code: str, refs: tuple[str, ...]):
        return StageRecoveryPolicyDecision(True, action, reason_code, refs)

    @staticmethod
    def _deny(reason_code: str, refs: tuple[str, ...]):
        return StageRecoveryPolicyDecision(False, RecoveryAction.DENY, reason_code, refs)
