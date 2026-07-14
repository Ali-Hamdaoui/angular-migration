"""Application facade for durable deterministic source analysis."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timezone

from app.core.config import Settings
from app.domain.source_analysis import SourceAnalysisRequest, SourceAnalysisResult
from app.repositories.session import session_scope
from app.repositories.source_analysis import SourceAnalysisRepository
from app.services.source_analysis_service import SourceAnalysisService


class SourceAnalysisApplicationService:
    def __init__(self, settings: Settings, *, analyzer: SourceAnalysisService | None = None, repository: SourceAnalysisRepository | None = None, session_scope_factory: Callable[[], AbstractContextManager] | None = None) -> None:
        self._analyzer = analyzer or SourceAnalysisService()
        self._repository = repository or SourceAnalysisRepository()
        self._session_scope = session_scope_factory or session_scope

    def analyze(self, request: SourceAnalysisRequest) -> SourceAnalysisResult:
        with self._session_scope() as session:
            existing = self._repository.get_by_idempotency(session, request.idempotency_key)
            if existing:
                return self._repository.to_result(existing)
        result = self._analyzer.analyze(request)
        with self._session_scope() as session:
            existing = self._repository.get_by_idempotency(session, request.idempotency_key)
            if existing:
                return self._repository.to_result(existing)
            self._repository.save(session, result, key=request.idempotency_key, actor=request.actor, now=datetime.now(timezone.utc))
        return result

    def get(self, analysis_id: str) -> SourceAnalysisResult | None:
        with self._session_scope() as session:
            record = self._repository.get_by_id(session, analysis_id)
            return self._repository.to_result(record) if record else None