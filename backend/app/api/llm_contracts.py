from typing import Any, Literal

from pydantic import Field

from app.domain.contracts import ContractModel


class LlmReadinessResponse(ContractModel):
    status: Literal['disabled', 'configuration_incomplete', 'configured_unverified', 'ready', 'degraded', 'blocked']
    provider: str = 'azure_openai'
    deployment_configured: bool
    model_capability: str
    error_code: str | None = None
    llm_enabled: bool = False
    endpoint_configured: bool = False
    authentication_configured: bool = False
    schema_capability_configured: bool = False
    last_smoke_check_status: str | None = None
    last_checked_at: str | None = None


class LlmSmokeRequest(ContractModel):
    run_id: str = Field(min_length=1)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    correlation_id: str | None = Field(default=None, max_length=128)


class LlmInvocationResponse(ContractModel):
    invocation_id: str
    run_id: str
    status: Literal['in_progress', 'completed', 'failed', 'blocked']
    role: str
    task_type: str
    provider: str
    deployment_alias: str
    model_capability: str = 'responses_json_schema'
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_checksums: dict[str, str] = Field(default_factory=dict)
    artifact_links: dict[str, str] = Field(default_factory=dict)
    correlation_id: str | None = None
    prompt_version: str | None = None
    schema_version: str | None = None
    pricing_version: str | None = None
    stage: str | None = None
    input_hashes: list[str] = Field(default_factory=list)
    redacted_summary: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    retries: int = 0
    latency_ms: int | None = None
    failure_code: str | None = None
    provider_http_status: int | None = None
    provider_error_code: str | None = None
    sanitized_provider_message: str | None = None
    provider_request_id: str | None = None
    failure_stage: str | None = None
    failure_subtype: str | None = None
    retryable: bool = False
    response_received: bool | None = None
    response_content_type: str | None = None
    response_bytes: int | None = None
    response_sha256: str | None = None
    response_kind: str | None = None
    transport_started: bool | None = None
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False
    structured_output: dict[str, Any] = Field(default_factory=dict)


class LlmActivityResponse(ContractModel):
    run_id: str
    invocations: list[LlmInvocationResponse] = Field(default_factory=list)


class LlmUsageResponse(ContractModel):
    run_id: str
    invocation_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    pricing_versions: list[str] = Field(default_factory=list)
    records: list[dict[str, Any]] = Field(default_factory=list)
