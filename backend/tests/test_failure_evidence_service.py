import pytest

from app.domain.transformation import FailureRoute
from app.services.failure_evidence_service import FailureEvidenceService


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("REGISTRY_TIMEOUT", FailureRoute.ENVIRONMENT_TRANSIENT),
        ("EXECUTION_PROFILE_NOT_FOUND", FailureRoute.ENVIRONMENT_PERMANENT),
        ("DEPENDENCY_PREFLIGHT_BLOCKED", FailureRoute.DEPENDENCY_INCOMPATIBLE),
        ("UNEXPECTED_PROMPT", FailureRoute.UNEXPECTED_PROMPT),
        ("VALIDATION_WORKSPACE_MUTATED", FailureRoute.POLICY_VIOLATION),
        ("VALIDATION_EVIDENCE_MISSING", FailureRoute.NON_REPAIRABLE_VALIDATION),
        ("COMPILATION_FAILED", FailureRoute.REPAIRABLE_SOURCE),
    ],
)
def test_classifier_has_closed_deterministic_routes(code, expected):
    evidence = {
        "normalized_failure": {"error_code": code},
        "failure_fingerprint": "sha256:new",
        "prior_fingerprints": [],
    }

    assert FailureEvidenceService().classify(evidence) == expected


def test_identical_failure_is_no_progress():
    evidence = {
        "normalized_failure": {"error_code": "COMPILATION_FAILED"},
        "failure_fingerprint": "sha256:same",
        "prior_fingerprints": ["sha256:same"],
    }

    assert FailureEvidenceService().classify(evidence) == FailureRoute.NO_PROGRESS
