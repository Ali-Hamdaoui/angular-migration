"""Deterministic source-runtime compatibility contracts and resolution rules.

This module deliberately has no process, filesystem, database, or network side
effects.  Inventory collection belongs to the environment capability boundary;
this module only decides whether an already observed candidate is eligible.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


POLICY_VERSION = "angular-source-runtime-v1"


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Version(_ImmutableModel):
    major: int = Field(ge=0)
    minor: int = Field(ge=0)
    patch: int = Field(ge=0)

    @classmethod
    def parse(cls, value: str) -> "Version | None":
        match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)", value)
        if not match:
            return None
        return cls(major=int(match.group(1)), minor=int(match.group(2)), patch=int(match.group(3)))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def at_least(self, other: "Version") -> bool:
        return (self.major, self.minor, self.patch) >= (other.major, other.minor, other.patch)


class RuntimeCandidate(_ImmutableModel):
    """One observed, paired Node/npm/npx installation."""

    profile_id: str = Field(min_length=1)
    operating_system: str = "windows"
    architecture: str = "amd64"
    node_executable: str = Field(min_length=1)
    node_exact: str = Field(min_length=1)
    npm_executable: str = Field(min_length=1)
    npm_exact: str = Field(min_length=1)
    npx_executable: str = Field(min_length=1)
    npx_exact: str = Field(min_length=1)
    angular_cli_exact: str | None = None
    installation_root: str | None = None
    registry_configured: bool = True
    proxy_configured: bool = True
    certificate_valid: bool = True
    environment_allowlist_valid: bool = True
    cache_policy_valid: bool = True
    network_policy: str = "approved-registries-only"
    available: bool = True

    @model_validator(mode="after")
    def require_paired_installation(self) -> "RuntimeCandidate":
        roots = {self._root(path) for path in (self.node_executable, self.npm_executable, self.npx_executable)}
        if len(roots) != 1:
            raise ValueError("node, npm, and npx must belong to one installation")
        return self

    @staticmethod
    def _root(path: str) -> str:
        normalized = path.replace("/", "\\").rstrip("\\")
        return normalized.rsplit("\\", 1)[0].lower()


class RuntimePolicy(_ImmutableModel):
    policy_version: str = POLICY_VERSION
    angular_major: int = 18
    supported_angular_minors: tuple[int, ...] = (0, 1, 2)
    node_minimums: dict[int, str] = {18: "18.19.1", 20: "20.11.1", 22: "22.0.0"}
    typescript_minimum: str = "5.4.0"
    typescript_exclusive_maximum: str = "5.6.0"
    rxjs_minimums: tuple[str, ...] = ("6.5.3", "7.4.0")
    operating_system: str = "windows"
    architecture: str = "amd64"
    allowed_network_policies: tuple[str, ...] = ("approved-registries-only",)


class ExecutionProfile(_ImmutableModel):
    profile_id: str
    operating_system: str
    architecture: str
    node_executable: str
    node_exact: str
    package_manager: Literal["npm"] = "npm"
    package_manager_executable: str
    package_manager_exact: str
    npx_executable: str
    npx_exact: str
    angular_cli_execution: Literal["npx"] = "npx"
    angular_cli_exact: str | None = None
    proxy_profile: str = "configured"
    certificate_profile: str = "validated"
    network_policy: str
    environment_allowlist: tuple[str, ...] = ("PATH", "HTTP_PROXY", "HTTPS_PROXY")
    cache_policy: str = "approved"
    compatibility_catalog_version: str
    source_angular_exact: str
    validated_at: datetime
    checksum: str


class RuntimeResolutionRequest(_ImmutableModel):
    source_angular_exact: str = Field(min_length=1)
    source_typescript_exact: str | None = None
    source_rxjs_exact: str | None = None
    candidates: tuple[RuntimeCandidate, ...] = ()
    expected_policy_version: str = POLICY_VERSION
    validated_at: datetime


class RuntimeResolutionResult(_ImmutableModel):
    status: Literal["resolved", "selection_required", "blocked"]
    policy_version: str
    compatible_profiles: tuple[ExecutionProfile, ...] = ()
    selected_profile: ExecutionProfile | None = None
    blockers: tuple[str, ...] = ()
    guidance: tuple[str, ...] = ()


class RuntimePolicyLoader:
    """Loads the versioned, checked-in policy for Sprint 1 source intake."""

    def load(self, policy_version: str = POLICY_VERSION) -> RuntimePolicy:
        if policy_version != POLICY_VERSION:
            raise ValueError("unsupported runtime compatibility policy")
        return RuntimePolicy(policy_version=policy_version)


class SourceRuntimeResolver:
    def __init__(self, policy_loader: RuntimePolicyLoader | None = None) -> None:
        self._loader = policy_loader or RuntimePolicyLoader()

    def resolve(self, request: RuntimeResolutionRequest) -> RuntimeResolutionResult:
        policy = self._loader.load(request.expected_policy_version)
        blockers: list[str] = []
        source = Version.parse(request.source_angular_exact)
        if source is None or source.major != policy.angular_major or source.minor not in policy.supported_angular_minors:
            blockers.append("SOURCE_ANGULAR_VERSION_UNSUPPORTED")
        if request.source_typescript_exact and not self._typescript_allowed(request.source_typescript_exact, policy):
            blockers.append("SOURCE_TYPESCRIPT_VERSION_INCOMPATIBLE")
        if request.source_rxjs_exact and not self._rxjs_allowed(request.source_rxjs_exact, policy):
            blockers.append("SOURCE_RXJS_VERSION_INCOMPATIBLE")
        if blockers:
            return self._blocked(policy, blockers)

        compatible: list[ExecutionProfile] = []
        for candidate in request.candidates:
            reasons = self._candidate_blockers(candidate, source, policy)
            if not reasons:
                compatible.append(self._profile(candidate, request, policy))
        compatible.sort(key=lambda profile: (self._version_key(profile.node_exact), profile.profile_id), reverse=True)
        if not compatible:
            return self._blocked(policy, ["NO_COMPATIBLE_RUNTIME_PROFILE"], ("Install or expose an approved paired Node/npm/npx runtime.",))
        if len(compatible) > 1:
            return RuntimeResolutionResult(status="selection_required", policy_version=policy.policy_version, compatible_profiles=tuple(compatible), guidance=("Select one approved runtime before baseline commands start.",))
        return RuntimeResolutionResult(status="resolved", policy_version=policy.policy_version, compatible_profiles=tuple(compatible), selected_profile=compatible[0])

    def confirm_selection(self, result: RuntimeResolutionResult, profile_id: str, checksum: str) -> ExecutionProfile:
        if result.status != "selection_required":
            raise ValueError("runtime selection is not required")
        profile = next((item for item in result.compatible_profiles if item.profile_id == profile_id), None)
        if profile is None or profile.checksum != checksum:
            raise ValueError("runtime profile selection is not an eligible checksum-bound candidate")
        return profile

    @staticmethod
    def is_stale(profile: ExecutionProfile, candidate: RuntimeCandidate, policy_version: str) -> bool:
        if profile.compatibility_catalog_version != policy_version:
            return True
        expected = SourceRuntimeResolver._profile(candidate, RuntimeResolutionRequest(source_angular_exact=profile.source_angular_exact, validated_at=profile.validated_at), RuntimePolicy(policy_version=policy_version))
        return expected.checksum != profile.checksum

    @staticmethod
    def _candidate_blockers(candidate: RuntimeCandidate, source: Version | None, policy: RuntimePolicy) -> list[str]:
        reasons: list[str] = []
        if not candidate.available:
            reasons.append("RUNTIME_PROFILE_UNAVAILABLE")
        if candidate.operating_system.lower() != policy.operating_system or candidate.architecture.lower() != policy.architecture:
            reasons.append("RUNTIME_PLATFORM_INCOMPATIBLE")
        node = Version.parse(candidate.node_exact)
        if node is None or source is None or node.major not in policy.node_minimums or not node.at_least(Version.parse(policy.node_minimums[node.major])):
            reasons.append("NODE_VERSION_INCOMPATIBLE")
        if Version.parse(candidate.npm_exact) is None or Version.parse(candidate.npx_exact) is None:
            reasons.append("PACKAGE_MANAGER_VERSION_UNRESOLVED")
        if candidate.angular_cli_exact and (Version.parse(candidate.angular_cli_exact) or Version(major=0, minor=0, patch=0)).major != policy.angular_major:
            reasons.append("ANGULAR_CLI_VERSION_INCOMPATIBLE")
        for valid, reason in ((candidate.registry_configured, "REGISTRY_UNAVAILABLE"), (candidate.certificate_valid, "CERTIFICATE_INVALID"), (candidate.environment_allowlist_valid, "ENVIRONMENT_ALLOWLIST_INVALID"), (candidate.cache_policy_valid, "CACHE_POLICY_INVALID")):
            if not valid:
                reasons.append(reason)
        if candidate.network_policy not in policy.allowed_network_policies:
            reasons.append("NETWORK_POLICY_UNAPPROVED")
        return reasons

    @staticmethod
    def _version_key(value: str) -> tuple[int, int, int]:
        version = Version.parse(value)
        return (version.major, version.minor, version.patch) if version else (-1, -1, -1)

    @staticmethod
    def _typescript_allowed(value: str, policy: RuntimePolicy) -> bool:
        version = Version.parse(value)
        return bool(version and version.at_least(Version.parse(policy.typescript_minimum)) and not version.at_least(Version.parse(policy.typescript_exclusive_maximum)))

    @staticmethod
    def _rxjs_allowed(value: str, policy: RuntimePolicy) -> bool:
        version = Version.parse(value)
        return bool(version and any(version.at_least(Version.parse(minimum)) for minimum in policy.rxjs_minimums))

    @staticmethod
    def _profile(candidate: RuntimeCandidate, request: RuntimeResolutionRequest, policy: RuntimePolicy) -> ExecutionProfile:
        payload = {
            "profile_id": candidate.profile_id, "operating_system": candidate.operating_system, "architecture": candidate.architecture,
            "node_executable": candidate.node_executable, "node_exact": candidate.node_exact, "package_manager": "npm",
            "package_manager_executable": candidate.npm_executable, "package_manager_exact": candidate.npm_exact,
            "npx_executable": candidate.npx_executable, "npx_exact": candidate.npx_exact, "angular_cli_execution": "npx",
            "angular_cli_exact": candidate.angular_cli_exact, "proxy_profile": "configured" if candidate.proxy_configured else "none",
            "certificate_profile": "validated" if candidate.certificate_valid else "invalid", "network_policy": candidate.network_policy,
            "environment_allowlist": ("PATH", "HTTP_PROXY", "HTTPS_PROXY"), "cache_policy": "approved",
            "compatibility_catalog_version": policy.policy_version, "source_angular_exact": request.source_angular_exact,
            "validated_at": request.validated_at,
        }
        canonical = json.dumps({key: (value.isoformat() if isinstance(value, datetime) else value) for key, value in payload.items()}, sort_keys=True, separators=(",", ":"), default=list).encode()
        return ExecutionProfile(**payload, checksum=f"sha256:{hashlib.sha256(canonical).hexdigest()}")

    @staticmethod
    def _blocked(policy: RuntimePolicy, blockers: list[str], guidance: tuple[str, ...] = ()) -> RuntimeResolutionResult:
        return RuntimeResolutionResult(status="blocked", policy_version=policy.policy_version, blockers=tuple(dict.fromkeys(blockers)), guidance=guidance)
