"""Deterministic rules for S1-F14 baseline qualification and G03.

This module is deliberately persistence- and execution-free.  Application
services provide the immutable evidence already produced by S1-F10 through
S1-F13 and may persist the resulting package or request a state transition.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


POLICY_VERSION = "baseline-qualification-v1"
PACKAGE_VERSION = "g03-v1"


class BaselineQualificationStatus(str, Enum):
    QUALIFIED = "qualified"
    QUALIFIED_WITH_KNOWN_FAILURES = "qualified_with_known_failures"
    REPRODUCIBILITY_DEGRADED = "reproducibility_degraded"
    BLOCKED_BY_ENVIRONMENT = "blocked_by_environment"
    BLOCKED_BY_PROJECT = "blocked_by_project"


class KnownFailurePolicy(str, Enum):
    STRICT_CLEAN = "strict_clean"
    QUALIFIED_KNOWN_FAILURES = "qualified_known_failures"


class G03Decision(str, Enum):
    APPROVED = "approved"
    MODIFICATION_REQUESTED = "modification_requested"
    REJECTED = "rejected"


@dataclass(frozen=True)
class BaselineEvidence:
    """The normalized evidence required to evaluate the baseline boundary."""

    runtime: Mapping[str, Any]
    install: Mapping[str, Any]
    validations: tuple[Mapping[str, Any], ...]
    parity: Mapping[str, Any]
    source_integrity: Mapping[str, Any]
    evidence_artifacts: tuple[Mapping[str, Any], ...]
    sandbox_fingerprint: str
    execution_profile_checksum: str
    state_version: int
    optional_failures: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class BaselineQualification:
    status: BaselineQualificationStatus
    policy: KnownFailurePolicy
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    known_failures: tuple[Mapping[str, Any], ...]
    evidence_confidence: Mapping[str, str]
    package_checksum: str
    policy_version: str = POLICY_VERSION


@dataclass(frozen=True)
class G03ApprovalPackage:
    run_id: str
    gate_id: str
    gate_version: str
    state_version: int
    actor: str
    policy: KnownFailurePolicy
    policy_version: str
    qualification_status: BaselineQualificationStatus
    evidence_set_checksum: str
    sandbox_fingerprint: str
    execution_profile_checksum: str
    package_checksum: str
    expires_at: str | None = None


@dataclass(frozen=True)
class G03DecisionResult:
    decision: G03Decision
    package_checksum: str
    stale: bool = False
    reason: str | None = None


class BaselinePolicyService:
    """Apply the explicit policy boundary for baseline failures."""

    def evaluate(
        self,
        evidence: BaselineEvidence,
        *,
        policy: KnownFailurePolicy = KnownFailurePolicy.STRICT_CLEAN,
        company_policy_allows_known_failures: bool = False,
    ) -> BaselineQualification:
        blockers: list[str] = []
        warnings: list[str] = []
        failures = tuple(self._known_failures(evidence))
        optional = tuple(dict(item) for item in evidence.optional_failures if isinstance(item, Mapping))
        optional_keys = {_stable_key(item) for item in optional}
        required_failures = tuple(item for item in failures if _stable_key(item) not in optional_keys)

        if not evidence.sandbox_fingerprint:
            blockers.append("BASELINE_SANDBOX_FINGERPRINT_REQUIRED")
        if not evidence.execution_profile_checksum:
            blockers.append("EXECUTION_PROFILE_CHECKSUM_REQUIRED")
        if not self._verified(evidence.source_integrity):
            blockers.append("SOURCE_INTEGRITY_NOT_VERIFIED")

        install_status = self._status(evidence.install)
        if install_status in {"failed", "blocked", "timed_out", "cancelled"}:
            blockers.append("BASELINE_INSTALL_FAILED")
        elif install_status not in {"passed", "succeeded", "success"}:
            blockers.append("BASELINE_INSTALL_NOT_PROVEN")

        validation_statuses = [self._status(item) for item in evidence.validations]
        if not evidence.validations:
            blockers.append("BASELINE_VALIDATION_EVIDENCE_REQUIRED")
        if any(status in {"failed", "blocked", "timed_out", "cancelled"} for status in validation_statuses):
            required_build_failed = any(
                self._kind(item) == "build" and self._status(item) in {"failed", "blocked", "timed_out", "cancelled"}
                for item in evidence.validations
            )
            required_test_failed = any(
                self._kind(item) == "test" and self._status(item) in {"failed", "blocked", "timed_out", "cancelled", "unsupported"}
                for item in evidence.validations
            )
            if required_build_failed:
                blockers.append("BASELINE_BUILD_FAILED")
            if required_test_failed:
                blockers.append("BASELINE_REQUIRED_TEST_NOT_PROVEN")
            else:
                if not required_build_failed:
                    warnings.append("BASELINE_VALIDATION_FAILURES_PRESENT")
        if any(status in {"not_configured", "manual_validation_required", "deferred_company_tool_required"} for status in validation_statuses):
            warnings.append("BASELINE_VALIDATION_NOT_MACHINE_PROVEN")

        if failures and not required_failures:
            warnings.append("BASELINE_HAS_PRE_EXISTING_OPTIONAL_DIAGNOSTICS")
        elif required_failures and policy is KnownFailurePolicy.STRICT_CLEAN:
            blockers.append("KNOWN_BASELINE_FAILURES_REQUIRE_POLICY")
        elif required_failures and policy is KnownFailurePolicy.QUALIFIED_KNOWN_FAILURES:
            if not company_policy_allows_known_failures:
                blockers.append("KNOWN_FAILURE_POLICY_NOT_ALLOWED")
            elif any(not item.get("fingerprint") for item in required_failures):
                blockers.append("KNOWN_FAILURE_FINGERPRINT_REQUIRED")
            else:
                warnings.append("BASELINE_HAS_APPROVED_KNOWN_FAILURES")

        if blockers:
            status = self._blocked_status(blockers, evidence)
        elif failures:
            status = BaselineQualificationStatus.QUALIFIED_WITH_KNOWN_FAILURES
        else:
            status = BaselineQualificationStatus.QUALIFIED

        payload = {
            "status": status.value,
            "policy": policy.value,
            "policy_version": POLICY_VERSION,
            "blockers": sorted(blockers),
            "warnings": sorted(warnings),
            "known_failures": list(failures),
            "evidence_confidence": dict(evidence.parity.get("confidence", {})),
            "sandbox_fingerprint": evidence.sandbox_fingerprint,
            "execution_profile_checksum": evidence.execution_profile_checksum,
            "state_version": evidence.state_version,
        }
        return BaselineQualification(
            status=status,
            policy=policy,
            blockers=tuple(sorted(blockers)),
            warnings=tuple(sorted(warnings)),
            known_failures=failures,
            evidence_confidence=dict(evidence.parity.get("confidence", {})),
            package_checksum=_checksum(payload),
        )

    @staticmethod
    def _known_failures(evidence: BaselineEvidence) -> list[Mapping[str, Any]]:
        failures = evidence.parity.get("failures", ())
        return [dict(item) for item in failures if isinstance(item, Mapping)]

    @staticmethod
    def _verified(integrity: Mapping[str, Any]) -> bool:
        return bool(integrity.get("verified", integrity.get("source_read_only_verified", False)))

    @staticmethod
    def _status(value: Mapping[str, Any]) -> str:
        return str(value.get("status", "")).lower()

    @staticmethod
    def _kind(value: Mapping[str, Any]) -> str:
        return str(value.get("kind", value.get("target_kind", ""))).lower()

    @staticmethod
    def _blocked_status(blockers: list[str], evidence: BaselineEvidence) -> BaselineQualificationStatus:
        environment_markers = ("ENVIRONMENT", "RUNTIME", "REGISTRY", "NOT_PROVEN")
        if any(any(marker in blocker for marker in environment_markers) for blocker in blockers):
            return BaselineQualificationStatus.BLOCKED_BY_ENVIRONMENT
        return BaselineQualificationStatus.BLOCKED_BY_PROJECT


class G03ApprovalPackageBuilder:
    """Create a checksum-bound G03 package from a qualification result."""

    def build(
        self,
        *,
        run_id: str,
        actor: str,
        evidence: BaselineEvidence,
        qualification: BaselineQualification,
        gate_version: str = PACKAGE_VERSION,
        expires_at: str | None = None,
    ) -> G03ApprovalPackage:
        artifact_payload = sorted(
            ({"artifact_id": item.get("artifact_id"), "checksum": item.get("checksum")} for item in evidence.evidence_artifacts),
            key=lambda item: str(item["artifact_id"]),
        )
        evidence_checksum = _checksum(artifact_payload)
        unsigned = {
            "run_id": run_id,
            "gate_id": "G03",
            "gate_version": gate_version,
            "state_version": evidence.state_version,
            "actor": actor,
            "policy": qualification.policy.value,
            "policy_version": qualification.policy_version,
            "qualification_status": qualification.status.value,
            "evidence_set_checksum": evidence_checksum,
            "sandbox_fingerprint": evidence.sandbox_fingerprint,
            "execution_profile_checksum": evidence.execution_profile_checksum,
            "expires_at": expires_at,
        }
        return G03ApprovalPackage(**unsigned, package_checksum=_checksum(unsigned))


class G03ApprovalService:
    """Fail-closed approval rules for the G03 boundary."""

    def decide(
        self,
        package: G03ApprovalPackage,
        decision: G03Decision,
        *,
        current_state_version: int | None = None,
        current_sandbox_fingerprint: str | None = None,
        current_execution_profile_checksum: str | None = None,
    ) -> G03DecisionResult:
        stale = (
            current_state_version is not None and current_state_version != package.state_version
        ) or (
            current_sandbox_fingerprint is not None and current_sandbox_fingerprint != package.sandbox_fingerprint
        ) or (
            current_execution_profile_checksum is not None
            and current_execution_profile_checksum != package.execution_profile_checksum
        )
        if stale:
            return G03DecisionResult(decision=G03Decision.REJECTED, package_checksum=package.package_checksum, stale=True, reason="G03 evidence is stale")
        if decision is G03Decision.APPROVED and package.qualification_status not in {
            BaselineQualificationStatus.QUALIFIED,
            BaselineQualificationStatus.QUALIFIED_WITH_KNOWN_FAILURES,
        }:
            return G03DecisionResult(decision=G03Decision.REJECTED, package_checksum=package.package_checksum, reason="baseline qualification is blocked")
        return G03DecisionResult(decision=decision, package_checksum=package.package_checksum)


def _checksum(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _stable_key(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), default=str)
