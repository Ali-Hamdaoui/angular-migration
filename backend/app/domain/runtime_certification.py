"""Bridge runtime certification contracts (V2 F11).

A runtime installation is certified for a migration stage when its node/npm
descriptors satisfy the compatibility catalogue's certified runtime profile for
that stage's transition.  Certification is the pre-execution gate authority.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.runtime_execution import RuntimeExecutableDescriptor
from app.domain.runtime_compatibility import RuntimeCompatibilityClass, classify_runtime_versions


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeCertificationDecision(_ImmutableModel):
    """Deterministic result of certifying a runtime against a stage transition."""

    run_id: str
    stage_id: str
    source_family: str
    target_family: str
    runtime_id: str | None = None
    node_exact: str | None = None
    npm_exact: str | None = None
    certified: bool
    allowed: bool = False
    classification: RuntimeCompatibilityClass = "UNSUPPORTED"
    reason: str | None = None
    certified_against: str | None = None
    resolved_at: datetime


def evaluate_certification(
    *,
    run_id: str,
    stage_id: str,
    source_family: str,
    target_family: str,
    node_descriptor: RuntimeExecutableDescriptor | None,
    npm_descriptor: RuntimeExecutableDescriptor | None,
    catalogue_validated_profiles: tuple[tuple[str, str], ...],
    source_node_ranges: tuple[str, ...] = (),
    target_node_ranges: tuple[str, ...] = (),
    npx_descriptor: RuntimeExecutableDescriptor | None = None,
    catalogue_version: str,
    resolved_at: datetime,
) -> RuntimeCertificationDecision:
    """Certify a resolved runtime against the catalogue's certified profiles.

    A runtime is certified when its node/npm exact versions match one of the
    catalogue entry's ``validated_runtime_profiles``.  A transition with no
    certified profiles cannot be certified (its entries remain
    ``historical_experimental`` until F11 certifies them).
    """
    if node_descriptor is None or npm_descriptor is None:
        return RuntimeCertificationDecision(
            run_id=run_id, stage_id=stage_id, source_family=source_family, target_family=target_family,
            certified=False, reason="runtime could not be resolved for the stage", classification="UNSUPPORTED",
            certified_against=catalogue_version, resolved_at=resolved_at,
        )
    if not catalogue_validated_profiles and not source_node_ranges and not target_node_ranges:
        return RuntimeCertificationDecision(
            run_id=run_id, stage_id=stage_id, source_family=source_family, target_family=target_family,
            certified=False, allowed=False, classification="UNSUPPORTED",
            reason="transition has no certified runtime profiles yet",
            certified_against=catalogue_version, resolved_at=resolved_at,
        )
    node_exact = _normalize_version(node_descriptor.version_exact)
    npm_exact = _normalize_version(npm_descriptor.version_exact)
    classification = classify_runtime_versions(
        node_exact=node_exact,
        npm_exact=npm_exact,
        npx_exact=_normalize_version(npx_descriptor.version_exact) if npx_descriptor else None,
        validated_runtime_profiles=catalogue_validated_profiles,
        source_node_ranges=source_node_ranges,
        target_node_ranges=target_node_ranges,
    )
    if classification == "EXACT_CERTIFIED":
        return RuntimeCertificationDecision(
            run_id=run_id, stage_id=stage_id, source_family=source_family, target_family=target_family,
            runtime_id=node_descriptor.runtime_id, node_exact=node_exact, npm_exact=npm_exact,
            certified=True, allowed=True, classification=classification,
            reason="runtime matches a certified catalogue profile",
            certified_against=catalogue_version, resolved_at=resolved_at,
        )
    if classification == "RANGE_COMPATIBLE":
        runtime_ids = {node_descriptor.runtime_id, npm_descriptor.runtime_id, npx_descriptor.runtime_id if npx_descriptor else None}
        if npx_descriptor is None or None in runtime_ids or len(runtime_ids) != 1:
            classification = "UNSUPPORTED"
        else:
            return RuntimeCertificationDecision(
                run_id=run_id, stage_id=stage_id, source_family=source_family, target_family=target_family,
                runtime_id=node_descriptor.runtime_id, node_exact=node_exact, npm_exact=npm_exact,
                certified=False, allowed=True, classification=classification,
                reason="runtime satisfies the official source/target Node range intersection and runtime governance",
                certified_against=catalogue_version, resolved_at=resolved_at,
            )
    return RuntimeCertificationDecision(
        run_id=run_id, stage_id=stage_id, source_family=source_family, target_family=target_family,
        runtime_id=node_descriptor.runtime_id, node_exact=node_exact, npm_exact=npm_exact,
        certified=False, allowed=False, classification=classification,
        reason=f"runtime {node_exact}/{npm_exact} is outside the governed compatibility policy",
        certified_against=catalogue_version, resolved_at=resolved_at,
    )


def _normalize_version(value: str | None) -> str | None:
    if value is None:
        return None
    return value[1:] if value[:1] in {"v", "V"} else value


def now_utc() -> datetime:
    return datetime.now(UTC)
