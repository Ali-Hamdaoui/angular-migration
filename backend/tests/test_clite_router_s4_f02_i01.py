"""Tests for S4-F02-I01 (AMFA-230): Backend domain for C-Lite failure routing.

Covers:
- Happy path: diagnostics match each route → correct FailureRouteDecision
- Invalid input: empty diagnostics → UNKNOWN_DIAGNOSIS
- Remediation checklist: environment route → checklist with environment actions
- Retry policy: max_retries returned correctly
- Policy version tracking: version included in decision
- Decision checksum: deterministic from route + actions
"""

from __future__ import annotations

import hashlib
import json

import pytest

from app.domain.failure import FailureDiagnostic, DiagnosticParserType, FailureRoute
from app.domain.route import (
    CLiteRule,
    CLiteRuleRegistry,
    FailureRouteDecision,
    RemediationAction,
    RemediationChecklist,
)
from app.services.clite_router import CLiteRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_diagnostic(message: str, code: str | None = None) -> FailureDiagnostic:
    return FailureDiagnostic(
        message=message,
        code=code,
        severity="error",
        parser_type=DiagnosticParserType.GENERIC,
        parser_confidence=1.0,
    )


def _make_diagnostics(*messages: str) -> list[FailureDiagnostic]:
    return [_make_diagnostic(m) for m in messages]


def _expected_checksum(route: FailureRoute, actions: list[str]) -> str:
    raw = json.dumps(
        [route.value] + actions,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# Happy path — diagnostics match each route
# ---------------------------------------------------------------------------


class TestHappyPathRouteClassification:
    """Every default rule matches its intended diagnostic pattern."""

    ROUTE_EXAMPLES: list[tuple[str, FailureRoute, str]] = [
        # (diagnostic_message, expected_route, action_hint)
        ("Permission denied while accessing /var/log", FailureRoute.ENVIRONMENT_OR_USER_ACTION, "check file permissions"),
        ("EACCES: permission denied, open /root/.npm", FailureRoute.ENVIRONMENT_OR_USER_ACTION, "check file permissions"),
        ("npm ERR! Failed to install dependency", FailureRoute.DEPENDENCY_REPAIR, "audit package.json"),
        ("Error: Cannot find module 'express' MODULE_NOT_FOUND", FailureRoute.DEPENDENCY_REPAIR, "audit package.json"),
        ("src/app.ts(15,5): error TS2322: Type mismatch", FailureRoute.CODE_OR_CONFIG_REPAIR, "review TypeScript"),
        ("TS2345: Argument of type 'X' is not assignable to 'Y'", FailureRoute.CODE_OR_CONFIG_REPAIR, "review TypeScript"),
        ("Connection refused to registry.npmjs.org:443", FailureRoute.RETRYABLE_EXTERNAL_FAILURE, "check network"),
        ("connect ECONNREFUSED 127.0.0.1:3000", FailureRoute.RETRYABLE_EXTERNAL_FAILURE, "check network"),
        ("Request timed out after 30000ms", FailureRoute.RETRYABLE_EXTERNAL_FAILURE, "check network"),
        ("Error: The Angular CLI requires a higher version of TypeScript", FailureRoute.CODE_OR_CONFIG_REPAIR, "inspect Angular CLI"),
        ("Angular CLI: An unhandled exception occurred", FailureRoute.CODE_OR_CONFIG_REPAIR, "inspect Angular CLI"),
        ("Template parse errors found in component.html", FailureRoute.CODE_OR_CONFIG_REPAIR, "inspect template error"),
    ]

    @pytest.mark.parametrize("message,expected_route,action_hint", ROUTE_EXAMPLES)
    def test_route_classification(self, message: str, expected_route: FailureRoute, action_hint: str) -> None:
        router = CLiteRouter()
        decision = router.classify(
            failure_diagnostics=_make_diagnostics(message),
            failure_id="fail-test-001",
            policy_version="c-lite-v1",
        )
        assert decision.route == expected_route, f"Expected {expected_route} for '{message}', got {decision.route}"
        assert decision.failure_id == "fail-test-001"
        assert decision.policy_version == "c-lite-v1"
        assert decision.decision_checksum.startswith("sha256:")
        assert len(decision.decision_checksum) == 71  # "sha256:" + 64 hex chars
        assert any(action_hint in a for a in decision.actions), (
            f"Expected action hint '{action_hint}' in {decision.actions}"
        )


# ---------------------------------------------------------------------------
# Invalid input — empty diagnostics
# ---------------------------------------------------------------------------


class TestEmptyDiagnostics:
    """Empty diagnostics must always yield UNKNOWN_DIAGNOSIS."""

    def test_empty_diagnostics_returns_unknown(self) -> None:
        router = CLiteRouter()
        decision = router.classify(
            failure_diagnostics=[],
            failure_id="fail-empty",
            policy_version="c-lite-v1",
        )
        assert decision.route == FailureRoute.UNKNOWN_DIAGNOSIS
        assert decision.actions == ["review manually"]
        assert decision.risk == "medium"

    def test_diagnostics_with_no_match_returns_unknown(self) -> None:
        router = CLiteRouter()
        decision = router.classify(
            failure_diagnostics=_make_diagnostics("some random info line"),
            failure_id="fail-nomatch",
            policy_version="c-lite-v1",
        )
        assert decision.route == FailureRoute.UNKNOWN_DIAGNOSIS
        assert decision.actions == ["review manually"]


# ---------------------------------------------------------------------------
# Remediation checklist
# ---------------------------------------------------------------------------


class TestRemediationChecklist:
    """Remediation checklists reflect the route type correctly."""

    def test_environment_route_yields_environment_actions(self) -> None:
        router = CLiteRouter()
        decision = router.classify(
            failure_diagnostics=_make_diagnostics("EACCES: permission denied"),
            failure_id="fail-env-001",
            policy_version="c-lite-v1",
        )
        assert decision.route == FailureRoute.ENVIRONMENT_OR_USER_ACTION
        checklist = router.build_remediation_checklist(decision)
        assert isinstance(checklist, RemediationChecklist)
        assert len(checklist.actions) > 0
        for action in checklist.actions:
            assert isinstance(action, RemediationAction)
            assert action.type == "environment"
        assert "route" in checklist.environment_info
        assert checklist.environment_info["route"] == "ENVIRONMENT_OR_USER_ACTION"
        assert checklist.environment_info["policy_version"] == "c-lite-v1"

    def test_code_repair_route_yields_manual_actions(self) -> None:
        router = CLiteRouter()
        decision = router.classify(
            failure_diagnostics=_make_diagnostics("TS2321: Type error in component"),
            failure_id="fail-code-001",
            policy_version="c-lite-v1",
        )
        assert decision.route == FailureRoute.CODE_OR_CONFIG_REPAIR
        checklist = router.build_remediation_checklist(decision)
        assert len(checklist.actions) > 0
        for action in checklist.actions:
            assert action.type == "manual"

    def test_retry_external_route_yields_retry_actions(self) -> None:
        router = CLiteRouter()
        decision = router.classify(
            failure_diagnostics=_make_diagnostics("Connection refused to api.example.com"),
            failure_id="fail-retry-001",
            policy_version="c-lite-v1",
        )
        assert decision.route == FailureRoute.RETRYABLE_EXTERNAL_FAILURE
        checklist = router.build_remediation_checklist(decision)
        assert len(checklist.actions) > 0
        for action in checklist.actions:
            assert action.type == "retry"

    def test_unknown_route_yields_manual_actions(self) -> None:
        router = CLiteRouter()
        decision = router.classify(
            failure_diagnostics=_make_diagnostics("unrecognised compiler warning xyz"),
            failure_id="fail-unk-001",
            policy_version="c-lite-v1",
        )
        assert decision.route == FailureRoute.UNKNOWN_DIAGNOSIS
        checklist = router.build_remediation_checklist(decision)
        assert len(checklist.actions) > 0
        for action in checklist.actions:
            assert action.type == "manual"


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    """Retry-policy properties match the contract."""

    def test_max_retries_default(self) -> None:
        router = CLiteRouter()
        assert router.max_retries == 3

    def test_max_retries_property(self) -> None:
        router = CLiteRouter()
        assert router.retry_policy["max_retries"] == 3

    def test_semantic_attempt_exclusions_present(self) -> None:
        router = CLiteRouter()
        exclusions = router.semantic_attempt_exclusions
        assert isinstance(exclusions, list)
        assert "dependency_install" in exclusions
        assert "network_operation" in exclusions

    def test_semantic_attempt_exclusions_in_policy_dict(self) -> None:
        router = CLiteRouter()
        policy = router.retry_policy
        assert "semantic_attempt_exclusions" in policy
        assert policy["semantic_attempt_exclusions"] == router.semantic_attempt_exclusions


# ---------------------------------------------------------------------------
# Policy version tracking
# ---------------------------------------------------------------------------


class TestPolicyVersion:
    """Policy version is carried through into the route decision."""

    def test_custom_policy_version(self) -> None:
        router = CLiteRouter()
        decision = router.classify(
            failure_diagnostics=_make_diagnostics("npm ERR! failure"),
            failure_id="fail-pol-001",
            policy_version="c-lite-v2-beta",
        )
        assert decision.policy_version == "c-lite-v2-beta"

    def test_default_policy_version(self) -> None:
        router = CLiteRouter()
        decision = router.classify(
            failure_diagnostics=_make_diagnostics("npm ERR! failure"),
            failure_id="fail-pol-002",
        )
        assert decision.policy_version == "c-lite-v1"

    def test_version_included_in_remediation_environment_info(self) -> None:
        router = CLiteRouter()
        decision = router.classify(
            failure_diagnostics=_make_diagnostics("EACCES broken"),
            failure_id="fail-pol-003",
            policy_version="c-lite-v3",
        )
        checklist = router.build_remediation_checklist(decision)
        assert checklist.environment_info["policy_version"] == "c-lite-v3"


# ---------------------------------------------------------------------------
# Decision checksum — deterministic
# ---------------------------------------------------------------------------


class TestDecisionChecksum:
    """The decision_checksum is a deterministic SHA-256 of route + actions."""

    def test_checksum_format(self) -> None:
        router = CLiteRouter()
        decision = router.classify(
            failure_diagnostics=_make_diagnostics("npm ERR! fail"),
            failure_id="fail-csum-001",
            policy_version="c-lite-v1",
        )
        assert decision.decision_checksum.startswith("sha256:")
        assert len(decision.decision_checksum) == 71  # "sha256:" (7) + 64 hex chars

    def test_checksum_deterministic_same_input(self) -> None:
        router = CLiteRouter()
        d1 = router.classify(
            failure_diagnostics=_make_diagnostics("npm ERR! fail"),
            failure_id="fail-csum-002",
            policy_version="c-lite-v1",
        )
        d2 = router.classify(
            failure_diagnostics=_make_diagnostics("npm ERR! fail"),
            failure_id="fail-csum-002",
            policy_version="c-lite-v1",
        )
        assert d1.decision_checksum == d2.decision_checksum

    def test_checksum_different_route_different_hash(self) -> None:
        router = CLiteRouter()
        d_perm = router.classify(
            failure_diagnostics=_make_diagnostics("EACCES: denied"),
            failure_id="fail-csum-003",
            policy_version="c-lite-v1",
        )
        d_npm = router.classify(
            failure_diagnostics=_make_diagnostics("npm ERR! fail"),
            failure_id="fail-csum-004",
            policy_version="c-lite-v1",
        )
        assert d_perm.route != d_npm.route
        assert d_perm.decision_checksum != d_npm.decision_checksum

    def test_checksum_deterministic_via_static_contract(self) -> None:
        """Verify checksum matches what we compute externally."""
        route = FailureRoute.DEPENDENCY_REPAIR
        actions = [
            "audit package.json / package-lock.json",
            "run npm install",
            "clear npm cache and retry",
        ]
        expected = _expected_checksum(route, actions)

        router = CLiteRouter()
        decision = router.classify(
            failure_diagnostics=_make_diagnostics("npm ERR! code ELIFECYCLE"),
            failure_id="fail-csum-005",
            policy_version="c-lite-v1",
        )
        assert decision.route == route
        assert decision.decision_checksum == expected

    def test_unknown_route_checksum(self) -> None:
        expected = _expected_checksum(FailureRoute.UNKNOWN_DIAGNOSIS, ["review manually"])
        router = CLiteRouter()
        decision = router.classify(
            failure_diagnostics=[],
            failure_id="fail-csum-empty",
            policy_version="c-lite-v1",
        )
        assert decision.decision_checksum == expected


# ---------------------------------------------------------------------------
# CLiteRuleRegistry — lower-level behaviour
# ---------------------------------------------------------------------------


class TestCLiteRuleRegistry:
    """Direct registry unit tests (not through the router)."""

    def test_rule_precedence_first_match_wins(self) -> None:
        """When multiple rules could match, the first registered rule wins."""
        registry = CLiteRuleRegistry(
            rules=[
                CLiteRule(
                    route=FailureRoute.ENVIRONMENT_OR_USER_ACTION,
                    confidence=0.9,
                    pattern=r"error",
                    actions=["env action"],
                    risk="medium",
                ),
                CLiteRule(
                    route=FailureRoute.CODE_OR_CONFIG_REPAIR,
                    confidence=0.9,
                    pattern=r"error",
                    actions=["code action"],
                    risk="low",
                ),
            ]
        )
        decision = registry.classify(
            diagnostics=_make_diagnostics("some error occurred"),
            failure_id="fail-ord",
            policy_version="c-lite-v1",
        )
        assert decision.route == FailureRoute.ENVIRONMENT_OR_USER_ACTION
        assert decision.actions == ["env action"]

    def test_no_match_fallback(self) -> None:
        registry = CLiteRuleRegistry()
        decision = registry.classify(
            diagnostics=_make_diagnostics("clean build output"),
            failure_id="fail-fallback",
            policy_version="c-lite-v1",
        )
        assert decision.route == FailureRoute.UNKNOWN_DIAGNOSIS
        assert decision.actions == ["review manually"]

    def test_add_rule_appends(self) -> None:
        registry = CLiteRuleRegistry()
        assert len(registry.rules) == 0
        registry.add_rule(
            CLiteRule(
                route=FailureRoute.DEPENDENCY_REPAIR,
                confidence=1.0,
                pattern=r"test",
            )
        )
        assert len(registry.rules) == 1

    def test_rules_property_returns_copy(self) -> None:
        registry = CLiteRuleRegistry(rules=[CLiteRule(route=FailureRoute.DEPENDENCY_REPAIR, confidence=1.0, pattern=r"test")])
        rules_view = registry.rules
        rules_view.clear()
        # Original should be unchanged
        assert len(registry.rules) == 1


# ---------------------------------------------------------------------------
# Safe rerun authorization
# ---------------------------------------------------------------------------


class TestSafeRerunAuthorization:
    """Safe-rerun authorisation logic."""

    def test_none_state_authorized(self) -> None:
        assert CLiteRouter.safe_rerun_authorization() is True

    def test_failed_state_authorized(self) -> None:
        assert CLiteRouter.safe_rerun_authorization({"status": "FAILED"}) is True

    def test_diagnostic_hold_authorized(self) -> None:
        assert CLiteRouter.safe_rerun_authorization({"status": "DIAGNOSTIC_HOLD"}) is True

    def test_cancelled_authorized(self) -> None:
        assert CLiteRouter.safe_rerun_authorization({"status": "CANCELLED"}) is True

    def test_recovery_running_authorized(self) -> None:
        assert CLiteRouter.safe_rerun_authorization({"status": "RECOVERY_RUNNING"}) is True

    def test_running_state_not_authorized(self) -> None:
        assert CLiteRouter.safe_rerun_authorization({"status": "RUNNING"}) is False

    def test_completed_state_not_authorized(self) -> None:
        assert CLiteRouter.safe_rerun_authorization({"status": "COMPLETED"}) is False


# ---------------------------------------------------------------------------
# RemediationAction / RemediationChecklist model validation
# ---------------------------------------------------------------------------


class TestRemediationModels:
    """Unit validation of the remediation models."""

    def test_remediation_action_valid_types(self) -> None:
        for t in ("manual", "environment", "retry"):
            action = RemediationAction(description=f"do {t} step", type=t)
            assert action.type == t

    def test_remediation_action_invalid_type(self) -> None:
        with pytest.raises(ValueError):
            RemediationAction(description="bad type", type="automatic")

    def test_checklist_defaults(self) -> None:
        checklist = RemediationChecklist()
        assert checklist.actions == []
        assert checklist.environment_info == {}

    def test_checklist_with_actions(self) -> None:
        actions = [
            RemediationAction(description="Step 1", type="manual"),
            RemediationAction(description="Step 2", type="environment"),
        ]
        checklist = RemediationChecklist(
            actions=actions,
            environment_info={"os": "linux"},
        )
        assert len(checklist.actions) == 2
        assert checklist.environment_info == {"os": "linux"}
