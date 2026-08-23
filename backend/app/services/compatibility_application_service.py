"""Authoritative, side-effect-free application contract for S2-F05-I01."""

from __future__ import annotations

import hashlib
import json
import re
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
from app.domain.runtime_compatibility import RuntimeCompatibilityClass, classify_runtime_versions
from app.domain.runtime_certification import RunMode
from app.services.artifact_binding import canonical_artifact_set_checksum
from app.services.migration_route_service import MigrationRouteError, MigrationRouteService


class CompatibilityApplicationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class CompatibilityResolver:
    """Resolve only catalogue data and already-observed runtime candidates."""

    def __init__(
        self,
        catalogue: CompatibilityCatalogue,
        *,
        gate_version: str = "g05-v1",
        route_service: MigrationRouteService | None = None,
        certified_profile_lookup: Callable[[str, str], tuple[tuple[str, str], ...]] | None = None,
    ) -> None:
        self.catalogue = catalogue
        self.gate_version = gate_version
        self._route_service = route_service or MigrationRouteService()
        # Optional promoted-certification source so production feasibility can
        # accept exact tuples whose immutable evidence was reviewed and
        # promoted after the static catalogue was frozen.
        self._certified_profile_lookup = certified_profile_lookup

    def resolve(self, request: CompatibilityResolutionRequest) -> CompatibilityResolutionResult:
        if request.catalogue_version != self.catalogue.version:
            raise CompatibilityApplicationError("STALE_CATALOGUE", "The requested compatibility catalogue is not current.", 409)
        source = Version.parse(request.source_angular_exact)
        if source is None:
            return self._blocked(request, "SOURCE_FAMILY_UNSUPPORTED")
        source_family = f"angular-{source.major}.x"
        supported_sources = {entry.source_family for entry in self.catalogue.entries}
        if source_family not in supported_sources:
            return self._blocked(request, "SOURCE_FAMILY_UNSUPPORTED", source_family)
        target_major = int(request.target_family.removeprefix("angular-").removesuffix(".x"))
        try:
            route_authority = self._route_service.compute(
                source.major,
                target_major,
                catalogue_version=self.catalogue.version,
                catalogue=self.catalogue,
            )
        except MigrationRouteError as error:
            if error.code == "CATALOGUE_ROUTE_MISSING":
                major = error.details.get("major")
                blocker = f"CATALOGUE_ROUTE_MISSING_{major}_{int(major) + 1}" if major is not None else error.code
            elif error.code == "ENVELOPE_VIOLATION" and str(error.details.get("blocker", "")).startswith("ROUTE_DIRECTION_INVALID"):
                blocker = "TARGET_MUST_BE_GREATER_THAN_SOURCE"
            else:
                blocker = error.code
            return self._blocked(request, blocker, source_family)
        entries = tuple(
            self.catalogue.entry_for(stage.source_family, stage.target_family)
            for stage in route_authority.stages
        )
        if any(entry is None for entry in entries):
            return self._blocked(request, "CATALOGUE_ROUTE_MISSING", source_family)
        entries = tuple(entry for entry in entries if entry is not None)
        entries = tuple(self._entry_with_promoted_profiles(entry) for entry in entries)

        blockers = list(dict.fromkeys([*request.dependency_findings, *(reason for entry in entries for reason in entry.blockers)]))
        warnings = list(dict.fromkeys(risk for entry in entries for risk in entry.known_risks))
        route = tuple(
            self._stage(entry, request, blockers if entry.blockers else (), warnings if entry.known_risks else ())
            for entry in entries
        )
        profile = self._select_stage1_profile(request, entries[0])
        if profile is None:
            blockers.append("NO_COMPATIBLE_STAGE1_PROFILE")
        elif profile.classification != "EXACT_CERTIFIED" and not self._qualification_authorized(request):
            # V2.2 P0-0: production fails closed on allowed-but-uncertified
            # exact profiles; analysis reporting stays available via the route.
            blockers.append("STAGE_RUNTIME_CERTIFICATION_REQUIRED")
        status = "blocked" if blockers else ("feasible_with_warnings" if warnings else "feasible")
        support_level = "blocked" if blockers else ("historical_experimental" if any(e.support_level == "historical_experimental" for e in entries) else entries[0].support_level)
        return self._result(request, source_family, route, profile, support_level, status, tuple(blockers), tuple(warnings))

    def _select_stage1_profile(self, request, entry) -> Stage1ExecutionProfile | None:
        candidates = [
            (candidate, classification)
            for candidate in request.runtime_candidates
            if (classification := self._candidate_classification(candidate, entry)) is not None
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[1] != "EXACT_CERTIFIED", self._version_key(item[0].node_exact), item[0].profile_id))
        candidate, classification = candidates[0]
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
            "classification": classification,
        }
        stage1_checksum = "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return Stage1ExecutionProfile(
            **payload,
            source_execution_profile_checksum=request.source_execution_profile_checksum,
            stage1_profile_checksum=stage1_checksum,
            checksum=stage1_checksum,
        )

    @staticmethod
    def _candidate_classification(candidate: RuntimeCandidate, entry) -> RuntimeCompatibilityClass | None:
        node = Version.parse(candidate.node_exact)
        npm = Version.parse(candidate.npm_exact)
        npx = Version.parse(candidate.npx_exact)
        governance = bool(
            candidate.available
            and candidate.operating_system.lower() == "windows"
            and candidate.architecture.lower() == "amd64"
            and node
            and npm
            and npx
            and npx.major == npm.major
            and (candidate.angular_cli_exact is None or candidate.angular_cli_exact == (entry.cli_exact or entry.target_cli_exact))
            and candidate.registry_configured
            and candidate.certificate_valid
            and candidate.environment_allowlist_valid
            and candidate.cache_policy_valid
            and candidate.network_policy == "approved-registries-only"
        )
        if not governance:
            return None
        classification = classify_runtime_versions(
            node_exact=candidate.node_exact,
            npm_exact=candidate.npm_exact,
            npx_exact=candidate.npx_exact,
            validated_runtime_profiles=entry.validated_runtime_profiles,
            source_node_ranges=entry.source_node_ranges,
            target_node_ranges=entry.target_node_ranges,
        )
        if classification != "UNSUPPORTED":
            return classification
        # Legacy/custom catalogues without official range metadata retain their
        # prior exact constraints, but are not promoted to certified evidence.
        if not entry.source_node_ranges and node and npm and str(node) == entry.node_exact and str(npm) == entry.npm_exact:
            return "RANGE_COMPATIBLE"
        return None

    @classmethod
    def _candidate_allowed(cls, candidate: RuntimeCandidate, entry) -> bool:
        return cls._candidate_classification(candidate, entry) is not None

    @staticmethod
    def _version_key(value: str) -> tuple[int, int, int]:
        version = Version.parse(value)
        return (version.major, version.minor, version.patch) if version else (-1, -1, -1)

    def _entry_with_promoted_profiles(self, entry):
        """Augment catalogue profiles with promoted certified exact tuples."""
        if self._certified_profile_lookup is None:
            return entry
        promoted = self._certified_profile_lookup(entry.source_family, entry.target_family)
        if not promoted:
            return entry
        merged = tuple(dict.fromkeys((*entry.validated_runtime_profiles, *promoted)))
        return entry.model_copy(update={"validated_runtime_profiles": merged})

    @staticmethod
    def _qualification_authorized(request) -> bool:
        """QUALIFICATION mode proceeds only with its explicit authorization checksum."""
        return (
            getattr(request, "run_mode", "PRODUCTION") == "QUALIFICATION"
            and bool(request.qualification_authorization_checksum)
        )

    def _stage(self, entry, request, blockers, warnings):
        classifications = [
            self._candidate_classification(candidate, entry)
            for candidate in request.runtime_candidates
        ]
        classification = next((item for item in classifications if item == "EXACT_CERTIFIED"), None)
        classification = classification or next((item for item in classifications if item == "RANGE_COMPATIBLE"), None)
        return {
            "stage_id": entry.stage_id,
            "source_family": entry.source_family,
            "target_family": entry.target_family,
            "support_level": entry.support_level,
            "target_angular_exact": entry.target_angular_exact,
            "target_cli_exact": entry.target_cli_exact,
            "typescript_exact": entry.typescript_exact,
            "rxjs_exact": entry.rxjs_exact,
            "zone_js_exact": entry.zone_js_exact,
            "target_cohort": entry.target_cohort(),
            "node_exact": entry.node_exact,
            "npm_exact": entry.npm_exact,
            "blockers": tuple(blockers),
            "warnings": tuple(warnings),
            "runtime_classification": classification,
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
