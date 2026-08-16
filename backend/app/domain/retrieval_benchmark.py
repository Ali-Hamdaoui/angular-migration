"""Retrieval benchmark contracts (V2 F28).

Deterministic, reproducible benchmarks over the 11 -> 21 fixture set: each
case runs the F20 code-context retrieval against a fixed workspace and
records relevance (precision/recall against ground truth), latency, and
budget utilization.  Results are persisted and versioned (F28-03).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BenchmarkFixtureKind(str, Enum):
    """The representative fixture families across majors (F28-01)."""

    COMPONENT = "component"
    SERVICE = "service"
    MODULE = "module"
    TEMPLATE = "template"


class RetrievalBenchmarkCase(_ImmutableModel):
    """One deterministic benchmark case over a fixture workspace."""

    case_id: str = Field(min_length=1)
    fixture_kind: BenchmarkFixtureKind
    source_major: int = Field(ge=11, le=21)
    symbols: tuple[str, ...] = Field(min_length=1)
    template_selectors: tuple[str, ...] = Field(default_factory=tuple)
    budget: int = Field(gt=0)
    #: Ground truth: files whose excerpts are genuinely relevant.
    relevant_files: tuple[str, ...] = Field(default_factory=tuple)


class RetrievalBenchmarkCaseResult(_ImmutableModel):
    """Precision/recall, latency, and budget utilization for one case."""

    case_id: str
    fixture_kind: str
    source_major: int
    retrieved_files: tuple[str, ...] = Field(default_factory=tuple)
    relevant_retrieved: tuple[str, ...] = Field(default_factory=tuple)
    precision: float = Field(default=0.0, ge=0.0, le=1.0)
    recall: float = Field(default=0.0, ge=0.0, le=1.0)
    f1: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    budget: int
    total_tokens: int
    budget_utilization: float = Field(default=0.0, ge=0.0, le=1.0)
    truncated: bool = False


class RetrievalBenchmarkReport(_ImmutableModel):
    """One versioned benchmark run across the fixture set."""

    benchmark_id: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    fixture_set: str = Field(min_length=1)
    case_results: tuple[RetrievalBenchmarkCaseResult, ...] = Field(default_factory=tuple)
    mean_precision: float = Field(default=0.0, ge=0.0, le=1.0)
    mean_recall: float = Field(default=0.0, ge=0.0, le=1.0)
    mean_f1: float = Field(default=0.0, ge=0.0, le=1.0)
    p95_latency_ms: float = Field(default=0.0, ge=0.0)
    mean_budget_utilization: float = Field(default=0.0, ge=0.0, le=1.0)
    deterministic: bool = True
    ran_at: datetime
    checksum: str = ""

    def bind_checksum(self) -> RetrievalBenchmarkReport:
        # The checksum covers only the deterministic evidence: per-case
        # relevance/budget, aggregated scores.  Wall-clock latency and the
        # run timestamp are recorded but excluded so identical retrieval
        # produces identical checksums across runs.
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        canonical.pop("ran_at", None)
        canonical.pop("benchmark_id", None)
        canonical.pop("p95_latency_ms", None)
        for case in canonical.get("case_results", []):
            case.pop("latency_ms", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})
