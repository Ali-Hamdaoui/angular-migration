"""Structured contracts for the Sprint 0 mock LLM Gateway."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.contracts import AgentKind


class LlmGatewayModel(BaseModel):
    """Base behavior for immutable gateway contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class LlmTaskType(str, Enum):
    ANALYSIS_SUMMARY = "analysis_summary"
    ANALYSIS_REVIEW = "analysis_review"
    PLAN_RATIONALE = "plan_rationale"
    PLANNING_REVIEW = "planning_review"
    TRANSFORMATION_EXPLANATION = "transformation_explanation"
    VALIDATION_CLASSIFICATION = "validation_classification"
    REPAIR_DIAGNOSIS = "repair_diagnosis"
    REPAIR_REVIEW = "repair_review"
    REPORT_SUMMARY = "report_summary"
    ASSISTANT_RESPONSE = "assistant_response"
    SMOKE_CHECK = "smoke_check"


class LlmRole(str, Enum):
    ASSISTANT = 'assistant'
    PHASE_PROPOSER = 'phase_proposer'
    PHASE_REVIEWER = 'phase_reviewer'
    REPAIR_PROPOSER = 'repair_proposer'
    REPAIR_REVIEWER = 'repair_reviewer'
    REPORT_NARRATOR = 'report_narrator'
    FALLBACK = 'fallback'


class LlmBudgetAction(str, Enum):
    CONTINUE = "continue"
    WARN = "warn"
    BLOCK_NEW_LLM_CALLS = "block_new_llm_calls"
    USE_DETERMINISTIC_FALLBACK = "use_deterministic_fallback"
    DIAGNOSTIC_HOLD = "diagnostic_hold"
    REQUIRE_APPROVAL = "require_approval"


class LlmContextSegment(LlmGatewayModel):
    segment_id: str
    label: str
    content: str
    untrusted: bool = False
    artifact_ref: str | None = None


class LlmRequest(LlmGatewayModel):
    request_id: str
    run_id: str
    stage_id: str | None = None
    agent_kind: AgentKind
    task_type: LlmTaskType
    system_policy: str = Field(min_length=1)
    context: list[LlmContextSegment] = Field(default_factory=list)
    response_schema: str = Field(min_length=1)
    max_output_tokens: int = Field(default=512, gt=0)
    role: LlmRole = LlmRole.ASSISTANT
    prompt_name: str | None = None

    @model_validator(mode="after")
    def require_untrusted_labels_for_repository_context(self) -> "LlmRequest":
        for segment in self.context:
            label = segment.label.lower()
            if any(marker in label for marker in ("repository", "source", "log", "diff", "compiler")) and not segment.untrusted:
                raise ValueError("repository, source, log, diff, and compiler context must be labeled untrusted")
        return self


class PromptRedactionResult(LlmGatewayModel):
    redacted_text: str
    redaction_count: int
    redaction_types: list[str] = Field(default_factory=list)


class LlmUsageRecord(LlmGatewayModel):
    usage_id: str
    run_id: str
    stage_id: str | None = None
    agent_kind: AgentKind
    task_type: LlmTaskType
    model_deployment_alias: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    input_price_per_million: float = Field(ge=0)
    output_price_per_million: float = Field(ge=0)
    input_cost_usd: float = Field(ge=0)
    output_cost_usd: float = Field(ge=0)
    total_cost_usd: float = Field(ge=0)
    retry_count: int = Field(default=0, ge=0)
    failed_call_count: int = Field(default=0, ge=0)
    created_at: datetime


class LlmResponse(LlmGatewayModel):
    response_id: str
    request_id: str
    run_id: str
    stage_id: str | None = None
    agent_kind: AgentKind
    task_type: LlmTaskType
    model_deployment_alias: str
    status: str
    summary: str
    structured_output: dict[str, object] = Field(default_factory=dict)
    usage: LlmUsageRecord
    redaction: PromptRedactionResult
    artifact_refs: list[str] = Field(default_factory=list)
    role: LlmRole = LlmRole.ASSISTANT
    prompt_version: str | None = None
    schema_version: str | None = None
    pricing_version: str | None = None
    failure_code: str | None = None


class LlmCostSummary(LlmGatewayModel):
    run_id: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    input_cost_usd: float = Field(ge=0)
    output_cost_usd: float = Field(ge=0)
    total_cost_usd: float = Field(ge=0)
    calls_by_agent: dict[str, int] = Field(default_factory=dict)
    calls_by_stage: dict[str, int] = Field(default_factory=dict)
    calls_by_task_type: dict[str, int] = Field(default_factory=dict)
    retry_count: int = Field(ge=0)
    failed_call_count: int = Field(ge=0)
    pricing_source: str = "mvp_configured_fixed_price"


class LlmBudgetDecision(LlmGatewayModel):
    run_id: str
    action: LlmBudgetAction
    reason: str
    projected_total_tokens: int = Field(ge=0)
    projected_total_cost_usd: float = Field(ge=0)
    token_budget: int = Field(ge=0)
    cost_budget_usd: float = Field(ge=0)
