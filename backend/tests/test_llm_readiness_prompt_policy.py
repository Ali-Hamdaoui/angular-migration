"""Focused readiness tests for local LLM prompt policy coverage."""

from pydantic import SecretStr

from app.core.config import Settings
from app.llm_gateway import PromptRegistry
from app.services.llm_evidence_application_service import LlmEvidenceApplicationService


def _azure_settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        artifact_root=tmp_path / "runs",
        workspace_root=tmp_path / "workspaces",
        snapshot_root=tmp_path / "snapshots",
        delivery_root=tmp_path / "delivery",
        sandbox_root=tmp_path / "sandboxes",
        llm_enabled=True,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_deployment="gpt-5-mini-private",
        azure_openai_api_version="2025-04-01-preview",
        azure_openai_api_key=SecretStr("super-secret-api-key"),
    )


def _registry_without(name: str) -> PromptRegistry:
    return PromptRegistry(
        [
            prompt
            for prompt in PromptRegistry.defaults()._prompts.values()
            if prompt.name != name
        ]
    )


def test_readiness_is_configured_unverified_with_full_production_registry(tmp_path) -> None:
    result = LlmEvidenceApplicationService(settings=_azure_settings(tmp_path)).readiness()
    assert result.status == "configured_unverified"
    assert result.error_code == "LLM_SMOKE_NOT_VERIFIED"
    assert result.llm_enabled is True
    assert result.endpoint_configured is True
    assert result.deployment_configured is True
    assert result.authentication_configured is True


def test_readiness_reports_prompt_policy_missing_when_mandatory_policy_is_absent(tmp_path) -> None:
    result = LlmEvidenceApplicationService(settings=_azure_settings(tmp_path)).readiness(
        registry=_registry_without("repair_proposer_v1")
    )
    assert result.status == "configuration_incomplete"
    assert result.error_code == "LLM_PROMPT_POLICY_MISSING"
    assert result.llm_enabled is True
    assert result.deployment_configured is True


def test_readiness_is_disabled_when_llm_disabled(tmp_path) -> None:
    settings = _azure_settings(tmp_path).model_copy(update={"llm_enabled": False})
    result = LlmEvidenceApplicationService(settings=settings).readiness()
    assert result.status == "disabled"
    assert result.error_code is None


def test_readiness_is_configuration_incomplete_when_env_missing(tmp_path) -> None:
    settings = _azure_settings(tmp_path).model_copy(
        update={"azure_openai_endpoint": None, "azure_openai_api_key": None}
    )
    result = LlmEvidenceApplicationService(settings=settings).readiness()
    assert result.status == "configuration_incomplete"
    assert result.error_code == "LLM_CONFIGURATION_INCOMPLETE"
    assert result.endpoint_configured is False
    assert result.authentication_configured is False
