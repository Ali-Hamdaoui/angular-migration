"""API contracts for the retrieval benchmark (V2 F28)."""

from datetime import datetime

from app.domain.contracts import ContractModel


class RetrievalBenchmarkCaseResultDto(ContractModel):
    case_id: str
    fixture_kind: str
    source_major: int
    retrieved_files: list[str]
    relevant_retrieved: list[str]
    precision: float
    recall: float
    f1: float
    latency_ms: float
    budget: int
    total_tokens: int
    budget_utilization: float
    truncated: bool


class RetrievalBenchmarkReportDto(ContractModel):
    benchmark_id: str
    version: int
    fixture_set: str
    case_results: list[RetrievalBenchmarkCaseResultDto]
    mean_precision: float
    mean_recall: float
    mean_f1: float
    p95_latency_ms: float
    mean_budget_utilization: float
    deterministic: bool
    ran_at: datetime
    checksum: str


class RetrievalBenchmarkListDto(ContractModel):
    benchmarks: list[RetrievalBenchmarkReportDto]


class RetrievalBenchmarkRunRequest(ContractModel):
    workspace_root: str
