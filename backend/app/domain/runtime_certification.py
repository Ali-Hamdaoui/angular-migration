"""Bridge runtime certification contracts (V2 F11).

A runtime installation is certified for a migration stage when its node/npm/npx
descriptors satisfy the compatibility catalogue's certified runtime profile for
that stage's transition.  Certification is the pre-execution gate authority.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.runtime_execution import RuntimeExecutableDescriptor


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
    catalogue_version: str,
    resolved_at: datetime,
) -> RuntimeCertificationDecision:
    """Certify a resolved runtime against the catalogue's certified profiles.

    A runtime is certified when its node/npm exact versions match one of the
    catalogue entry's ``validated_runtime_profiles``.  A transition with no
    certified profiles cannot be certified (its entries remain
    ``historical_experimental`` until F11 certifies them).
    """
    if not catalogue_validated_profiles:
        return RuntimeCertificationDecision(
            run_id=run_id, stage_id=stage_id, source_family=source_family, target_family=target_family,
            certified=False, reason="transition has no certified runtime profiles yet",
            certified_against=catalogue_version, resolved_at=resolved_at,
        )
    if node_descriptor is None or npm_descriptor is None:
        return RuntimeCertificationDecision(
            run_id=run_id, stage_id=stage_id, source_family=source_family, target_family=target_family,
            certified=False, reason="runtime could not be resolved for the stage",
            certified_against=catalogue_version, resolved_at=resolved_at,
        )
    node_exact = _normalize_version(node_descriptor.version_exact)
    npm_exact = _normalize_version(npm_descriptor.version_exact)
    for certified_node, certified_npm in catalogue_validated_profiles:
        if node_exact == certified_node and npm_exact == certified_npm:
            return RuntimeCertificationDecision(
                run_id=run_id, stage_id=stage_id, source_family=source_family, target_family=target_family,
                runtime_id=node_descriptor.runtime_id, node_exact=node_exact, npm_exact=npm_exact,
                certified=True, reason="runtime matches a certified catalogue profile",
                certified_against=catalogue_version, resolved_at=resolved_at,
            )
    return RuntimeCertificationDecision(
        run_id=run_id, stage_id=stage_id, source_family=source_family, target_family=target_family,
        runtime_id=node_descriptor.runtime_id, node_exact=node_exact, npm_exact=npm_exact,
        certified=False, reason=f"runtime {node_exact}/{npm_exact} does not match any certified profile",
        certified_against=catalogue_version, resolved_at=resolved_at,
    )


def _normalize_version(value: str | None) -> str | None:
    if value is None:
        return None
    return value[1:] if value[:1] in {"v", "V"} else value


def now_utc() -> datetime:
    return datetime.now(UTC)
