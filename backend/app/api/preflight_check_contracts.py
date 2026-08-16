"""API contracts for preflight checks (V2 F16)."""

from datetime import datetime
from typing import Literal

from app.domain.contracts import ContractModel


class PreflightCheckResultDto(ContractModel):
    check_id: str
    name: str
    passed: bool
    blockers: list[str]
    detail: str = ""


class PreflightVerdictDto(ContractModel):
    run_id: str
    status: Literal["passed", "warnings", "blocked"]
    checks: list[PreflightCheckResultDto]
    blockers: list[str]
    checksum: str


class PreflightVerdictRecordDto(ContractModel):
    id: str
    run_id: str
    status: str
    blockers: list[str]
    checks: list[dict]
    checksum: str
    created_at: datetime


class RunPreflightRequest(ContractModel):
    source_root: str
