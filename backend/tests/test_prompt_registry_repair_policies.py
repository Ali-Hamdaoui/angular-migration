"""Focused coverage for repair and prompt-explanation policies in the production registry."""

import pytest

from app.llm_gateway import (
    AzureGatewayError,
    LlmFailureCode,
    LlmTaskType,
    PromptDefinition,
    PromptRegistry,
    production_prompt_policy_gaps,
)


def _defaults_without(name: str) -> PromptRegistry:
    return PromptRegistry(
        [
            prompt
            for prompt in PromptRegistry.defaults()._prompts.values()
            if prompt.name != name
        ]
    )


def test_defaults_resolve_repair_proposer_policy() -> None:
    prompt = PromptRegistry.defaults().get(
        'repair_proposer_v1', LlmTaskType.REPAIR_DIAGNOSIS
    )
    assert prompt.version == 'prompt-repair-proposer-v1'
    assert 'Repair Proposer' in prompt.system_policy
    assert prompt.allowed_tasks == frozenset({LlmTaskType.REPAIR_DIAGNOSIS})


def test_defaults_resolve_repair_reviewer_policy() -> None:
    prompt = PromptRegistry.defaults().get(
        'repair_reviewer_v1', LlmTaskType.REPAIR_REVIEW
    )
    assert prompt.version == 'prompt-repair-reviewer-v1'
    assert 'Repair Reviewer' in prompt.system_policy
    assert prompt.allowed_tasks == frozenset({LlmTaskType.REPAIR_REVIEW})


def test_defaults_resolve_transformer_prompt_explanation_policy() -> None:
    prompt = PromptRegistry.defaults().get(
        'transformer-prompt-explanation-v1', LlmTaskType.TRANSFORMATION_EXPLANATION
    )
    assert prompt.version == 'prompt-transformer-explanation-v1'
    assert 'Explain only the supplied Angular CLI prompt' in prompt.system_policy
    assert prompt.allowed_tasks == frozenset({LlmTaskType.TRANSFORMATION_EXPLANATION})


def test_repair_and_explanation_policies_reject_wrong_task_with_authorization() -> None:
    registry = PromptRegistry.defaults()
    with pytest.raises(AzureGatewayError) as denied:
        registry.get('repair_proposer_v1', LlmTaskType.REPAIR_REVIEW)
    assert denied.value.code == LlmFailureCode.AUTHORIZATION
    with pytest.raises(AzureGatewayError) as denied:
        registry.get('repair_reviewer_v1', LlmTaskType.REPAIR_DIAGNOSIS)
    assert denied.value.code == LlmFailureCode.AUTHORIZATION
    with pytest.raises(AzureGatewayError) as denied:
        registry.get(
            'transformer-prompt-explanation-v1', LlmTaskType.ASSISTANT_RESPONSE
        )
    assert denied.value.code == LlmFailureCode.AUTHORIZATION


def test_production_policy_coverage_is_complete_for_defaults() -> None:
    assert production_prompt_policy_gaps() == []
    assert production_prompt_policy_gaps(PromptRegistry.defaults()) == []


def test_gap_is_reported_when_mandatory_policy_is_missing() -> None:
    gaps = production_prompt_policy_gaps(_defaults_without('repair_proposer_v1'))
    assert 'repair_proposer_v1' in gaps
    assert 'repair_reviewer_v1' not in gaps
    assert 'llm_smoke_v1' not in gaps


def test_gap_is_reported_when_policy_allowed_tasks_exclude_tuple_task() -> None:
    registry = _defaults_without('repair_proposer_v1')
    registry.register(
        PromptDefinition(
            name='repair_proposer_v1',
            version='prompt-repair-proposer-v1',
            system_policy='You are the Repair Proposer.',
            allowed_tasks=frozenset({LlmTaskType.REPAIR_REVIEW}),
        )
    )
    gaps = production_prompt_policy_gaps(registry)
    assert 'repair_proposer_v1' in gaps


def test_unregistered_prompt_raises_instead_of_silent_fallback() -> None:
    with pytest.raises(AzureGatewayError) as denied:
        PromptRegistry.defaults().get(
            'repair_proposer_v2', LlmTaskType.REPAIR_DIAGNOSIS
        )
    assert denied.value.code == LlmFailureCode.AUTHORIZATION
