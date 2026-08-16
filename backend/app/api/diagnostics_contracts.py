"""API contracts for failure diagnostic packs (V2 F03)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.domain.contracts import ContractModel


class PlatformFaultDto(ContractModel):
    fault_code: str
    category: Literal["environment", "command", "dependency", "workflow", "state", "transport", "llm", "policy", "unknown"]
    severity: Literal["info", "warning", "error", "critical"]
    message: str
    remediation: str | None = None
    correlation_id: str | None = None
    occurred_at: datetime
    context: dict[str, Any] = Field(default_factory=dict)


class WorkflowFailureContextDto(ContractModel):
    run_id: str | None = None
    stage_id: str | None = None
    step_id: str | None = None
    execution_id: str | None = None
    command_id: str | None = None
    state_version: int | None = None
    event_sequence: int | None = None
    workflow_node: str | None = None
    phase: str | None = None


class CommandFailureEvidenceDto(ContractModel):
    command: list[str] = Field(default_factory=list)
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    working_directory_alias: str | None = None
    runtime_profile_id: str | None = None
    timeout_seconds: int | None = None
    cancelled: bool = False
    timed_out: bool = False


class FailureDiagnosticPackDto(ContractModel):
    pack_id: str
    correlation_id: str | None = None
    fault: PlatformFaultDto
    workflow_context: WorkflowFailureContextDto = Field(default_factory=WorkflowFailureContextDto)
    command_evidence: CommandFailureEvidenceDto | None = None
    sanitized_traceback: str = ""
    created_at: datetime
    checksum: str = ""


class FailureDiagnosticPackListDto(ContractModel):
    packs: list[FailureDiagnosticPackDto]
