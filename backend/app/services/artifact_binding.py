"""Canonical checksum-bound artifact reference handling."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping


_CHECKSUM = re.compile(r"^sha256:[0-9a-f]{64}$")


def canonical_artifact_references(references: Iterable[Mapping[str, str] | object]) -> tuple[dict[str, str], ...]:
    """Validate, deduplicate, and deterministically order artifact references."""
    by_id: dict[str, str] = {}
    for reference in references:
        artifact_id = reference.get("artifact_id") if isinstance(reference, Mapping) else getattr(reference, "artifact_id", None)
        checksum = reference.get("checksum") if isinstance(reference, Mapping) else getattr(reference, "checksum", None)
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise ValueError("artifact reference requires a non-empty artifact_id")
        if not isinstance(checksum, str) or not _CHECKSUM.fullmatch(checksum):
            raise ValueError("artifact reference requires a sha256 checksum")
        previous = by_id.get(artifact_id)
        if previous is not None and previous != checksum:
            raise ValueError("artifact reference has a conflicting checksum")
        by_id[artifact_id] = checksum
    return tuple({"artifact_id": artifact_id, "checksum": by_id[artifact_id]} for artifact_id in sorted(by_id))


def canonical_artifact_set_checksum(references: Iterable[Mapping[str, str] | object]) -> str:
    canonical = canonical_artifact_references(references)
    payload = [[item["artifact_id"], item["checksum"]] for item in canonical]
    return "sha256:" + hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
