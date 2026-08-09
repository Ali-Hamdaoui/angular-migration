from app.services.planning_input_resolver import PlanningInputResolutionError
from app.services.planning_job_service import classify_planning_failure
from app.services.workspace_configuration_reader import WorkspaceConfigurationError


def test_deterministic_workspace_failure_is_terminal_and_not_retryable():
    error = WorkspaceConfigurationError("WORKSPACE_JSON_SYNTAX_INVALID", "angular.json", "angular.json")

    disposition = classify_planning_failure(error)

    assert disposition.code == "WORKSPACE_JSON_SYNTAX_INVALID"
    assert disposition.retryable is False
    assert disposition.terminal is True


def test_resolver_domain_failure_is_terminal_and_preserves_code():
    error = PlanningInputResolutionError("PLANNING_BUILD_TARGET_MISSING", "No supported build target is configured.")

    disposition = classify_planning_failure(error)

    assert disposition.code == "PLANNING_BUILD_TARGET_MISSING"
    assert disposition.retryable is False
    assert disposition.terminal is True


def test_only_allowlisted_transient_failures_are_retryable():
    error = PlanningInputResolutionError("PLANNING_DATABASE_TRANSIENT", "Database temporarily unavailable")

    disposition = classify_planning_failure(error)

    assert disposition.code == "PLANNING_DATABASE_TRANSIENT"
    assert disposition.retryable is True
    assert disposition.terminal is False


def test_unknown_failures_do_not_default_to_retry_everything():
    disposition = classify_planning_failure(RuntimeError("unexpected"))

    assert disposition.retryable is False
    assert disposition.terminal is True
