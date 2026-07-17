"""Application facade for durable path validation results."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timezone

from app.core.config import Settings
from app.domain.path_validation import PathValidationRequest, PathValidationResult
from app.repositories.path_validation import PathValidationRepository
from app.repositories.session import session_scope
from app.services.path_validation_service import PathValidationService


class PathValidationApplicationService:
    def __init__(
        self,
        settings: Settings,
        *,
        validator: PathValidationService | None = None,
        repository: PathValidationRepository | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
    ) -> None:
        self._validator = validator or PathValidationService(settings)
        self._repository = repository or PathValidationRepository()
        self._session_scope = session_scope_factory or session_scope

    def validate(self, request: PathValidationRequest) -> PathValidationResult:
        with self._session_scope() as session:
            existing = self._repository.get_by_idempotency(session, request.idempotency_key)
            if existing:
                return self._repository.to_result(existing)
        result = self._validator.validate(request)
        with self._session_scope() as session:
            existing = self._repository.get_by_idempotency(session, request.idempotency_key)
            if existing:
                return self._repository.to_result(existing)
            record = self._repository.save(
                session,
                result,
                key=request.idempotency_key,
                actor=request.actor,
                now=datetime.now(timezone.utc),
            )
            persisted = self._repository.to_result(record)
        return persisted

    def get(self, validation_id: str) -> PathValidationResult | None:
        with self._session_scope() as session:
            record = self._repository.get_by_id(session, validation_id)
            return self._repository.to_result(record) if record else None