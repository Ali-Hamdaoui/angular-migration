"""Failure diagnostics service: sanitization, classification, pack assembly (V2 F03)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.domain.diagnostics import (
    CommandFailureEvidence,
    FailureDiagnosticPack,
    PlatformFault,
    PlatformFaultCategory,
    PlatformFaultSeverity,
    WorkflowFailureContext,
)
from app.llm_gateway.redaction import redact_prompt_text

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_TRACEBACK_MAX_CHARS = 16_000
_SECRET_ASSIGNMENT = re.compile(
    r"^(\s*)([A-Za-z0-9_]{2,}(?:SECRET|TOKEN|PASSWORD|PASSWD|API[_-]?KEY|PRIVATE[_-]?KEY)"
    r"|[A-Za-z0-9_]*AZURE_OPENAI_[A-Z0-9_]+)\s*[:=]\s*([A-Za-z0-9._~+/=-]{8,})"
)
_SENTINEL_PATTERNS: tuple[str, ...] = (
    "ghp_", "gho_", "sk-", "xoxb-", "AKIA", "A43W", "Bearer ",
)


def sanitize_traceback(traceback_text: str | None) -> str:
    """Make a traceback safe to persist and share.

    - strips ANSI escapes
    - redacts secret assignments and sentinel-prefixed values line by line
      (bounded work per line, no catastrophic backtracking)
    - removes Python memory addresses
    - bounds the length
    """
    if not traceback_text:
        return ""
    text = _ANSI_ESCAPE.sub("", traceback_text)
    lines = text.splitlines()
    cleaned_lines: list[str] = []
    for line in lines:
        match = _SECRET_ASSIGNMENT.match(line)
        if match:
            line = f"{match.group(1)}{match.group(2)}=[REDACTED]"
        redacted = redact_prompt_text(line).redacted_text
        for sentinel in _SENTINEL_PATTERNS:
            redacted = re.sub(
                re.escape(sentinel) + r"[A-Za-z0-9._~+/=\-]{8,}",
                f"{sentinel}[REDACTED]",
                redacted,
            )
        redacted = re.sub(r"0x[0-9a-fA-F]{6,}", "0x[ADDR]", redacted)
        cleaned_lines.append(redacted)
    result = "\n".join(cleaned_lines)
    if len(result) > _TRACEBACK_MAX_CHARS:
        result = result[: _TRACEBACK_MAX_CHARS] + "\n[diagnostic traceback truncated]"
    return result


def _category_for_code(fault_code: str) -> PlatformFaultCategory:
    code = (fault_code or "").upper()
    if any(token in code for token in ("LLM", "AZURE", "GATEWAY", "PROVIDER", "TRANSPORT", "NETWORK")):
        return PlatformFaultCategory.LLM
    if any(token in code for token in ("STATE", "TRANSITION", "LEASE", "IDEMPOTENCY")):
        return PlatformFaultCategory.STATE
    if any(token in code for token in ("POLICY", "FORBIDDEN", "VIOLATION", "DENIED", "AUTHORIZATION")):
        return PlatformFaultCategory.POLICY
    if any(token in code for token in ("ENV", "PATH", "PROFILE", "WORKSPACE", "SANDBOX", "STORE")):
        return PlatformFaultCategory.ENVIRONMENT
    if any(token in code for token in ("DEPENDENCY", "NPM", "NODE", "VERSION", "REGISTRY")):
        return PlatformFaultCategory.DEPENDENCY
    if any(token in code for token in ("COMMAND", "EXECUTION", "WORKER", "TIMEOUT", "CANCEL")):
        return PlatformFaultCategory.COMMAND
    if any(token in code for token in ("WORKFLOW", "STAGE", "PLAN", "GRAPH", "NODE")):
        return PlatformFaultCategory.WORKFLOW
    return PlatformFaultCategory.UNKNOWN


def _severity_for_code(fault_code: str) -> PlatformFaultSeverity:
    code = (fault_code or "").upper()
    if any(token in code for token in ("DENIED", "VIOLATION", "FORBIDDEN", "CRITICAL", "MISMATCH", "CORRUPT")):
        return PlatformFaultSeverity.CRITICAL
    return PlatformFaultSeverity.ERROR


def classify_failure(error: Exception) -> PlatformFault:
    """Derive a typed PlatformFault from any backend exception."""
    fault_code = getattr(error, "code", None) or type(error).__name__
    message = getattr(error, "message", None) or str(error) or type(error).__name__
    remediation = getattr(error, "remediation", None)
    context = dict(getattr(error, "details", None) or {})
    return PlatformFault(
        fault_code=fault_code,
        category=_category_for_code(fault_code),
        severity=_severity_for_code(fault_code),
        message=message[:4096],
        remediation=remediation,
        occurred_at=datetime.now(UTC),
        context=context,
    )


def build_diagnostic_pack(
    *,
    fault: PlatformFault,
    workflow_context: WorkflowFailureContext | None = None,
    command_evidence: CommandFailureEvidence | None = None,
    sanitized_traceback: str = "",
    correlation_id: str | None = None,
    pack_id: str | None = None,
    created_at: datetime | None = None,
) -> FailureDiagnosticPack:
    """Assemble an immutable, checksum-bound diagnostic pack."""
    from uuid import uuid4

    now = created_at or datetime.now(UTC)
    effective_correlation = correlation_id or fault.correlation_id
    pack = FailureDiagnosticPack(
        pack_id=pack_id or f"diag-{uuid4().hex[:20]}",
        correlation_id=effective_correlation,
        fault=fault,
        workflow_context=workflow_context or WorkflowFailureContext(),
        command_evidence=command_evidence,
        sanitized_traceback=sanitize_traceback(sanitized_traceback),
        created_at=now,
    )
    return pack.bind_checksum()


def bounded_command_output(text: str | None, *, max_bytes: int = 200_000) -> str:
    """Bound command stdout/stderr for diagnostic pack persistence."""
    if not text:
        return ""
    if len(text.encode("utf-8")) <= max_bytes:
        return _ANSI_ESCAPE.sub("", text)
    bounded = text.encode("utf-8")[:max_bytes].decode("utf-8", errors="replace")
    return _ANSI_ESCAPE.sub("", bounded) + "\n[command output truncated]"


def evidence_from_dict(payload: dict[str, Any]) -> CommandFailureEvidence:
    """Project a diagnostic evidence dict back into the immutable model."""
    return CommandFailureEvidence(
        command=tuple(payload.get("command") or ()),
        exit_code=payload.get("exit_code"),
        stdout=payload.get("stdout") or "",
        stderr=payload.get("stderr") or "",
        working_directory_alias=payload.get("working_directory_alias"),
        runtime_profile_id=payload.get("runtime_profile_id"),
        timeout_seconds=payload.get("timeout_seconds"),
        cancelled=bool(payload.get("cancelled")),
        timed_out=bool(payload.get("timed_out")),
    )


def context_from_dict(payload: dict[str, Any]) -> WorkflowFailureContext:
    return WorkflowFailureContext(
        run_id=payload.get("run_id"),
        stage_id=payload.get("stage_id"),
        step_id=payload.get("step_id"),
        execution_id=payload.get("execution_id"),
        command_id=payload.get("command_id"),
        state_version=payload.get("state_version"),
        event_sequence=payload.get("event_sequence"),
        workflow_node=payload.get("workflow_node"),
        phase=payload.get("phase"),
    )
