"""Bridge runtime certification contracts (V2 F11).

A runtime installation is certified for a migration stage when its node/npm
descriptors satisfy the compatibility catalogue's certified runtime profile for
that stage's transition.  Certification is the pre-execution gate authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.runtime_execution import RuntimeExecutableDescriptor
from app.domain.runtime_compatibility import RuntimeCompatibilityClass, classify_runtime_versions


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


#: Immutable plan/run mode. Missing mode reads as PRODUCTION; QUALIFICATION
#: always requires its explicit authorization checksum.
RunMode = Literal["PRODUCTION", "QUALIFICATION"]

#: Immutable evidence sections a complete qualification bundle must contain
#: before deterministic certification promotion may accept it.
QUALIFICATION_EVIDENCE_SECTIONS: tuple[str, ...] = (
    "npm_ci",
    "dependency_tree",
    "build",
    "test",
    "migration",
    "validation",
    "gate",
    "promotion",
    "seal",
    "final_fingerprint_chain",
)


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
    run_mode: RunMode = "PRODUCTION"
    qualification_authorization_checksum: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )

    @model_validator(mode="after")
    def validate_qualification_authorization(self) -> RuntimeCertificationDecision:
        if self.run_mode == "QUALIFICATION" and not self.qualification_authorization_checksum:
            raise ValueError("qualification decisions require an explicit authorization checksum")
        return self


def canonical_payload_checksum(payload: Mapping[str, object]) -> str:
    """Stable sha256 binding for immutable JSON contracts."""
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(serialized.encode()).hexdigest()


def _authorization_checksum_for_payload(payload: Mapping[str, object]) -> str:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if key == "authorization_checksum":
            continue
        if isinstance(value, datetime):
            normalized[key] = value.isoformat()
        elif key in _DATETIME_PAYLOAD_FIELDS and isinstance(value, str):
            normalized[key] = datetime.fromisoformat(value).isoformat()
        else:
            normalized[key] = value
    return canonical_payload_checksum(normalized)


#: Payload fields that carry datetimes and must serialize identically whether
#: supplied as datetime objects or ISO strings.
_DATETIME_PAYLOAD_FIELDS = frozenset({"expires_at", "decided_at"})


class RuntimeQualificationAuthorization(_ImmutableModel):
    """Immutable operator authorization to exercise an allowed-but-uncertified runtime.

    QUALIFICATION mode may execute only under this explicit authorization; it
    never exposes the profile to PRODUCTION and never sets ``certified``.
    """

    schema_version: Literal["runtime-qualification-authorization-v1"] = (
        "runtime-qualification-authorization-v1"
    )
    authorization_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    source_family: str = Field(pattern=r"^angular-(1[1-9]|2[01])\.x$")
    target_family: str = Field(pattern=r"^angular-(1[1-9]|2[01])\.x$")
    runtime_descriptor_checksums: tuple[str, ...] = ()
    catalogue_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    expires_at: datetime
    authorization_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @classmethod
    def bind(cls, **fields) -> "RuntimeQualificationAuthorization":
        """Construct with a deterministic checksum bound over the full payload."""
        payload = dict(fields)
        payload.setdefault("schema_version", cls.model_fields["schema_version"].default)
        checksum = _authorization_checksum_for_payload(payload)
        return cls(**payload, authorization_checksum=checksum)

    @model_validator(mode="after")
    def bind_checksum(self) -> RuntimeQualificationAuthorization:
        expected = _authorization_checksum_for_payload(self.model_dump())
        if self.authorization_checksum != expected:
            raise ValueError("qualification authorization checksum does not bind its payload")
        return self

    @property
    def digest(self) -> str:
        """Lowercase SHA256 hex (no scheme prefix) used in deterministic paths."""
        return self.authorization_checksum.removeprefix("sha256:")


class RuntimeQualificationEvidence(_ImmutableModel):
    """Checksum-bound evidence bundle produced by one qualification execution."""

    schema_version: Literal["runtime-qualification-evidence-v1"] = (
        "runtime-qualification-evidence-v1"
    )
    evidence_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    authorization_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    node_path: str = Field(min_length=1)
    npm_path: str = Field(min_length=1)
    npx_path: str = Field(min_length=1)
    node_exact: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    npm_exact: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    npx_exact: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    node_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    npm_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    npx_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalogue_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    governed_path_checksum: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    cli_toolchain_authority_checksums: tuple[str, ...] = ()
    dependency_intent_checksum: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    lockfile_policy_checksum: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    #: Named immutable evidence references; every section required for
    #: certification promotion must be present and non-empty.
    sections: Mapping[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_required_sections(self) -> RuntimeQualificationEvidence:
        missing = [name for name in QUALIFICATION_EVIDENCE_SECTIONS if not self.sections.get(name)]
        if missing:
            raise ValueError(f"incomplete qualification evidence; missing sections: {sorted(missing)}")
        return self

    @property
    def descriptor_checksums(self) -> tuple[str, ...]:
        return tuple(
            canonical_payload_checksum({"kind": kind, "path": path, "version": version, "sha256": sha})
            for kind, path, version, sha in (
                ("node", self.node_path, self.node_exact, self.node_sha256),
                ("npm", self.npm_path, self.npm_exact, self.npm_sha256),
                ("npx", self.npx_path, self.npx_exact, self.npx_sha256),
            )
        )


class RuntimeCertificationPromotionDecision(_ImmutableModel):
    """Explicit reviewer decision required before certification promotion."""

    schema_version: Literal["runtime-certification-promotion-v1"] = (
        "runtime-certification-promotion-v1"
    )
    decision_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    authorization_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reviewer: str = Field(min_length=1)
    decision: Literal["accepted", "rejected"]
    reason: str | None = None
    evidence_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    decided_at: datetime

    @property
    def promotion_checksum(self) -> str:
        return canonical_payload_checksum(self.model_dump(mode="json"))


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


def qualification_authorization_path(stage_id: str, authorization_digest: str) -> str:
    """Deterministic immutable authorization artifact path."""
    return f"04_workflow_state/stages/{stage_id}/runtime-qualification/{authorization_digest}/authorization.json"


def qualification_evidence_path(stage_id: str, authorization_digest: str) -> str:
    """Deterministic immutable evidence artifact path."""
    return f"04_workflow_state/stages/{stage_id}/runtime-qualification/{authorization_digest}/evidence.json"


def qualification_promotion_path(stage_id: str, authorization_digest: str) -> str:
    """Deterministic immutable promotion-decision artifact path."""
    return f"04_workflow_state/stages/{stage_id}/runtime-qualification/{authorization_digest}/promotion.json"


def runtime_certification_artifact_path(stage_id: str, record_id: str) -> str:
    """Deterministic authoritative certification decision artifact path."""
    return f"04_workflow_state/stages/{stage_id}/runtime-certifications/{record_id}.json"


def _normalize_version(value: str | None) -> str | None:
    if value is None:
        return None
    return value[1:] if value[:1] in {"v", "V"} else value


def now_utc() -> datetime:
    return datetime.now(UTC)
