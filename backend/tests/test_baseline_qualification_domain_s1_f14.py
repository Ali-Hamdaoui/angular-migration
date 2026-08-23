from app.domain.baseline_qualification import (
    BaselineEvidence,
    BaselinePolicyService,
    BaselineQualificationStatus,
    G03ApprovalPackageBuilder,
    G03ApprovalService,
    G03Decision,
    KnownFailurePolicy,
)


def evidence(*, failures=(), install="passed", build="passed", source_verified=True):
    return BaselineEvidence(
        runtime={"status": "selected"},
        install={"status": install},
        validations=({"kind": "build", "status": build}, {"kind": "test", "status": "passed"}),
        parity={"failures": failures, "confidence": {"failures": "machine_proven"}},
        source_integrity={"verified": source_verified},
        evidence_artifacts=({"artifact_id": "artifact-1", "checksum": "sha256:artifact"},),
        sandbox_fingerprint="sha256:sandbox",
        execution_profile_checksum="sha256:profile",
        state_version=7,
    )


def test_clean_baseline_is_qualified_and_g03_can_be_approved():
    result = BaselinePolicyService().evaluate(evidence())
    package = G03ApprovalPackageBuilder().build(run_id="run-1", actor="operator", evidence=evidence(), qualification=result)

    assert result.status is BaselineQualificationStatus.QUALIFIED
    decision = G03ApprovalService().decide(package, G03Decision.APPROVED, current_state_version=7)
    assert decision.decision is G03Decision.APPROVED
    assert not decision.stale


def test_known_failure_requires_explicit_allowed_policy_and_never_looks_clean():
    failure = {"fingerprint": "sha256:failure", "kind": "test", "message": "known"}
    clean_policy = BaselinePolicyService().evaluate(evidence(failures=(failure,)))
    allowed = BaselinePolicyService().evaluate(
        evidence(failures=(failure,)),
        policy=KnownFailurePolicy.QUALIFIED_KNOWN_FAILURES,
        company_policy_allows_known_failures=True,
    )

    assert clean_policy.status is BaselineQualificationStatus.BLOCKED_BY_PROJECT
    assert allowed.status is BaselineQualificationStatus.QUALIFIED_WITH_KNOWN_FAILURES


def test_pre_existing_lint_debt_is_captured_without_blocking_g03():
    failure = {"fingerprint": "sha256:lint", "kind": "lint", "origin": "pre-existing", "message": "legacy"}
    current = evidence(failures=(failure,))
    current = current.__class__(**{**current.__dict__, "optional_failures": (failure,)})

    result = BaselinePolicyService().evaluate(current)

    assert result.status is BaselineQualificationStatus.QUALIFIED_WITH_KNOWN_FAILURES
    assert not result.blockers
    assert result.known_failures == (failure,)


def test_optional_lint_debt_does_not_hide_a_required_failure():
    lint = {"fingerprint": "sha256:lint", "kind": "lint", "origin": "pre-existing"}
    test = {"fingerprint": "sha256:test", "kind": "test", "origin": "pre-existing"}
    current = evidence(failures=(lint, test))
    current = current.__class__(**{**current.__dict__, "optional_failures": (lint,)})

    result = BaselinePolicyService().evaluate(current)

    assert result.status is BaselineQualificationStatus.BLOCKED_BY_PROJECT
    assert "KNOWN_BASELINE_FAILURES_REQUIRE_POLICY" in result.blockers


def test_failed_install_or_build_cannot_be_approved():
    result = BaselinePolicyService().evaluate(evidence(install="failed", build="passed"))
    package = G03ApprovalPackageBuilder().build(run_id="run-1", actor="operator", evidence=evidence(install="failed", build="passed"), qualification=result)

    assert result.status is not BaselineQualificationStatus.QUALIFIED
    assert G03ApprovalService().decide(package, G03Decision.APPROVED).decision is G03Decision.REJECTED


def test_g03_is_stale_when_state_or_execution_profile_changes():
    current = evidence()
    result = BaselinePolicyService().evaluate(current)
    package = G03ApprovalPackageBuilder().build(run_id="run-1", actor="operator", evidence=current, qualification=result)

    decision = G03ApprovalService().decide(
        package,
        G03Decision.APPROVED,
        current_state_version=8,
        current_execution_profile_checksum="sha256:changed",
    )
    assert decision.decision is G03Decision.REJECTED
    assert decision.stale
