"""AcceptanceHarnessService — orchestrates fixture generation, subprocess execution,
evidence collection, and result evaluation for the Angular acceptance harness.

No G01–G09 production services are duplicated. State transitions delegate to
StateTransitionService where available; idempotency is enforced through
idempotency keys and state version checks.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import (
    ArtifactRefDto,
    ArtifactType,
    CancellationPolicy,
    HarnessFixtureType,
    HarnessRequestDto,
    HarnessResultDto,
    HarnessStatusDto,
)
from app.repositories.session import session_scope
from app.services.runtime_evidence_collector import RuntimeEvidenceCollector

# Mapping of fixture types to generator functions.
# Each generator accepts (root: Path, name: str) -> Path.
FIXTURE_GENERATORS: dict[HarnessFixtureType, Callable[[Path, str], Path]] = {}


def _resolve_generator(fixture_type: HarnessFixtureType) -> Callable[[Path, str], Path]:
    """Resolve the generator function for the given fixture type."""
    if not FIXTURE_GENERATORS:
        _register_generators()
    generator = FIXTURE_GENERATORS.get(fixture_type)
    if generator is None:
        raise ValueError(f"Unknown fixture type: {fixture_type!r}")
    return generator


def _register_generators() -> None:
    """Register all fixture generator functions."""
    from tests.fixture_generators.angular_fixture import (
        create_angular_fixture,
        create_angular_fixture_180x,
        create_cancellable_fixture,
        create_compiler_error_fixture,
        create_dependency_conflict_fixture,
        create_environment_blocker_fixture,
        create_passable_fixture,
    )

    FIXTURE_GENERATORS[HarnessFixtureType.ANGULAR_180X] = create_angular_fixture_180x
    FIXTURE_GENERATORS[HarnessFixtureType.ANGULAR_182X] = create_angular_fixture
    FIXTURE_GENERATORS[HarnessFixtureType.PASSABLE] = create_passable_fixture
    FIXTURE_GENERATORS[HarnessFixtureType.COMPILER_ERROR] = create_compiler_error_fixture
    FIXTURE_GENERATORS[HarnessFixtureType.DEPENDENCY_CONFLICT] = create_dependency_conflict_fixture
    FIXTURE_GENERATORS[HarnessFixtureType.ENVIRONMENT_BLOCKER] = create_environment_blocker_fixture
    FIXTURE_GENERATORS[HarnessFixtureType.CANCELLABLE] = create_cancellable_fixture


@dataclass
class _IdempotencyRecord:
    """In-memory idempotency record for a harness fixture request."""

    result: HarnessResultDto
    state_version: int = 1


class StaleStateVersionError(ValueError):
    """Raised when an expected state version does not match the current version."""


class AcceptanceHarnessService:
    """Orchestrates the full acceptance harness lifecycle.

    Responsible for:
    - Selecting and generating fixture workspaces
    - Configuring subprocess profiles and delegating to ExecutionWorker
    - Collecting and persisting runtime evidence
    - Evaluating fixture outcomes (pass/fail)
    - Tracking idempotency and state version for request deduplication
    """

    def __init__(
        self,
        settings,
        *,
        fake_model_config: dict | None = None,
        session_scope_factory=session_scope,
        artifact_store: LocalFilesystemArtifactStore | None = None,
        evidence_collector: RuntimeEvidenceCollector | None = None,
        execution_worker: Any | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._execution_worker = execution_worker

        # Fake model gateway (Phase B contract point)
        self._fake_gateway = fake_model_config

        # In-memory fixture_id -> fixture_root mapping
        self._fixture_id_to_root: dict[str, Path] = {}

        # Lazy artifact store from settings if not provided.
        if artifact_store is None:
            root = (
                Path(settings.artifact_root)
                if settings.artifact_root
                else Path(settings.platform_repository_root) / "data" / "harness"
            )
            artifact_store = LocalFilesystemArtifactStore(root)
        self._artifact_store = artifact_store

        self._evidence_collector = evidence_collector or RuntimeEvidenceCollector(
            settings,
            artifact_store=artifact_store,
            session_scope_factory=session_scope_factory,
        )

        # In-memory idempotency tracking (will be replaced by DB-backed
        # StateTransitionService when G01–G09 integration is available).
        self._idempotency_store: dict[str, _IdempotencyRecord] = {}
        self._state_versions: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_fixture(self, request: HarnessRequestDto) -> HarnessResultDto:
        """Generate a fixture workspace and record manifest evidence.

        Returns a HarnessResultDto with the fixture root and outcome.
        Raises ValueError for unknown fixture types.
        """
        # Idempotency check
        if request.idempotency_key and request.idempotency_key in self._idempotency_store:
            record = self._idempotency_store[request.idempotency_key]
            if record.state_version == request.expected_state_version:
                return record.result
            raise StaleStateVersionError(
                f"Expected state version {request.expected_state_version}, "
                f"found {record.state_version}"
            )

        generator = _resolve_generator(request.fixture_type)
        fixture_name = request.name or f"fixture-{request.fixture_type.value}-{uuid4().hex[:8]}"

        # Create fixture under an external temp root
        fixture_root = self._fixture_root_path()
        fixture_root.mkdir(parents=True, exist_ok=True)
        created_path = generator(fixture_root, fixture_name)

        # Compute checksum of the generated workspace
        checksum = self._checksum_workspace(created_path)

        fixture_id = f"fixture-{uuid4().hex[:12]}"
        self._fixture_id_to_root[fixture_id] = created_path

        # Write fixture manifest evidence
        run_id = f"harness-run-{uuid4().hex[:12]}"
        manifest_ref = self._evidence_collector.record_fixture_manifest(
            run_id=run_id,
            fixture_type=request.fixture_type.value,
            root=str(created_path),
            checksum=checksum,
        )

        # Isolation evidence
        isolation_ref = self._evidence_collector.record_isolation_evidence(
            run_id=run_id,
            fixture_root=str(created_path),
            output_root=str(self._output_root_path()),
        )

        # Source integrity proof (T02 / AMFA-283)
        source_integrity_ref = self._evidence_collector.record_source_integrity_proof(
            run_id=run_id,
            fixture_id=fixture_id,
            source_path=str(created_path),
            checksum=checksum,
            manifest={
                "fixture_type": request.fixture_type.value,
                "generator": request.fixture_type.value,
                "file_count": len(list(created_path.rglob("*"))),
            },
        )

        result = HarnessResultDto(
            fixture_id=fixture_id,
            fixture_root=str(created_path),
            outcome="GENERATED",
            evidence_refs=[manifest_ref, isolation_ref, source_integrity_ref],
            state_version=1,
            idempotent_replay=False,
        )

        # Store for idempotency
        if request.idempotency_key:
            self._idempotency_store[request.idempotency_key] = _IdempotencyRecord(
                result=result, state_version=1
            )

        return result

    def run_subprocess_profile(
        self,
        fixture_root: str | Path,
        profile_id: str,
        *,
        arguments: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        """Run a subprocess command via the harness execution worker.

        Returns a dict with keys: status, exit_code, stdout, stderr, duration_ms.
        If no execution_worker is configured, returns a SKIPPED marker.
        """
        if self._execution_worker is None:
            return {
                "status": "SKIPPED",
                "exit_code": None,
                "stdout": "",
                "stderr": "No execution worker configured for harness",
                "duration_ms": 0,
            }

        from app.command_execution.worker import (
            CommandLogWriter,
            CommandPolicy,
            CommandRequestDto,
            ExecutionWorker,
        )
        from app.runtime_profiles.harness_profiles import (
            HARNESS_COMMAND_REGISTRY,
            HARNESS_FIXTURE_ROOT,
            HARNESS_OUTPUT_ROOT,
            HARNESS_PROFILE_ENTRIES,
            HARNESS_PROFILE_ID,
        )

        profile_entry = HARNESS_PROFILE_ENTRIES.get(profile_id)
        if profile_entry is None:
            return {
                "status": "REJECTED",
                "exit_code": None,
                "stdout": "",
                "stderr": f"Unknown harness profile: {profile_id}",
                "duration_ms": 0,
            }

        fixture_root_path = Path(fixture_root).resolve()

        policy = CommandPolicy(
            sandbox_root=fixture_root_path,
            registry=HARNESS_COMMAND_REGISTRY,
            working_directory_aliases={
                HARNESS_FIXTURE_ROOT: fixture_root_path,
                HARNESS_OUTPUT_ROOT: fixture_root_path / "dist",
            },
            runtime_profiles=frozenset({"none", HARNESS_PROFILE_ID}),
            network_profiles=frozenset({"none"}),
        )

        command_request = CommandRequestDto(
            command_id=profile_id,
            run_id=f"harness-{uuid4().hex[:12]}",
            executable=str(profile_entry["executable"]),
            arguments=list(arguments) if arguments else list(profile_entry["default_args"]),
            working_directory_alias=HARNESS_FIXTURE_ROOT,
            runtime_profile_id=HARNESS_PROFILE_ID,
            timeout_seconds=int(profile_entry["timeout_seconds"]),
            network_profile=str(profile_entry["network_profile"]),
            cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE,
            idempotency_key=f"harness-{profile_id}-{uuid4().hex[:12]}",
            requested_at=self._now(),
        )

        log_writer = CommandLogWriter(self._artifact_store)
        worker = ExecutionWorker(
            policy=policy,
            log_writer=log_writer,
        )
        result = worker.run(command_request)

        return {
            "status": result.result.status.value,
            "exit_code": result.result.exit_code,
            "stdout": result.stdout_artifact.content if result.stdout_artifact else "",
            "stderr": result.stderr_artifact.content if result.stderr_artifact else "",
            "duration_ms": result.result.duration_ms or 0,
        }

    def evaluate_fixture(self, fixture_id: str) -> HarnessResultDto:
        """Evaluate a previously generated fixture by running ng build.

        Returns a HarnessResultDto with the evaluation outcome and evidence.
        If no execution_worker is configured, returns EVALUATION_SKIPPED.
        """
        run_id = f"harness-eval-{uuid4().hex[:12]}"
        out: str = "UNKNOWN"
        evidence_refs: list[ArtifactRefDto] = []

        if self._execution_worker is not None:
            fixture_root = self._find_fixture_root(fixture_id)
            if fixture_root is None:
                return HarnessResultDto(
                    fixture_id=fixture_id,
                    fixture_root="",
                    outcome="FIXTURE_NOT_FOUND",
                    state_version=1,
                )

            # Run ng build
            build_result = self.run_subprocess_profile(
                fixture_root=fixture_root,
                profile_id="ng-build",
            )

            # Record integration evidence
            integration_ref = self._evidence_collector.record_integration_result(
                run_id=run_id,
                result=build_result,
                duration_ms=build_result.get("duration_ms", 0),
            )
            evidence_refs.append(integration_ref)

            exit_code = build_result.get("exit_code")
            build_status = build_result.get("status", "UNKNOWN")
            if exit_code == 0:
                out = "PASSED"
                # Record output fingerprint on success (T02 / AMFA-283)
                fingerprint = self._compute_output_fingerprint(fixture_root)
                fingerprint_ref = self._evidence_collector.record_output_fingerprint(
                    run_id=run_id,
                    fixture_id=fixture_id,
                    artifact_root=str(fixture_root / "dist"),
                    fingerprint_data=fingerprint,
                )
                evidence_refs.append(fingerprint_ref)
            elif build_status in ("CANCELLED", "TIMED_OUT"):
                out = build_status
                # Record cancellation evidence (T02 / AMFA-283)
                cancel_ref = self._evidence_collector.record_cancellation_evidence(
                    run_id=run_id,
                    fixture_id=fixture_id,
                    fixture_root=str(fixture_root),
                    reason=f"Subprocess {build_status.lower()} during ng build",
                    cancel_event_type=build_status,
                )
                evidence_refs.append(cancel_ref)
            elif exit_code is not None:
                out = "FAILED"
            else:
                out = "BLOCKED"
        else:
            out = "EVALUATION_SKIPPED"

        # Lightweight fake gateway integration (Phase B contract point).
        # When a gateway is configured, record a gateway evidence artifact
        # so downstream Phase B consumers can verify the integration path.
        if self._fake_gateway is not None:
            gateway_ref = self._artifact_store.write_text_artifact(
                run_id,
                "gateway/gateway_check.json",
                json.dumps(
                    {
                        "gateway_configured": True,
                        "fixture_id": fixture_id,
                        "phase": "contract_point",
                    }
                ),
                ArtifactType.JSON,
                created_by="acceptance_harness",
            )
            evidence_refs.append(
                ArtifactRefDto(
                    artifact_id=gateway_ref.ref.artifact_id,
                    run_id=run_id,
                    artifact_type=ArtifactType.JSON,
                    relative_path="gateway/gateway_check.json",
                    created_at=self._now(),
                    checksum=gateway_ref.ref.checksum,
                )
            )

        # Record proof report
        report = (
            f"# Fixture Evaluation Report\n\n"
            f"- **fixture_id**: {fixture_id}\n"
            f"- **outcome**: {out}\n"
            f"- **evidence_artifacts**: {len(evidence_refs)}\n"
        )
        proof_ref = self._evidence_collector.record_proof_report(
            run_id=run_id,
            summary=report,
        )
        evidence_refs.append(proof_ref)

        return HarnessResultDto(
            fixture_id=fixture_id,
            fixture_root="",
            outcome=out,
            evidence_refs=evidence_refs,
            state_version=1,
        )

    def run_acceptance_suite(
        self,
        requests: list[HarnessRequestDto],
    ) -> HarnessStatusDto:
        """Orchestrate a full acceptance suite: generate → subprocess → evaluate.

        Each request is processed independently. Results are aggregated into
        a HarnessStatusDto with overall success/failure.
        """
        results: list[HarnessResultDto] = []
        errors: list[str] = []
        total_start = self._now()

        for req in requests:
            try:
                gen_result = self.generate_fixture(req)
                results.append(gen_result)

                if gen_result.outcome == "GENERATED":
                    eval_result = self.evaluate_fixture(gen_result.fixture_id)
                    results.append(eval_result)
            except (ValueError, StaleStateVersionError) as exc:
                errors.append(str(exc))
                results.append(
                    HarnessResultDto(
                        fixture_id=f"fixture-err-{uuid4().hex[:8]}",
                        fixture_root="",
                        outcome="ERROR",
                        state_version=0,
                    )
                )

        total_duration = int((self._now() - total_start).total_seconds() * 1000)
        passed = sum(1 for r in results if r.outcome == "PASSED")
        failed = sum(1 for r in results if r.outcome in ("FAILED", "ERROR", "CANCELLED", "TIMED_OUT"))
        generated = sum(1 for r in results if r.outcome == "GENERATED")

        overall = "PASSED" if not failed else "FAILED"
        if not results:
            overall = "EMPTY_SUITE"

        # Record aggregate suite evidence (T02 / AMFA-283)
        suite_run_id = f"harness-suite-{uuid4().hex[:12]}"
        fixture_results_serialized = [
            {
                "fixture_id": r.fixture_id,
                "outcome": r.outcome,
                "evidence_count": len(r.evidence_refs),
            }
            for r in results
        ]
        aggregate_summary = {
            "total_fixtures": len(results),
            "passed": passed,
            "failed": failed,
            "generated": generated,
            "duration_ms": total_duration,
            "overall": overall,
            "started_at": total_start.isoformat(),
            "completed_at": self._now().isoformat(),
        }
        aggregate_ref = self._evidence_collector.record_acceptance_suite_evidence(
            run_id=suite_run_id,
            aggregate_summary=aggregate_summary,
            fixture_results=fixture_results_serialized,
        )

        return HarnessStatusDto(
            overall_status=overall,
            fixtures=results,
            errors=errors,
            evidence_summary={
                "total_fixtures": len(results),
                "passed": passed,
                "failed": failed,
                "generated": generated,
                "duration_ms": total_duration,
                "suite_evidence_id": aggregate_ref.artifact_id,
            },
        )

    def get_status(self) -> HarnessStatusDto:
        """Return the current harness status (no active suite = empty)."""
        return HarnessStatusDto(
            overall_status="READY",
            fixtures=[],
            errors=[],
            evidence_summary={"state": "idle"},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_output_fingerprint(fixture_root: Path | str) -> dict[str, object]:
        """Compute SHA-256 fingerprint of the build output directory.

        Returns a dict with fingerprint hash, file list, or a reason if the
        output directory does not exist.
        """
        root = Path(fixture_root)
        dist = root / "dist"
        if not dist.is_dir():
            return {
                "fingerprint": None,
                "reason": "output directory not found",
                "path": str(dist),
            }

        hasher = hashlib.sha256()
        files: list[dict[str, object]] = []
        for path in sorted(dist.rglob("*")):
            if path.is_file():
                rel = str(path.relative_to(dist))
                content = path.read_bytes()
                hasher.update(rel.encode("utf-8"))
                hasher.update(content)
                files.append({"path": rel, "size": len(content)})

        return {
            "fingerprint": f"sha256:{hasher.hexdigest()}",
            "file_count": len(files),
            "files": files,
        }

    def get_harness_gateway_info(self) -> dict[str, str]:
        """Return info about the configured model gateway for this harness.

        When a fake_model_config is configured (Phase B contract point),
        returns mock_gateway details. Otherwise returns a skipped marker.
        """
        if self._fake_gateway is not None:
            gw = self._fake_gateway.get("gateway") if isinstance(self._fake_gateway, dict) else None
            return {
                "provider": "mock_gateway",
                "status": "configured",
                "gateway_type": type(gw).__name__ if gw else "dict_config",
            }
        return {"provider": "none", "status": "skipped"}

    def _fixture_root_path(self) -> Path:
        """Return the base path for fixture workspace generation."""
        base = (
            Path(self._settings.workspace_root)
            if self._settings.workspace_root
            else Path("/tmp") / "amfa-harness-fixtures"
        )
        return base

    def _output_root_path(self) -> Path:
        """Return the base path for harness output artifacts."""
        base = (
            Path(self._settings.artifact_root)
            if self._settings.artifact_root
            else Path("/tmp") / "amfa-harness-output"
        )
        return base

    def _find_fixture_root(self, fixture_id: str) -> Path | None:
        """Attempt to find a fixture root by fixture_id.

        Checks the in-memory fixture_id -> fixture_root mapping first,
        then falls back to directory walk for legacy/manual fixtures.
        """
        # In-memory mapping (populated by generate_fixture)
        if fixture_id in self._fixture_id_to_root:
            return self._fixture_id_to_root[fixture_id]
        # Fallback: walk the fixture root directory
        fixture_base = self._fixture_root_path()
        if not fixture_base.exists():
            return None
        for child in sorted(fixture_base.iterdir()):
            if child.is_dir():
                return child
        return None

    @staticmethod
    def _checksum_workspace(root: Path) -> str:
        """Compute a deterministic SHA-256 checksum over the workspace contents."""
        hasher = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            if path.is_file():
                relative = path.relative_to(root)
                hasher.update(str(relative).encode("utf-8"))
                hasher.update(path.read_bytes())
        return f"sha256:{hasher.hexdigest()}"
