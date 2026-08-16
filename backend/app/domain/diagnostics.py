"""Typed platform fault and failure diagnostic pack contracts (V2 F03).

A ``PlatformFault`` is the typed, stable form of a backend failure.  A
``FailureDiagnosticPack`` freezes the fault together with the workflow context
and command evidence that make it debuggable, all bound by correlation IDs.

This module has no process, filesystem, database, or network side effects.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlatformFaultSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class PlatformFaultCategory(str, Enum):
    ENVIRONMENT = "environment"
    COMMAND = "command"
    DEPENDENCY = "dependency"
    WORKFLOW = "workflow"
    STATE = "state"
    TRANSPORT = "transport"
    LLM = "llm"
    POLICY = "policy"
    UNKNOWN = "unknown"


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PlatformFault(_ImmutableModel):
    """Stable, typed representation of one backend failure."""

    fault_code: str = Field(min_length=1, max_length=128)
    category: PlatformFaultCategory = PlatformFaultCategory.UNKNOWN
    severity: PlatformFaultSeverity = PlatformFaultSeverity.ERROR
    message: str = Field(min_length=1, max_length=4096)
    remediation: str | None = None
    correlation_id: str | None = None
    occurred_at: datetime
    context: dict[str, Any] = Field(default_factory=dict)


class WorkflowFailureContext(_ImmutableModel):
    """The workflow state around a failure: where it happened, in what run."""

    run_id: str | None = None
    stage_id: str | None = None
    step_id: str | None = None
    execution_id: str | None = None
    command_id: str | None = None
    state_version: int | None = None
    event_sequence: int | None = None
    workflow_node: str | None = None
    phase: str | None = None


class CommandFailureEvidence(_ImmutableModel):
    """The exact command and its bounded outputs at failure time."""

    command: tuple[str, ...] = ()
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    working_directory_alias: str | None = None
    runtime_profile_id: str | None = None
    timeout_seconds: int | None = None
    cancelled: bool = False
    timed_out: bool = False


class FailureDiagnosticPack(_ImmutableModel):
    """Immutable diagnostic pack: fault + context + evidence, checksum-bound."""

    pack_id: str = Field(min_length=1)
    correlation_id: str | None = None
    fault: PlatformFault
    workflow_context: WorkflowFailureContext = Field(default_factory=WorkflowFailureContext)
    command_evidence: CommandFailureEvidence | None = None
    sanitized_traceback: str = ""
    created_at: datetime
    checksum: str = ""

    def bind_checksum(self) -> FailureDiagnosticPack:
        """Compute the immutable checksum over the pack's serialized content."""
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(
            __import__("json").dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


def pack_checksum(pack: FailureDiagnosticPack) -> str:
    return pack.checksum or pack.bind_checksum().checksum


def now_utc() -> datetime:
    return datetime.now(UTC)
