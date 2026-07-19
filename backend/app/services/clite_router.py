"""Application service for C-Lite failure routing — deterministic failure-to-route classification.

The ``CLiteRouter`` wraps a ``CLiteRuleRegistry`` with default C-Lite rules
and exposes convenience methods for remediation checklists, retry policy
queries, and safe-rerun authorization checks.
"""

from __future__ import annotations

from typing import Any

from app.domain.failure import FailureDiagnostic, FailureRoute
from app.domain.route import (
    CLiteRule,
    CLiteRuleRegistry,
    FailureRouteDecision,
    RemediationAction,
    RemediationChecklist,
)

# ---------------------------------------------------------------------------
# Default C-Lite rules (hardcoded; policy-driven in production)
# ---------------------------------------------------------------------------

_DEFAULT_RULES: list[CLiteRule] = [
    CLiteRule(
        route=FailureRoute.ENVIRONMENT_OR_USER_ACTION,
        confidence=0.9,
        pattern=r"Permission denied|EACCES",
        actions=[
            "check file permissions",
            "verify user ownership",
            "review environment variables",
        ],
        risk="medium",
    ),
    CLiteRule(
        route=FailureRoute.DEPENDENCY_REPAIR,
        confidence=0.95,
        pattern=r"npm ERR!|MODULE_NOT_FOUND",
        actions=[
            "audit package.json / package-lock.json",
            "run npm install",
            "clear npm cache and retry",
        ],
        risk="low",
    ),
    CLiteRule(
        route=FailureRoute.CODE_OR_CONFIG_REPAIR,
        confidence=0.85,
        pattern=r"TS\d+[:\s]",
        actions=[
            "review TypeScript compiler diagnostics",
            "check tsconfig.json configuration",
            "fix type errors in source files",
        ],
        risk="medium",
    ),
    CLiteRule(
        route=FailureRoute.RETRYABLE_EXTERNAL_FAILURE,
        confidence=0.9,
        pattern=r"Connection refused|ECONNREFUSED|timeout",
        actions=[
            "check network connectivity",
            "verify external service availability",
            "schedule automatic retry with backoff",
        ],
        risk="low",
    ),
    CLiteRule(
        route=FailureRoute.CODE_OR_CONFIG_REPAIR,
        confidence=0.8,
        pattern=r"Error:|Angular CLI",
        actions=[
            "inspect Angular CLI error details",
            "review angular.json configuration",
            "check Angular version compatibility",
        ],
        risk="medium",
    ),
    CLiteRule(
        route=FailureRoute.CODE_OR_CONFIG_REPAIR,
        confidence=0.8,
        pattern=r"Template parse error",
        actions=[
            "inspect template error details",
            "review component template syntax",
            "check imported module declarations",
        ],
        risk="medium",
    ),
]


def _build_default_registry() -> CLiteRuleRegistry:
    registry = CLiteRuleRegistry()
    for rule in _DEFAULT_RULES:
        registry.add_rule(rule)
    return registry


# ---------------------------------------------------------------------------
# CLiteRouter
# ---------------------------------------------------------------------------


class CLiteRouter:
    """Application service for C-Lite failure routing.

    Wraps a ``CLiteRuleRegistry`` and provides high-level methods for
    route classification, remediation checklist construction, retry-policy
    introspection, and safe-rerun authorisation.
    """

    def __init__(self, rule_registry: CLiteRuleRegistry | None = None) -> None:
        self._registry = rule_registry or _build_default_registry()

    # -- Public API ---------------------------------------------------------

    def classify(
        self,
        failure_diagnostics: list[FailureDiagnostic],
        failure_id: str,
        policy_version: str = "c-lite-v1",
    ) -> FailureRouteDecision:
        """Classify failure diagnostics into a ``FailureRouteDecision``.

        Delegates to the underlying ``CLiteRuleRegistry.classify()``.
        """
        return self._registry.classify(failure_diagnostics, failure_id, policy_version)

    def build_remediation_checklist(
        self, route_decision: FailureRouteDecision
    ) -> RemediationChecklist:
        """Build a ``RemediationChecklist`` from a route decision.

        Each action in the decision is mapped to a ``RemediationAction``.
        The action type is inferred from the route:
          - ``ENVIRONMENT_OR_USER_ACTION`` → ``type="environment"``
          - ``RETRYABLE_EXTERNAL_FAILURE`` → ``type="retry"``
          - Everything else → ``type="manual"``
        """
        route_type_map: dict[FailureRoute, str] = {
            FailureRoute.ENVIRONMENT_OR_USER_ACTION: "environment",
            FailureRoute.RETRYABLE_EXTERNAL_FAILURE: "retry",
        }
        default_type = "manual"

        actions = [
            RemediationAction(description=action, type=route_type_map.get(route_decision.route, default_type))
            for action in route_decision.actions
        ]

        return RemediationChecklist(
            actions=actions,
            environment_info={
                "route": route_decision.route.value,
                "policy_version": route_decision.policy_version,
                "risk": route_decision.risk,
            },
        )

    @property
    def retry_policy(self) -> dict[str, Any]:
        """Return the retry-policy configuration as a dictionary.

        Returns:
            A dict with ``max_retries`` (int) and
            ``semantic_attempt_exclusions`` (list[str]).
        """
        return {
            "max_retries": 3,
            "semantic_attempt_exclusions": [
                "dependency_install",
                "network_operation",
            ],
        }

    @property
    def max_retries(self) -> int:
        """The maximum number of automatic retry attempts (default 3)."""
        return 3

    @property
    def semantic_attempt_exclusions(self) -> list[str]:
        """Operation types excluded from automatic retry semantic attempts."""
        return ["dependency_install", "network_operation"]

    @staticmethod
    def safe_rerun_authorization(run_state: dict[str, Any] | None = None) -> bool:
        """Determine whether the run can be safely re-executed.

        A run is safe to rerun if:
          - No ``run_state`` is supplied (conservative: authorise).
          - The run is in a terminal failure or holds state
            (``FAILED``, ``DIAGNOSTIC_HOLD``, ``CANCELLED``).
          - The run is in a non-terminal but restartable state
            (``RECOVERY_RUNNING``).

        Returns ``True`` when the run is authorised for safe rerun,
        ``False`` otherwise.
        """
        if run_state is None:
            return True

        status = run_state.get("status", "")
        safe_states = {"FAILED", "DIAGNOSTIC_HOLD", "CANCELLED", "RECOVERY_RUNNING"}
        return status in safe_states
