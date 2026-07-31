"""Backend-owned LLM Gateway mock boundary."""

from app.llm_gateway.contracts import (
    LlmBudgetAction,
    LlmBudgetDecision,
    LlmContextSegment,
    LlmCostSummary,
    LlmRequest,
    LlmResponse,
    LlmRole,
    LlmTaskType,
    LlmUsageRecord,
    PromptRedactionResult,
)
from app.llm_gateway.mock_gateway import MockLlmGateway, build_usage_record, decide_budget, summarize_usage
from app.llm_gateway.redaction import redact_prompt_text
from app.llm_gateway.azure_gateway import AzureGatewayError, AzureOpenAILLMGateway, DeploymentConfiguration, LlmFailureCode, ModelCapability, ModelCapabilityRegistry, PRODUCTION_LLM_POLICY_TUPLES, PromptDefinition, PromptRegistry, PromptSchemaRegistry, RoleRouter, StructuredOutputValidationError, production_prompt_policy_gaps

__all__ = [
    'AzureGatewayError',
    'AzureOpenAILLMGateway',
    'DeploymentConfiguration',
    'LlmFailureCode',
    'LlmRole',
    'ModelCapability',
    'ModelCapabilityRegistry',
    'PRODUCTION_LLM_POLICY_TUPLES',
    'PromptDefinition',
    'PromptRegistry',
    'PromptSchemaRegistry',
    'RoleRouter',
    'StructuredOutputValidationError',
    "LlmBudgetAction",
    "LlmBudgetDecision",
    "LlmContextSegment",
    "LlmCostSummary",
    "LlmRequest",
    "LlmResponse",
    "LlmTaskType",
    "LlmUsageRecord",
    "MockLlmGateway",
    "PromptRedactionResult",
    "build_usage_record",
    "decide_budget",
    "production_prompt_policy_gaps",
    "redact_prompt_text",
    "summarize_usage",
]
