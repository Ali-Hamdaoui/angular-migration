"""Persistence access for deterministic source-analysis snapshots."""

from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.source_analysis import SourceAnalysisResult
from app.repositories.models import SourceAnalysisModel


class SourceAnalysisRepository:
    def get_by_idempotency(self, session: Session, key: str) -> SourceAnalysisModel | None:
        return session.scalar(select(SourceAnalysisModel).where(SourceAnalysisModel.idempotency_key == key))

    def get_by_id(self, session: Session, analysis_id: str) -> SourceAnalysisModel | None:
        return session.get(SourceAnalysisModel, analysis_id)

    def save(self, session: Session, result: SourceAnalysisResult, *, key: str, actor: str | None, now: datetime) -> SourceAnalysisModel:
        snapshot = result.snapshot
        record = SourceAnalysisModel(
            id=snapshot.analysis_id,
            idempotency_key=key,
            actor=actor,
            status=snapshot.status,
            source_path=snapshot.source_path,
            policy_version=snapshot.policy_version,
            checksum=snapshot.checksum,
            snapshot=snapshot.model_dump(mode="json"),
            created_at=now,
        )
        session.add(record)
        session.flush()
        return record

    @staticmethod
    def to_result(record: SourceAnalysisModel) -> SourceAnalysisResult:
        from app.domain.source_analysis import SourceAnalysisSnapshot
        return SourceAnalysisResult(snapshot=SourceAnalysisSnapshot.model_validate(record.snapshot))