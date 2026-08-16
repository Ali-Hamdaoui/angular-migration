"""Persistence model for versioned retrieval benchmark reports (V2 F28-03)."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.models.base import Base


class RetrievalBenchmarkModel(Base):
    __tablename__ = "retrieval_benchmarks"
    __table_args__ = (
        UniqueConstraint("fixture_set", "version", name="uq_retrieval_benchmark_set_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    fixture_set: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    case_results: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    mean_precision: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mean_recall: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mean_f1: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    p95_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mean_budget_utilization: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    deterministic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
