"""Domain contracts for C-Lite failure routing — deterministic failure-to-route classification."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pydantic import Field

from app.domain.contracts import ContractModel
from app.domain.failure import FailureDiagnostic, FailureRoute


class CLiteRule(ContractModel):
    """A single C-Lite routing rule with a regex pattern to match against diagnostic messages.

    Attributes:
        route: The target FailureRoute to assign when this rule matches.
        confidence: Certainty of the match (0.0–1.0).
        pattern: A regex pattern tested against concatenated diagnostic messages.
        actions: Suggested remediation actions for this route.
        risk: Risk level string (e.g. \"low\", \"medium\", \"high\").
    """

    route: FailureRoute
    confidence: float = Field(ge=0.0, le=1.0)
    pattern: str = Field(min_length=1)
    actions: list[str] = Field(default_factory=list)
    risk: str = "low"


class FailureRouteDecision(ContractModel):
    """Immutable decision produced by the C-Lite classifier.

    Complies with the ``failure_route.schema.json`` contract.
    The ``decision_checksum`` is a deterministic sha256: over the
    route value and actions list produced by the matching rule.
    """

    failure_id: str = Field(min_length=1, max_length=128)
    route: FailureRoute
    policy_version: str = Field(min_length=1)
    decision_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    actions: list[str] = Field(default_factory=list)
    risk: str = "medium"


class RemediationAction(ContractModel):
    """A single actionable step to resolve a routed failure.

    Attributes:
        description: Human-readable instructions for the step.
        type: Category of action — manual, environment, or retry.
    """

    description: str = Field(min_length=1, max_length=2000)
    type: str = Field(pattern=r"^(manual|environment|retry)$")


class RemediationChecklist(ContractModel):
    """Ordered list of remediation actions scoped to a route decision.

    Attributes:
        actions: Ordered remediation steps to perform.
        environment_info: Arbitrary key-value metadata about the
            environment state at the time of the decision.
    """

    actions: list[RemediationAction] = Field(default_factory=list)
    environment_info: dict[str, Any] = Field(default_factory=dict)


class CLiteRuleRegistry:
    """A collection of C-Lite rules that classifies failure diagnostics into a route.

    Rules are evaluated in order; the first rule whose pattern matches any
    diagnostic message wins.  If no rule matches, ``UNKNOWN_DIAGNOSIS`` is returned.
    """

    def __init__(self, rules: list[CLiteRule] | None = None) -> None:
        self._rules: list[CLiteRule] = rules or []

    @property
    def rules(self) -> list[CLiteRule]:
        """Return the list of registered rules (read-only view)."""
        return list(self._rules)

    def add_rule(self, rule: CLiteRule) -> None:
        """Append a single rule to the registry."""
        self._rules.append(rule)

    def classify(
        self,
        diagnostics: list[FailureDiagnostic],
        failure_id: str,
        policy_version: str,
    ) -> FailureRouteDecision:
        """Classify diagnostics into a ``FailureRouteDecision``.

        Extracts message text from each diagnostic and tests it against
        every rule's ``pattern`` in registration order.  Returns the
        first match, or ``UNKNOWN_DIAGNOSIS`` when nothing matches.

        The ``decision_checksum`` is a deterministic SHA-256 digest
        computed from the chosen route value and actions.
        """
        messages = " ".join(d.message for d in diagnostics).strip()

        for rule in self._rules:
            if re.search(rule.pattern, messages, re.IGNORECASE):
                return FailureRouteDecision(
                    failure_id=failure_id,
                    route=rule.route,
                    policy_version=policy_version,
                    decision_checksum=self._compute_checksum(
                        route=rule.route, actions=rule.actions
                    ),
                    actions=list(rule.actions),
                    risk=rule.risk,
                )

        # Fallback — no rule matched
        return FailureRouteDecision(
            failure_id=failure_id,
            route=FailureRoute.UNKNOWN_DIAGNOSIS,
            policy_version=policy_version,
            decision_checksum=self._compute_checksum(
                route=FailureRoute.UNKNOWN_DIAGNOSIS,
                actions=["review manually"],
            ),
            actions=["review manually"],
            risk="medium",
        )

    @staticmethod
    def _compute_checksum(route: FailureRoute, actions: list[str]) -> str:
        """Return a deterministic ``sha256:`` checksum from route + actions."""
        raw = json.dumps(
            [route.value] + actions,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return "sha256:" + hashlib.sha256(raw).hexdigest()
