"""Domain contracts for FailureEvidence — deterministic failure diagnostics capture."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from app.domain.contracts import ArtifactRefDto, ContractModel


class FailureStatus(str, Enum):
    """Lifecycle status of a FailureEvidence record."""

    FINALIZED = "finalized"
    INVALID = "invalid"
    STALE = "stale"


class FailureOrigin(str, Enum):
    """Classification of where a failure originated relative to the migration."""

    PRE_EXISTING_UNCHANGED = "pre_existing_unchanged"
    PRE_EXISTING_CHANGED = "pre_existing_changed"
    MIGRATION_CAUSED = "migration_caused"
    RESOLVED_PRE_EXISTING = "resolved_pre_existing"
    UNKNOWN_ORIGIN = "unknown_origin"


class FailureRoute(str, Enum):
    """C-Lite classification route for failure diagnostics.

    Maps a failure to the type of repair or action that should be taken.
    """

    CODE_OR_CONFIG_REPAIR = "CODE_OR_CONFIG_REPAIR"
    DEPENDENCY_REPAIR = "DEPENDENCY_REPAIR"
    ENVIRONMENT_OR_USER_ACTION = "ENVIRONMENT_OR_USER_ACTION"
    RETRYABLE_EXTERNAL_FAILURE = "RETRYABLE_EXTERNAL_FAILURE"
    UNKNOWN_DIAGNOSIS = "UNKNOWN_DIAGNOSIS"


class DiagnosticParserType(str, Enum):
    """Recognised diagnostic parser kinds for structured failure extraction."""

    NPM = "npm"
    ANGULAR_CLI = "angular_cli"
    TYPESCRIPT = "typescript"
    TEMPLATE = "template"
    TEST = "test"
    GENERIC = "generic"


class FailureDiagnostic(ContractModel):
    """A single, normalised diagnostic extracted from raw command output."""

    message: str = Field(min_length=1, max_length=4000)
    code: str | None = Field(default=None, max_length=128)
    file_path: str | None = Field(default=None, max_length=1024)
    line_number: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=1)
    severity: str = Field(default="error", pattern=r"^(error|warning|info)$")
    parser_type: DiagnosticParserType
    parser_confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class DiagnosticParserResult(ContractModel):
    """Output of one diagnostic parser run against raw command output."""

    parser_type: DiagnosticParserType
    confidence: float = Field(ge=0.0, le=1.0)
    diagnostics: list[FailureDiagnostic] = Field(default_factory=list)
    raw_excerpt: str | None = Field(default=None, max_length=8000)
    line_number: int | None = Field(default=None, ge=1)
    file_path: str | None = Field(default=None, max_length=1024)


class ParserRegistry(dict[DiagnosticParserType, Callable[[str], DiagnosticParserResult]]):
    """A dictionary mapping parser types to their parse callables.

    Each callable accepts raw stdout/stderr text and returns a
    DiagnosticParserResult with zero or more FailureDiagnostic items.
    """

    def register(self, parser_type: DiagnosticParserType, parser_fn: Callable[[str], DiagnosticParserResult]) -> None:
        """Register a single parser under its type key."""
        self[parser_type] = parser_fn

    def parse_all(self, raw_output: str) -> list[DiagnosticParserResult]:
        """Run all registered parsers against *raw_output* and return results."""
        results: list[DiagnosticParserResult] = []
        for parser_type, parser_fn in self.items():
            try:
                result = parser_fn(raw_output)
                results.append(result)
            except Exception:
                results.append(
                    DiagnosticParserResult(
                        parser_type=parser_type,
                        confidence=0.0,
                        diagnostics=[],
                        raw_excerpt=None,
                    )
                )
        return results


class FailureBuilderInput(ContractModel):
    """Input for constructing FailureEvidence from a command execution result."""

    run_id: str = Field(min_length=1, max_length=64)
    stage_id: str = Field(min_length=1, max_length=64)
    execution_id: str = Field(min_length=1, max_length=128)
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    workspace_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=128)
    baseline_artifact_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_exit_code_or_output(self) -> FailureBuilderInput:
        if self.exit_code is None and not self.stdout and not self.stderr:
            raise ValueError("At least one of exit_code, stdout, or stderr must be provided")
        return self


class FailureEvidence(ContractModel):
    """Immutable failure evidence record produced by the builder service."""

    failure_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=64)
    stage_id: str = Field(min_length=1, max_length=64)
    execution_id: str = Field(min_length=1, max_length=128)
    failure_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    origin: FailureOrigin
    diagnostics: list[FailureDiagnostic] = Field(min_length=1)
    workspace_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    status: FailureStatus
    raw_log_artifacts: list[ArtifactRefDto] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_status_origin_rules(self) -> FailureEvidence:
        if self.status == FailureStatus.STALE and self.origin == FailureOrigin.MIGRATION_CAUSED:
            raise ValueError("A stale failure cannot be classified as migration_caused")
        return self


class FailureFingerprintService:
    """Compute a deterministic sha256 fingerprint from diagnostic content."""

    @staticmethod
    def compute(diagnostics: list[FailureDiagnostic]) -> str:
        """Return a sha256: fingerprint over serialised diagnostic content."""
        raw = json.dumps(
            [d.model_dump(mode="json") for d in diagnostics],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return "sha256:" + hashlib.sha256(raw).hexdigest()


class OriginComparator:
    """Compare current diagnostics against baseline to determine FailureOrigin."""

    def __init__(self, baseline_diagnostics_reader: Callable[[str], list[FailureDiagnostic]] | None = None) -> None:
        self._baseline_reader = baseline_diagnostics_reader or self._noop_baseline_reader

    @staticmethod
    def _noop_baseline_reader(_artifact_id: str) -> list[FailureDiagnostic]:
        return []

    def compare(
        self,
        current: list[FailureDiagnostic],
        baseline_artifact_ids: list[str],
    ) -> FailureOrigin:
        """Compare current diagnostics against baseline reference artifacts.

        Returns the most appropriate origin classification based on whether
        baseline diagnostics exist and how they relate to current ones.
        """
        if not baseline_artifact_ids:
            return FailureOrigin.MIGRATION_CAUSED

        baseline_diagnostics: list[FailureDiagnostic] = []
        for artifact_id in baseline_artifact_ids:
            try:
                baseline_diagnostics.extend(self._baseline_reader(artifact_id))
            except Exception:
                continue

        if not baseline_diagnostics:
            return FailureOrigin.MIGRATION_CAUSED

        current_messages = {d.message for d in current}
        baseline_messages = {d.message for d in baseline_diagnostics}

        if not current_messages and not baseline_messages:
            return FailureOrigin.UNKNOWN_ORIGIN

        # All current failures also exist in baseline → unchanged
        if current_messages and current_messages.issubset(baseline_messages):
            return FailureOrigin.PRE_EXISTING_UNCHANGED

        intersection = current_messages & baseline_messages
        new_failures = current_messages - baseline_messages
        resolved = baseline_messages - current_messages

        if intersection and new_failures:
            return FailureOrigin.PRE_EXISTING_CHANGED

        if resolved and not new_failures and not intersection:
            return FailureOrigin.RESOLVED_PRE_EXISTING

        if new_failures and not resolved and not intersection:
            return FailureOrigin.MIGRATION_CAUSED

        return FailureOrigin.UNKNOWN_ORIGIN
