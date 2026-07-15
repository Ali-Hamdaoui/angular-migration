from app.domain.g02 import G02ApprovalPackageBuilder, G02ApprovalService, G02Decision


def _package(**overrides):
    values = {
        "run_id": "run-1", "state_version": 4, "actor": "operator",
        "snapshot_id": "snapshot-1", "gate_version": "g02-v1",
        "source_fingerprint": "sha256:source-before",
        "snapshot_fingerprint": "sha256:snapshot", "manifest_checksum": "sha256:manifest",
        "policy_version": "source-snapshot-policy-v1", "source_read_only_verified": True,
    }
    values.update(overrides)
    return G02ApprovalPackageBuilder().build(**values)


def test_valid_g02_approval_establishes_snapshot_boundary():
    package = _package()
    result = G02ApprovalService().decide(package, G02Decision.APPROVED)
    assert result.decision is G02Decision.APPROVED
    assert result.baseline_input_boundary == "snapshot-1"
    assert package.source_integrity_verified is True


def test_changed_source_fails_closed():
    package = _package(after_source_fingerprint="sha256:source-after")
    result = G02ApprovalService().decide(package, G02Decision.APPROVED)
    assert result.decision is G02Decision.REJECTED
    assert result.stale is True
    assert result.baseline_input_boundary is None


def test_approved_with_comment_requires_comment():
    package = _package()
    try:
        G02ApprovalService().decide(package, G02Decision.APPROVED_WITH_COMMENT)
    except ValueError as error:
        assert "comment" in str(error)
    else:
        raise AssertionError("approval without a comment should be rejected")

