"""Command execution evidence (V2.3 Phase 6).

Every executed command stores one ``CommandExecutionEvidence`` record
binding its identity, runtime profile, working directory, environment
checksum, timing, exit code, and per-stream/artifact checksums.  The record
is immutable: it is built from the durable ``CommandExecutionModel`` row and
the artifact store metadata, never from live process state.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from app.domain.contracts import ContractModel


def _checksum(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class CommandExecutionEvidence(ContractModel):
    """Immutable per-command execution evidence (V2.3 Phase 6)."""

    schema_version: str = "command-execution-evidence-v1"
    run_id: str
    stage_id: str | None = None
    command_id: str
    template_id: str
    execution_id: str
    command_execution_row_id: str
    runtime_profile: str | None = None
    cwd: str | None = None
    environment_checksum: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    exit_code: int | None = None
    stdout_checksum: str | None = None
    stderr_checksum: str | None = None
    artifact_checksum: str | None = None
    status: str | None = None
    evidence_checksum: str | None = None

    @classmethod
    def create(cls, **fields) -> "CommandExecutionEvidence":
        draft = cls(**fields)
        facts = {
            "run_id": draft.run_id,
            "stage_id": draft.stage_id,
            "command_id": draft.command_id,
            "template_id": draft.template_id,
            "execution_id": draft.execution_id,
            "command_execution_row_id": draft.command_execution_row_id,
            "runtime_profile": draft.runtime_profile,
            "cwd": draft.cwd,
            "environment_checksum": draft.environment_checksum,
            "exit_code": draft.exit_code,
            "stdout_checksum": draft.stdout_checksum,
            "stderr_checksum": draft.stderr_checksum,
            "artifact_checksum": draft.artifact_checksum,
            "status": draft.status,
        }
        return draft.model_copy(update={"evidence_checksum": _checksum(facts)})


def build_command_execution_evidence(
    *,
    execution_row,
    artifact_checksums: dict[str, str] | None = None,
) -> CommandExecutionEvidence:
    """Build one immutable evidence record from a durable execution row.

    ``artifact_checksums`` maps artifact ids (stdout/stderr/result/manifest/
    command-log) to their checksums; when absent the row's own references are
    recorded without checksums and the artifact store re-verifies on read.
    """
    started = execution_row.started_at if getattr(execution_row, "started_at", None) else None
    ended = execution_row.finished_at if getattr(execution_row, "finished_at", None) else None
    stdout_id = getattr(execution_row, "stdout_artifact_id", None)
    stderr_id = getattr(execution_row, "stderr_artifact_id", None)
    checksums = dict(artifact_checksums or {})
    artifact_ids = tuple(getattr(execution_row, "artifact_ids", None) or ())
    artifact_checksum = (
        _checksum({"artifacts": sorted(artifact_ids)})
        if artifact_ids
        else None
    )
    environment_checksum = getattr(execution_row, "runtime_checksum", None)
    return CommandExecutionEvidence.create(
        run_id=getattr(execution_row, "run_id", "") or "",
        stage_id=getattr(execution_row, "stage_id", None),
        command_id=getattr(execution_row, "command_id", None) or "",
        template_id=getattr(execution_row, "template_id", None) or "",
        execution_id=getattr(execution_row, "id", None) or "",
        command_execution_row_id=getattr(execution_row, "id", None) or "",
        runtime_profile=getattr(execution_row, "runtime_profile_id", None),
        cwd=getattr(execution_row, "safe_relative_working_directory", None),
        environment_checksum=environment_checksum,
        started_at=_as_utc(started),
        ended_at=_as_utc(ended),
        exit_code=getattr(execution_row, "exit_code", None),
        stdout_checksum=checksums.get(stdout_id) if stdout_id else None,
        stderr_checksum=checksums.get(stderr_id) if stderr_id else None,
        artifact_checksum=artifact_checksum,
        status=getattr(execution_row, "status", None),
    )


def _as_utc(value) -> datetime | None:
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)