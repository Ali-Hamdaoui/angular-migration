"""Authoritative, side-effect-free application contract for S2-F05-I01."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Callable

from app.domain.compatibility import (
    CompatibilityCatalogue,
    CompatibilityResolutionRequest,
    CompatibilityResolutionResult,
    FeasibilityPackage,
    G05Package,
    Stage1ExecutionProfile,
    calculate_stage1_profile_checksum,
)
from app.domain.execution_profile import RuntimeCandidate, Version
from app.services.artifact_binding import canonical_artifact_set_checksum


class CompatibilityApplicationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class CatalogueRouteDecision:
    source_family: str
    target_family: str
    entries: tuple
    blocker: str | None = None


def resolve_catalogue_route(catalogue: CompatibilityCatalogue, source_exact: str, target_family: str) -> CatalogueRouteDecision:
    source = Version.parse(source_exact)
    source_family = f"angular-{source.major}.x" if source is not None else "unknown"
    canonical_target = target_family.strip()
    if re.fullmatch(r"\d+\.x", canonical_target):
        canonical_target = f"angular-{canonical_target}"
    supported_sources = {entry.source_family for entry in catalogue.entries}
    supported_targets = {entry.target_family for entry in catalogue.entries}
    if source is None or source_family not in supported_sources:
        return CatalogueRouteDecision(source_family, canonical_target, (), "SOURCE_FAMILY_UNSUPPORTED")
    if canonical_target not in supported_targets:
        return CatalogueRouteDecision(source_family, canonical_target, (), "TARGET_FAMILY_UNSUPPORTED")
    target_major = int(canonical_target.removeprefix("angular-").removesuffix(".x"))
    if source.major >= target_major:
        return CatalogueRouteDecision(source_family, canonical_target, (), "TARGET_MUST_BE_GREATER_THAN_SOURCE")
    entries = []
    for major in range(source.major, target_major):
        entry = catalogue.entry_for(f"angular-{major}.x", f"angular-{major + 1}.x")
        if entry is None:
            return CatalogueRouteDecision(source_family, canonical_target, (), f"CATALOGUE_ROUTE_MISSING_{major}_{major + 1}")
        entries.append(entry)
    return CatalogueRouteDecision(source_family, canonical_target, tuple(entries))


class CompatibilityResolver:
    """Resolve only catalogue data and already-observed runtime candidates."""

    def __init__(self, catalogue: CompatibilityCatalogue, *, gate_version: str = "g05-v1") -> None:
        self.catalogue = catalogue
        self.gate_version = gate_version

    def resolve(self, request: CompatibilityResolutionRequest) -> CompatibilityResolutionResult:
        if request.catalogue_version != self.catalogue.version:
            raise CompatibilityApplicationError("STALE_CATALOGUE", "The requested compatibility catalogue is not current.", 409)
        decision = resolve_catalogue_route(self.catalogue, request.source_angular_exact, request.target_family)
        source_family = decision.source_family
        if decision.blocker:
            return self._blocked(request, decision.blocker, source_family)
        entries = decision.entries

        blockers = list(dict.fromkeys([*request.dependency_findings, *(reason for entry in entries for reason in entry.blockers)]))
        warnings = list(dict.fromkeys(risk for entry in entries for risk in entry.known_risks))
        route = tuple(
            self._stage(entry, request, blockers if entry.blockers else (), warnings if entry.known_risks else ())
            for entry in entries
        )
        profile = self._select_stage1_profile(request, entries[0])
        if profile is None:
            blockers.append("NO_COMPATIBLE_STAGE1_PROFILE")
        status = "blocked" if blockers else ("feasible_with_warnings" if warnings else "feasible")
        support_level = "blocked" if blockers else ("historical_experimental" if any(e.support_level == "historical_experimental" for e in entries) else entries[0].support_level)
        return self._result(request, source_family, route, profile, support_level, status, tuple(blockers), tuple(warnings))

    def _select_stage1_profile(self, request, entry) -> Stage1ExecutionProfile | None:
        candidates = [candidate for candidate in request.runtime_candidates if self._candidate_allowed(candidate, entry)]
        if not candidates:
            return None
        candidates.sort(key=lambda candidate: (self._version_key(candidate.node_exact), candidate.profile_id), reverse=True)
        candidate = candidates[0]
        payload = {
            "profile_id": candidate.profile_id,
            "angular_exact": entry.target_angular_exact,
            "angular_cli_exact": entry.cli_exact or entry.target_cli_exact,
            "node_exact": candidate.node_exact,
            "npm_exact": candidate.npm_exact,
            "npx_exact": candidate.npx_exact,
            "node_executable": candidate.node_executable,
            "npm_executable": candidate.npm_executable,
            "npx_executable": candidate.npx_executable,
            "operating_system": candidate.operating_system,
            "architecture": candidate.architecture,
            "catalogue_version": self.catalogue.version,
            "source_angular_exact": request.source_angular_exact,
        }
        stage1_checksum = "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return Stage1ExecutionProfile(
            **payload,
            source_execution_profile_checksum=request.source_execution_profile_checksum,
            stage1_profile_checksum=stage1_checksum,
            checksum=stage1_checksum,
        )

    @staticmethod
    def _candidate_allowed(candidate: RuntimeCandidate, entry) -> bool:
        node = Version.parse(candidate.node_exact)
        npm = Version.parse(candidate.npm_exact)
        npx = Version.parse(candidate.npx_exact)
        if entry.validated_runtime_profiles:
            version_allowed = bool(
                node
                and npm
                and any(str(node) == node_exact and str(npm) == npm_exact for node_exact, npm_exact in entry.validated_runtime_profiles)
            )
        else:
            version_allowed = bool(
                node
                and npm
                and node.major == entry.node_major
                and npm.major == entry.npm_major
                and (entry.node_exact is None or str(node) == entry.node_exact)
                and (entry.npm_exact is None or str(npm) == entry.npm_exact)
            )
        return bool(
            candidate.available
            and candidate.operating_system.lower() == "windows"
            and candidate.architecture.lower() == "amd64"
            and node
            and npm
            and npx
            and version_allowed
            and npx.major == entry.npm_major
            and (candidate.angular_cli_exact is None or candidate.angular_cli_exact == (entry.cli_exact or entry.target_cli_exact))
            and candidate.registry_configured
            and candidate.certificate_valid
            and candidate.environment_allowlist_valid
            and candidate.cache_policy_valid
            and candidate.network_policy == "approved-registries-only"
        )

    @staticmethod
    def _version_key(value: str) -> tuple[int, int, int]:
        version = Version.parse(value)
        return (version.major, version.minor, version.patch) if version else (-1, -1, -1)

    @staticmethod
    def _stage(entry, request, blockers, warnings):
        return {
            "stage_id": entry.stage_id,
            "source_family": entry.source_family,
            "target_family": entry.target_family,
            "support_level": entry.support_level,
            "target_angular_exact": entry.target_angular_exact,
            "target_cli_exact": entry.target_cli_exact,
            "node_exact": entry.node_exact,
            "npm_exact": entry.npm_exact,
            "blockers": tuple(blockers),
            "warnings": tuple(warnings),
        }

    def _blocked(self, request, reason, source_family=None):
        source_family = source_family or "unknown"
        return self._result(request, source_family, (), None, "blocked", "blocked", (reason,), ())

    def _result(self, request, source_family, route, profile, support_level, status, blockers, warnings):
        artifact_set_checksum = self._artifact_set_checksum(request)
        package_payload = {
            "catalogue_version": self.catalogue.version,
            "catalogue_checksum": self.catalogue.checksum,
            "source_exact": request.source_angular_exact,
            "source_family": source_family,
            "target_family": request.target_family,
            "support_level": support_level,
            "route": [stage.model_dump(mode="json") if hasattr(stage, "model_dump") else stage for stage in route],
            "selected_profile": profile.model_dump(mode="json") if profile else None,
            "blockers": blockers,
            "warnings": warnings,
            "artifact_set_checksum": artifact_set_checksum,
            "workspace_fingerprint": request.workspace_fingerprint,
            "plan_version": request.plan_version,
        }
        package_checksum = "sha256:" + hashlib.sha256(json.dumps(package_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        package = FeasibilityPackage(**package_payload, package_checksum=package_checksum)
        gate = G05Package(
            status="blocked" if status == "blocked" else "pending",
            package_checksum=package_checksum,
            artifact_set_checksum=artifact_set_checksum,
            state_version=request.expected_state_version,
            workspace_fingerprint=request.workspace_fingerprint,
            plan_version=request.plan_version,
            feasibility=package,
        )
        return CompatibilityResolutionResult(
            run_id=request.run_id,
            status=status,
            source_exact=request.source_angular_exact,
            source_family=source_family,
            target_family=request.target_family,
            support_level=support_level,
            route=tuple(route),
            selected_profile=profile,
            package=package,
            gate=gate,
            state_version=request.expected_state_version,
        )

    @staticmethod
    def _artifact_set_checksum(request):
        return canonical_artifact_set_checksum(request.prerequisite_artifacts)


class CompatibilityApplicationService:
    """Application seam; persistence and event adapters belong to S2-F05-I02."""

    def __init__(self, *, resolver: CompatibilityResolver, state_version_reader: Callable[[str], int] | None = None, artifact_reader: Callable[[str], str] | None = None) -> None:
        self._resolver = resolver
        self._state_version_reader = state_version_reader
        self._artifact_reader = artifact_reader
        self._results: dict[tuple[str, str], tuple[str, CompatibilityResolutionResult]] = {}

    def resolve(self, request: CompatibilityResolutionRequest) -> CompatibilityResolutionResult:
        request_checksum = self._checksum(request.model_dump(mode="json"))
        key = (request.run_id, request.idempotency_key)
        existing = self._results.get(key)
        if existing:
            if existing[0] != request_checksum:
                raise CompatibilityApplicationError("IDEMPOTENCY_PAYLOAD_MISMATCH", "The idempotency key was already used with a different payload.", 409)
            return existing[1].model_copy(update={"idempotent_replay": True})
        if self._state_version_reader and self._state_version_reader(request.run_id) != request.expected_state_version:
            raise CompatibilityApplicationError("STALE_STATE_VERSION", "The run state version is stale.", 409)
        self._validate_artifacts(request)
        try:
            result = self._resolver.resolve(request)
        except CompatibilityApplicationError:
            raise
        except Exception as error:
            raise CompatibilityApplicationError("COMPATIBILITY_RESOLUTION_FAILED", "Compatibility resolution failed closed.", 503) from error
        self._results[key] = (request_checksum, result)
        return result

    def _validate_artifacts(self, request):
        if not self._artifact_reader:
            return
        for artifact in request.prerequisite_artifacts:
            try:
                actual = self._artifact_reader(artifact.artifact_id)
            except Exception as error:
                raise CompatibilityApplicationError("PREREQUISITE_ARTIFACT_UNAVAILABLE", "A prerequisite artifact is unavailable.", 409) from error
            if actual != artifact.checksum:
                raise CompatibilityApplicationError("PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH", "A prerequisite artifact checksum does not match.", 409)

    @staticmethod
    def _checksum(payload):
        return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
