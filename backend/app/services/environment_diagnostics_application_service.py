"""Application facade that binds environment diagnostics to durable persistence."""

from datetime import datetime, timezone
from collections.abc import Callable
from contextlib import AbstractContextManager

from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution.worker import CommandLogWriter, CommandPolicy, ExecutionWorker
from app.core.config import Settings
from app.domain.system import EnvironmentCapabilityResult, RefreshEnvironmentRequest
from app.repositories.environment_capability import EnvironmentCapabilityRepository
from app.repositories.session import session_scope
from app.services.environment_capability_service import EnvironmentCapabilityService


class EnvironmentDiagnosticsApplicationService:
    def __init__(
        self,
        settings: Settings,
        *,
        repository: EnvironmentCapabilityRepository | None = None,
        capability_service: EnvironmentCapabilityService | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
    ) -> None:
        self._settings = settings
        self._session_scope = session_scope_factory or session_scope
        self._repository = repository or EnvironmentCapabilityRepository()
        if capability_service is None:
            store = LocalFilesystemArtifactStore(settings.artifact_root)
            sandbox_root = settings.sandbox_root.resolve()
            sandbox_root.mkdir(parents=True, exist_ok=True)
            worker = ExecutionWorker(
                CommandPolicy(
                    sandbox_root=sandbox_root,
                    working_directory_aliases={"run_workspace": sandbox_root},
                ),
                CommandLogWriter(store, max_output_bytes=settings.command_max_output_bytes),
                timeout_seconds=min(settings.command_timeout_seconds, 10),
            )
            capability_service = EnvironmentCapabilityService(settings, worker, store)
        self._capability_service = capability_service

    def latest(self) -> EnvironmentCapabilityResult | None:
        with self._session_scope() as session:
            record = self._repository.get_latest(session)
            return self._repository.to_result(record) if record else None

    def refresh(self, request: RefreshEnvironmentRequest) -> EnvironmentCapabilityResult:
        with self._session_scope() as session:
            existing = self._repository.get_by_idempotency(session, request.idempotency_key)
            if existing:
                return self._repository.to_result(existing)

        result = self._capability_service.diagnose(request.idempotency_key)
        with self._session_scope() as session:
            existing = self._repository.get_by_idempotency(session, request.idempotency_key)
            if existing:
                return self._repository.to_result(existing)
            self._repository.save(
                session,
                result,
                idempotency_key=request.idempotency_key,
                actor=request.actor,
                now=datetime.now(timezone.utc),
            )
        return result
