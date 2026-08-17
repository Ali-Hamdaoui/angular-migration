from datetime import UTC, datetime

import pytest

from app.domain.execution_profile import (
    RuntimeCandidate,
    RuntimeResolutionRequest,
    SourceRuntimeResolver,
)


NOW = datetime(2026, 7, 15, tzinfo=UTC)


def candidate(profile_id: str, *, node: str = "20.11.1", angular_cli: str = "18.2.3", **changes) -> RuntimeCandidate:
    values = {
        "profile_id": profile_id,
        "node_executable": r"C:\\Tools\\node20\\node.exe",
        "node_exact": node,
        "npm_executable": r"C:\\Tools\\node20\\npm.cmd",
        "npm_exact": "10.2.4",
        "npx_executable": r"C:\\Tools\\node20\\npx.cmd",
        "npx_exact": "10.2.4",
        "angular_cli_exact": angular_cli,
    }
    values.update(changes)
    return RuntimeCandidate(**values)


def request(*candidates: RuntimeCandidate, angular: str = "18.2.3", ts: str = "5.5.4", rxjs: str = "7.8.1") -> RuntimeResolutionRequest:
    return RuntimeResolutionRequest(
        source_angular_exact=angular,
        source_typescript_exact=ts,
        source_rxjs_exact=rxjs,
        candidates=tuple(candidates),
        validated_at=NOW,
    )


def test_resolves_one_exact_source_compatible_profile_with_checksum():
    result = SourceRuntimeResolver().resolve(request(candidate("node-20")))

    assert result.status == "resolved"
    assert result.selected_profile is not None
    assert result.selected_profile.node_exact == "20.11.1"
    assert result.selected_profile.package_manager == "npm"
    assert result.selected_profile.checksum.startswith("sha256:")


def test_multiple_profiles_require_explicit_checksum_bound_selection():
    result = SourceRuntimeResolver().resolve(request(candidate("node-20"), candidate("node-22", node="22.0.0")))

    assert result.status == "selection_required"
    selected = SourceRuntimeResolver().confirm_selection(result, "node-20", next(p.checksum for p in result.compatible_profiles if p.profile_id == "node-20"))
    assert selected.profile_id == "node-20"


def test_host_incompatible_runtime_is_blocked_and_not_silently_used():
    result = SourceRuntimeResolver().resolve(request(candidate("node-16", node="16.20.2")))

    assert result.status == "blocked"
    assert "NO_COMPATIBLE_RUNTIME_PROFILE" in result.blockers


def test_candidate_integrity_and_environment_constraints_block_resolution():
    result = SourceRuntimeResolver().resolve(request(candidate("bad", registry_configured=False)))

    assert result.status == "blocked"
    assert "NO_COMPATIBLE_RUNTIME_PROFILE" in result.blockers


def test_source_version_and_typescript_compatibility_are_fail_closed():
    unsupported = SourceRuntimeResolver().resolve(request(candidate("node-20"), angular="10.3.12"))
    wrong_typescript = SourceRuntimeResolver().resolve(request(candidate("node-20"), ts="5.6.0"))

    assert unsupported.status == "blocked"
    assert "SOURCE_ANGULAR_VERSION_UNSUPPORTED" in unsupported.blockers
    assert wrong_typescript.status == "blocked"
    assert "SOURCE_TYPESCRIPT_VERSION_INCOMPATIBLE" in wrong_typescript.blockers


def test_selection_rejects_unknown_or_tampered_checksum():
    result = SourceRuntimeResolver().resolve(request(candidate("node-20"), candidate("node-22", node="22.0.0")))

    with pytest.raises(ValueError, match="checksum-bound"):
        SourceRuntimeResolver().confirm_selection(result, "node-20", "sha256:tampered")


@pytest.mark.parametrize(
    ("angular", "typescript", "node", "cli", "rxjs"),
    (
        ("11.2.14", "4.1.6", "12.22.12", "11.2.14", "6.5.3"),
        ("12.2.17", "4.3.5", "14.20.2", "12.2.17", "6.5.3"),
        ("16.2.12", "5.1.6", "18.20.8", "16.2.12", "7.8.1"),
        ("18.2.3", "5.5.4", "20.11.1", "18.2.3", "7.8.1"),
    ),
)
def test_source_runtime_resolution_uses_catalogue_constraints(angular, typescript, node, cli, rxjs):
    result = SourceRuntimeResolver().resolve(
        request(
            candidate(
                f"node-{node}",
                node=node,
                angular_cli=cli,
                npm_exact="8.19.4" if node.startswith(("12.", "16.")) else "10.2.4",
                npx_exact="8.19.4" if node.startswith(("12.", "16.")) else "10.2.4",
            ),
            angular=angular,
            ts=typescript,
            rxjs=rxjs,
        )
    )

    assert result.status == "resolved"
    assert result.selected_profile is not None
    assert result.selected_profile.source_angular_exact == angular


def test_source_runtime_resolution_rejects_out_of_envelope_and_incompatible_candidate():
    unsupported = SourceRuntimeResolver().resolve(
        request(candidate("node-12", node="12.22.12", angular_cli="10.0.0"), angular="22.0.0", ts="5.9.0")
    )
    incompatible = SourceRuntimeResolver().resolve(
        request(candidate("node-10", node="10.13.0", angular_cli="16.2.12"), angular="16.2.12", ts="5.1.6")
    )

    assert "SOURCE_ANGULAR_VERSION_UNSUPPORTED" in unsupported.blockers
    assert incompatible.status == "blocked"
    assert "NO_COMPATIBLE_RUNTIME_PROFILE" in incompatible.blockers
