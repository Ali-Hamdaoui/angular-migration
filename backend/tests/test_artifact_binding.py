import pytest

from app.services.artifact_binding import canonical_artifact_references, canonical_artifact_set_checksum


def test_artifact_references_are_sorted_and_checksum_is_order_independent():
    first = [{"artifact_id": "b", "checksum": "sha256:" + "b" * 64}, {"artifact_id": "a", "checksum": "sha256:" + "a" * 64}]
    second = list(reversed(first))

    assert canonical_artifact_references(first) == canonical_artifact_references(second)
    assert canonical_artifact_set_checksum(first) == canonical_artifact_set_checksum(second)


def test_conflicting_duplicate_artifact_reference_fails_closed():
    with pytest.raises(ValueError, match="conflicting checksum"):
        canonical_artifact_references([
            {"artifact_id": "a", "checksum": "sha256:" + "a" * 64},
            {"artifact_id": "a", "checksum": "sha256:" + "b" * 64},
        ])
