"""Application facade binding the runtime resolver authority to durable state (V2 F01-02/04)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from uuid import uuid4

from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution.worker import CommandLogWriter, CommandPolicy, ExecutionWorker
from app.core.config import Settings
from app.domain.contracts import CommandRequestDto, CommandStatus
from app.domain.runtime_execution import (
    RuntimeExecutableDescriptor,
    RuntimeRequirement,
    RuntimeRequirementBinding,
)
from app.repositories.models import RuntimeExecutionEvidenceModel
from app.repositories.session import session_scope
from app.services.runtime_resolver_authority import (
    RuntimeMatrix,
    RuntimeResolverAuthority,
    VersionProbe,
)


class RuntimeResolutionError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class RuntimeResolutionApplicationService:
    """Resolve runtime requirements and persist runtime execution evidence."""

    def __init__(
        self,
        settings: Settings,
        *,
        authority: RuntimeResolverAuthority | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        if authority is None:
            matrix = RuntimeMatrix(
                node_install_root=settings.runtime_node_install_root.expanduser().resolve(),
                angular_cli_root=settings.runtime_angular_cli_root.expanduser().resolve(),
            )
            authority = RuntimeResolverAuthority(
                matrix, probe=_build_worker_version_probe(settings, matrix), now_provider=self._now_provider
            )
        self._authority = authority

    def discover(self) -> list[RuntimeExecutableDescriptor]:
        return self._authority.discover()

    def resolve(self, requirements: list[RuntimeRequirement]) -> list[RuntimeRequirementBinding]:
        if not requirements:
            raise RuntimeResolutionError("EMPTY_REQUIREMENTS", "At least one runtime requirement is required.")
        return self._authority.resolve(requirements)

    def record_evidence(
        self,
        run_id: str,
        bindings: list[RuntimeRequirementBinding],
        *,
        execution_id: str | None = None,
        actor: str | None = None,
    ) -> list[RuntimeExecutionEvidenceModel]:
        """Persist resolved bindings as immutable runtime execution evidence."""
        if not run_id.strip():
            raise RuntimeResolutionError("RUN_ID_REQUIRED", "run_id is required.")
        now = self._now_provider()
        records: list[RuntimeExecutionEvidenceModel] = []
        with self._session_scope() as session:
            for binding in bindings:
                descriptor = binding.descriptor
                if descriptor is None:
                    continue
                evidence_id = _evidence_id(run_id, binding.requirement.runtime_id, binding.requirement.kind.value)
                existing = session.get(RuntimeExecutionEvidenceModel, evidence_id)
                if existing is not None:
                    records.append(existing)
                    continue
                idempotency_key = f"{binding.requirement.runtime_id}:{descriptor.sha256}"
                record = RuntimeExecutionEvidenceModel(
                    id=evidence_id,
                    run_id=run_id,
                    execution_id=execution_id,
                    idempotency_key=idempotency_key,
                    kind=descriptor.kind.value,
                    executable_name=descriptor.executable_name,
                    resolved_path=descriptor.resolved_path,
                    version_exact=descriptor.version_exact,
                    sha256=descriptor.sha256,
                    operating_system=descriptor.operating_system,
                    architecture=descriptor.architecture,
                    installation_root=descriptor.installation_root,
                    source=descriptor.source,
                    runtime_id=descriptor.runtime_id,
                    created_at=now,
                )
                session.add(record)
                records.append(record)
            session.commit()
            for record in records:
                session.refresh(record)
        return records

    def list_evidence(self, run_id: str) -> list[RuntimeExecutableDescriptor]:
        from sqlalchemy import select

        with self._session_scope() as session:
            rows = session.scalars(
                select(RuntimeExecutionEvidenceModel).where(RuntimeExecutionEvidenceModel.run_id == run_id)
            ).all()
            return [descriptor_from_model(row) for row in rows]


def _evidence_id(run_id: str, runtime_id: str, kind: str) -> str:
    import hashlib

    return "rev-" + hashlib.sha256(f"{run_id}:{runtime_id}:{kind}".encode()).hexdigest()[:24]


def descriptor_from_model(row: RuntimeExecutionEvidenceModel) -> RuntimeExecutableDescriptor:
    """Project a persisted evidence row back into its domain descriptor."""
    from app.domain.runtime_execution import RuntimeExecutableKind

    return RuntimeExecutableDescriptor(
        kind=RuntimeExecutableKind(row.kind),
        executable_name=row.executable_name,
        resolved_path=row.resolved_path,
        version_exact=row.version_exact,
        sha256=row.sha256,
        operating_system=row.operating_system,
        architecture=row.architecture,
        installation_root=row.installation_root,
        source=row.source,
        runtime_id=row.runtime_id,
        probed_at=row.created_at,
    )


def _build_worker_version_probe(settings: Settings, matrix: RuntimeMatrix) -> VersionProbe:
    """Return a version probe that runs ``<path> --version`` through the command worker.

    PATH is overridden with the executable's bin directory so npm/npx shebangs
    resolve to the same node runtime being probed (PATH-independent binding).
    """
    store = LocalFilesystemArtifactStore(settings.artifact_root)
    sandbox_root = settings.sandbox_root.resolve()
    sandbox_root.mkdir(parents=True, exist_ok=True)
    worker = ExecutionWorker(
        CommandPolicy(
            sandbox_root=sandbox_root,
            working_directory_aliases={"run_workspace": sandbox_root},
            runtime_probe_roots=matrix.probe_roots,
            environment_overrides={},
        ),
        CommandLogWriter(store, max_output_bytes=settings.command_max_output_bytes),
        timeout_seconds=min(settings.command_timeout_seconds, 10),
    )
    cache: dict[tuple[str, int, int], str | None] = {}

    def probe(path) -> str | None:
        from pathlib import Path

        resolved = Path(path).resolve()
        try:
            stat = resolved.stat()
        except OSError:
            return None
        key = (str(resolved), stat.st_mtime_ns, stat.st_size)
        if key in cache:
            return cache[key]
        run_id = f"runtime-resolve-{uuid4().hex[:12]}"
        import os

        bin_dir = str(resolved.parent)
        request = CommandRequestDto(
            command_id="runtime-executable-probe",
            run_id=run_id,
            requester="runtime-resolver-authority",
            executable=str(resolved),
            arguments=["--version"],
            working_directory_alias="run_workspace",
            runtime_profile_id="source-runtime-profile",
            timeout_seconds=10,
            network_profile="none",
            idempotency_key=f"probe:{resolved}",
            requested_at=datetime.now(UTC),
            environment_overrides={"PATH": os.pathsep.join([bin_dir, os.environ.get("PATH", "")])},
        )
        result = worker.run(request)
        version: str | None = None
        if result.result.status is CommandStatus.SUCCEEDED and result.stdout_artifact is not None:
            content = result.stdout_artifact.content.strip()
            if content:
                version = content.splitlines()[0]
        cache[key] = version
        return version

    return probe
