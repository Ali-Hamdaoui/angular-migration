"""Backend-owned mock LLM Gateway for Sprint 0."""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.artifact_store.local_store import LocalFilesystemArtifactStore, StoredArtifact
from app.core.config import Settings, get_settings
from app.domain.contracts import ArtifactType
from app.llm_gateway.contracts import (
    LlmBudgetAction,
    LlmBudgetDecision,
    LlmCostSummary,
    LlmRequest,
    LlmResponse,
    LlmUsageRecord,
)
from app.llm_gateway.redaction import redact_prompt_text


class MockLlmGateway:
    """Mock gateway that never calls Azure OpenAI or exposes credentials."""

    def __init__(
        self,
        settings: Settings | None = None,
        artifact_store: LocalFilesystemArtifactStore | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._artifact_store = artifact_store or LocalFilesystemArtifactStore(self._settings.artifact_root)

    def complete(self, request: LlmRequest, prior_usage: list[LlmUsageRecord] | None = None) -> LlmResponse:
        """Create a deterministic schema-shaped mock response and redacted audit artifact."""
        redacted_prompt = self._redacted_prompt(request)
        input_tokens = _estimate_tokens(redacted_prompt.redacted_text)
        output_tokens = min(request.max_output_tokens, max(32, math.ceil(input_tokens * 0.2)))
        usage = build_usage_record(
            run_id=request.run_id,
            stage_id=request.stage_id,
            agent_kind=request.agent_kind,
            task_type=request.task_type,
            model_deployment_alias=self._model_alias,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_price_per_million=self._input_price,
            output_price_per_million=self._output_price,
        )
        budget = decide_budget(
            request.run_id,
            [*(prior_usage or []), usage],
            token_budget=self._settings.llm_token_budget,
            cost_budget_usd=self._settings.llm_cost_budget_usd,
        )
        artifact = self._write_redacted_interaction_artifact(request, redacted_prompt.redacted_text, usage, budget)
        return LlmResponse(
            response_id=f"llm-response-{uuid4().hex[:12]}",
            request_id=request.request_id,
            run_id=request.run_id,
            stage_id=request.stage_id,
            agent_kind=request.agent_kind,
            task_type=request.task_type,
            model_deployment_alias=self._model_alias,
            status="mocked",
            summary=f"Mock {request.task_type.value} response generated through backend LLM Gateway.",
            structured_output={
                "schema": request.response_schema,
                "trusted_policy_applied": True,
                "untrusted_context_count": sum(1 for segment in request.context if segment.untrusted),
                "budget_action": budget.action.value,
                "execution_authorized": False,
                "approval_authorized": False,
            },
            usage=usage,
            redaction=redacted_prompt,
            artifact_refs=[artifact.ref.artifact_id],
        )

    @property
    def _model_alias(self) -> str:
        return self._settings.azure_openai_deployment or "gpt-5-mini"

    @property
    def _input_price(self) -> float:
        return self._settings.llm_input_price_per_million_tokens or 0.25

    @property
    def _output_price(self) -> float:
        return self._settings.llm_output_price_per_million_tokens or 2.0

    def _redacted_prompt(self, request: LlmRequest):
        prompt = {
            "system_policy": request.system_policy,
            "context": [
                {
                    "segment_id": segment.segment_id,
                    "label": segment.label,
                    "untrusted": segment.untrusted,
                    "artifact_ref": segment.artifact_ref,
                    "content": segment.content,
                }
                for segment in request.context
            ],
        }
        return redact_prompt_text(json.dumps(prompt, sort_keys=True))

    def _write_redacted_interaction_artifact(
        self,
        request: LlmRequest,
        redacted_prompt: str,
        usage: LlmUsageRecord,
        budget: LlmBudgetDecision,
    ) -> StoredArtifact:
        content = json.dumps(
            {
                "request_id": request.request_id,
                "run_id": request.run_id,
                "stage_id": request.stage_id,
                "agent_kind": request.agent_kind.value,
                "task_type": request.task_type.value,
                "model_deployment_alias": usage.model_deployment_alias,
                "redacted_prompt": redacted_prompt,
                "usage": usage.model_dump(mode="json"),
                "budget_decision": budget.model_dump(mode="json"),
                "raw_prompt_stored": False,
                "hidden_reasoning_stored": False,
            },
            indent=2,
            sort_keys=True,
        )
        return self._artifact_store.write_text_artifact(
            request.run_id,
            "04_workflow_state/llm_interaction_log_redacted.json",
            content,
            ArtifactType.JSON,
            stage_id=request.stage_id,
            created_by="llm_gateway_mock",
            content_type="application/json",
            policy_version="migration-policy-v1",
        )

    def write_usage_summary_artifact(self, run_id: str, records: list[LlmUsageRecord]) -> StoredArtifact:
        """Persist a redacted Markdown usage and cost summary artifact."""
        summary = summarize_usage(run_id, records)
        content = "\n".join(
            [
                "# LLM Usage and Cost Summary",
                "",
                f"Total input tokens: {summary.input_tokens}",
                f"Total output tokens: {summary.output_tokens}",
                f"Total tokens: {summary.total_tokens}",
                f"Total input cost USD: {summary.input_cost_usd:.8f}",
                f"Total output cost USD: {summary.output_cost_usd:.8f}",
                f"Total cost USD: {summary.total_cost_usd:.8f}",
                f"Pricing source: {summary.pricing_source}",
                f"Retries: {summary.retry_count}",
                f"Failed calls: {summary.failed_call_count}",
                "",
            ]
        )
        return self._artifact_store.write_text_artifact(
            run_id,
            "final_report/llm_usage_and_cost_summary.md",
            content,
            ArtifactType.MARKDOWN,
            created_by="llm_gateway_mock",
            content_type="text/markdown",
            policy_version="migration-policy-v1",
        )


def build_usage_record(
    *,
    run_id: str,
    stage_id: str | None,
    agent_kind,
    task_type,
    model_deployment_alias: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int | None = None,
    input_price_per_million: float,
    output_price_per_million: float,
    retry_count: int = 0,
    failed_call_count: int = 0,
    created_at: datetime | None = None,
) -> LlmUsageRecord:
    input_cost = input_tokens / 1_000_000 * input_price_per_million
    output_cost = output_tokens / 1_000_000 * output_price_per_million
    return LlmUsageRecord(
        usage_id=f"llm-usage-{uuid4().hex[:12]}",
        run_id=run_id,
        stage_id=stage_id,
        agent_kind=agent_kind,
        task_type=task_type,
        model_deployment_alias=model_deployment_alias,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens if total_tokens is None else total_tokens,
        input_price_per_million=input_price_per_million,
        output_price_per_million=output_price_per_million,
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=input_cost + output_cost,
        retry_count=retry_count,
        failed_call_count=failed_call_count,
        created_at=created_at or datetime.now(UTC),
    )


def summarize_usage(run_id: str, records: list[LlmUsageRecord]) -> LlmCostSummary:
    scoped = [record for record in records if record.run_id == run_id]
    return LlmCostSummary(
        run_id=run_id,
        input_tokens=sum(record.input_tokens for record in scoped),
        output_tokens=sum(record.output_tokens for record in scoped),
        total_tokens=sum(record.total_tokens for record in scoped),
        input_cost_usd=sum(record.input_cost_usd for record in scoped),
        output_cost_usd=sum(record.output_cost_usd for record in scoped),
        total_cost_usd=sum(record.total_cost_usd for record in scoped),
        calls_by_agent=dict(Counter(record.agent_kind.value for record in scoped)),
        calls_by_stage=dict(Counter(record.stage_id or "global" for record in scoped)),
        calls_by_task_type=dict(Counter(record.task_type.value for record in scoped)),
        retry_count=sum(record.retry_count for record in scoped),
        failed_call_count=sum(record.failed_call_count for record in scoped),
    )


def decide_budget(
    run_id: str,
    records: list[LlmUsageRecord],
    *,
    token_budget: int,
    cost_budget_usd: float,
) -> LlmBudgetDecision:
    summary = summarize_usage(run_id, records)
    if token_budget and summary.total_tokens > token_budget:
        return LlmBudgetDecision(
            run_id=run_id,
            action=LlmBudgetAction.BLOCK_NEW_LLM_CALLS,
            reason="token budget exceeded",
            projected_total_tokens=summary.total_tokens,
            projected_total_cost_usd=summary.total_cost_usd,
            token_budget=token_budget,
            cost_budget_usd=cost_budget_usd,
        )
    if summary.failed_call_count:
        return LlmBudgetDecision(
            run_id=run_id,
            action=LlmBudgetAction.USE_DETERMINISTIC_FALLBACK,
            reason="failed calls require deterministic fallback",
            projected_total_tokens=summary.total_tokens,
            projected_total_cost_usd=summary.total_cost_usd,
            token_budget=token_budget,
            cost_budget_usd=cost_budget_usd,
        )
    if cost_budget_usd and summary.total_cost_usd > cost_budget_usd:
        return LlmBudgetDecision(
            run_id=run_id,
            action=LlmBudgetAction.DIAGNOSTIC_HOLD,
            reason="cost budget exceeded",
            projected_total_tokens=summary.total_tokens,
            projected_total_cost_usd=summary.total_cost_usd,
            token_budget=token_budget,
            cost_budget_usd=cost_budget_usd,
        )
    if token_budget and summary.total_tokens >= token_budget * 0.8:
        action = LlmBudgetAction.WARN
        reason = "token budget nearing limit"
    elif cost_budget_usd and summary.total_cost_usd >= cost_budget_usd * 0.8:
        action = LlmBudgetAction.WARN
        reason = "cost budget nearing limit"
    else:
        action = LlmBudgetAction.CONTINUE
        reason = "within configured budget"
    return LlmBudgetDecision(
        run_id=run_id,
        action=action,
        reason=reason,
        projected_total_tokens=summary.total_tokens,
        projected_total_cost_usd=summary.total_cost_usd,
        token_budget=token_budget,
        cost_budget_usd=cost_budget_usd,
    )


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))
