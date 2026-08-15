"""Domain contract tests for F01-01 immutable runtime requirement separation."""

from datetime import UTC, datetime

import pytest

from app.domain.runtime_execution import (
    RuntimeExecutableDescriptor,
    RuntimeExecutableKind,
    RuntimeRequirement,
    RuntimeRequirementBinding,
)

NOW = datetime(2026, 8, 15, tzinfo=UTC)


def descriptor(**changes) -> RuntimeExecutableDescriptor:
    values = {
        "kind": RuntimeExecutableKind.NODE,
        "executable_name": "node",
        "resolved_path": "/home/ubuntu/.nvm/versions/node/v18.20.8/bin/node",
        "version_exact": "18.20.8",
        "sha256": "a" * 64,
        "operating_system": "linux",
        "architecture": "amd64",
        "installation_root": "/home/ubuntu/.nvm/versions/node/v18.20.8",
        "source": "nvm",
        "runtime_id": "node18",
        "probed_at": NOW,
    }
    values.update(changes)
    return RuntimeExecutableDescriptor(**values)


def requirement(**changes) -> RuntimeRequirement:
    values = {
        "kind": RuntimeExecutableKind.NODE,
        "runtime_id": "node18",
        "version_exact": "18.20.8",
    }
    values.update(changes)
    return RuntimeRequirement(**values)


def test_descriptor_is_immutable():
    item = descriptor()
    with pytest.raises(ValueError):
        item.resolved_path = "/other/path"


def test_descriptor_rejects_unknown_fields_and_bad_checksum():
    with pytest.raises(ValueError):
        RuntimeExecutableDescriptor(**descriptor().model_dump(), extra_field="x")
    with pytest.raises(ValueError):
        descriptor(sha256="zz-not-hex")


def test_requirement_requires_semver():
    with pytest.raises(ValueError):
        requirement(version_exact="latest")
    with pytest.raises(ValueError):
        requirement(version_exact=None, minimum_version=None, required_sha256=None)


def test_requirement_satisfied_exact_version():
    assert requirement().satisfied_by(descriptor()) is True


def test_requirement_rejects_kind_mismatch():
    other = descriptor(kind=RuntimeExecutableKind.NPM, executable_name="npm")
    assert requirement().satisfied_by(other) is False


def test_requirement_minimum_version_semantics():
    req = requirement(version_exact=None, minimum_version="18.0.0")
    assert req.satisfied_by(descriptor()) is True
    assert req.satisfied_by(descriptor(version_exact="17.9.1")) is False


def test_requirement_checksum_bound():
    req = requirement(required_sha256="b" * 64)
    assert req.satisfied_by(descriptor()) is False
    assert req.satisfied_by(descriptor(sha256="b" * 64)) is True


def test_binding_requires_descriptor_that_satisfies_requirement():
    good = RuntimeRequirementBinding(requirement=requirement(), descriptor=descriptor(), resolved_at=NOW)
    assert good.requirement.satisfied_by(good.descriptor) is True
    bad = RuntimeRequirementBinding(
        requirement=requirement(), descriptor=descriptor(version_exact="16.0.0"), resolved_at=NOW
    )
    assert bad.requirement.satisfied_by(bad.descriptor) is False
    unresolved = RuntimeRequirementBinding(
        requirement=requirement(), blocked_reason="no compatible node", resolved_at=NOW
    )
    assert unresolved.descriptor is None


def test_descriptor_matches_identity_comparison():
    first = descriptor()
    assert first.matches(descriptor()) is True
    assert first.matches(descriptor(sha256="b" * 64)) is False
    assert first.matches(descriptor(resolved_path="/other")) is False
