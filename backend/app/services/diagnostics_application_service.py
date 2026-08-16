"""Application facade for persisting and retrieving failure diagnostic packs (V2 F03)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.domain.diagnostics import (
    CommandFailureEvidence,
    FailureDiagnosticPack,
    PlatformFault,
    WorkflowFailureContext,
)
from app.repositories.models import FailureDiagnosticPackModel
from app.repositories.session import session_scope
from app.services.diagnostics_service import (
    bounded_command_output,
    build_diagnostic_pack,
    classify_failure,
    context_from_dict,
    evidence_from_dict,
)


class DiagnosticsApplicationService:
    """Persist diagnostic packs and expose typed retrieval."""

    def __init__(
        self,
        *,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def record_command_failure(
        self,
        *,
        run_id: str,
        execution_id: str | None,
        correlation_id: str | None,
        error: Exception | None = None,
        fault: PlatformFault | None = None,
        command: tuple[str, ...] = (),
        exit_code: int | None = None,
        stdout: str = "",
        stderr: str = "",
        working_directory_alias: str | None = None,
        runtime_profile_id: str | None = None,
        timeout_seconds: int | None = None,
        cancelled: bool = False,
        timed_out: bool = False,
        traceback_text: str | None = None,
        stage_id: str | None = None,
        command_id: str | None = None,
        state_version: int | None = None,
        event_sequence: int | None = None,
        workflow_node: str | None = None,
        phase: str | None = None,
        remediation: str | None = None,
        fault_code_override: str | None = None,
    ) -> FailureDiagnosticPack | None:
        """Build and persist a diagnostic pack for a command failure."""
        if fault is None:
            if error is not None:
                fault = classify_failure(error)
                if fault_code_override:
                    fault = fault.model_copy(update={"fault_code": fault_code_override})
                if remediation:
                    fault = fault.model_copy(update={"remediation": remediation})
            else:
                fault = PlatformFault(
                    fault_code=fault_code_override or "UNKNOWN_FAILURE",
                    message=(stderr or stdout or "Backend failure")[:4096],
                    occurred_at=self._now_provider(),
                )
        if correlation_id:
            fault = fault.model_copy(update={"correlation_id": correlation_id})
        workflow_context = WorkflowFailureContext(
            run_id=run_id,
            stage_id=stage_id,
            execution_id=execution_id,
            command_id=command_id,
            state_version=state_version,
            event_sequence=event_sequence,
            workflow_node=workflow_node,
            phase=phase,
        )
        command_evidence = CommandFailureEvidence(
            command=tuple(command),
            exit_code=exit_code,
            stdout=bounded_command_output(stdout),
            stderr=bounded_command_output(stderr),
            working_directory_alias=working_directory_alias,
            runtime_profile_id=runtime_profile_id,
            timeout_seconds=timeout_seconds,
            cancelled=cancelled,
            timed_out=timed_out,
        )
        pack = build_diagnostic_pack(
            fault=fault,
            workflow_context=workflow_context,
            command_evidence=command_evidence,
            sanitized_traceback=traceback_text or "",
            correlation_id=correlation_id,
            created_at=self._now_provider(),
        )
        return self._record_pack(pack, run_id=run_id, execution_id=execution_id)

    def _record_pack(self, pack: FailureDiagnosticPack, *, run_id: str, execution_id: str | None) -> FailureDiagnosticPack:
        with self._session_scope() as session:
            existing = session.get(FailureDiagnosticPackModel, pack.pack_id)
            if existing is not None:
                return self._pack_from_model(existing)
            model = FailureDiagnosticPackModel(
                id=pack.pack_id,
                run_id=run_id,
                execution_id=execution_id,
                correlation_id=pack.correlation_id,
                fault_code=pack.fault.fault_code,
                category=pack.fault.category.value,
                severity=pack.fault.severity.value,
                message=pack.fault.message,
                remediation=pack.fault.remediation,
                workflow_context=pack.workflow_context.model_dump(mode="json"),
                command_evidence=pack.command_evidence.model_dump(mode="json") if pack.command_evidence else None,
                sanitized_traceback=pack.sanitized_traceback,
                checksum=pack.checksum,
                state_version=1,
                created_at=pack.created_at,
            )
            session.add(model)
            session.commit()
            return pack

    def get_pack(self, pack_id: str) -> FailureDiagnosticPack | None:
        with self._session_scope() as session:
            model = session.get(FailureDiagnosticPackModel, pack_id)
            return self._pack_from_model(model) if model else None

    def list_packs(self, run_id: str) -> list[FailureDiagnosticPack]:
        with self._session_scope() as session:
            models = session.scalars(
                select(FailureDiagnosticPackModel)
                .where(FailureDiagnosticPackModel.run_id == run_id)
                .order_by(FailureDiagnosticPackModel.created_at.desc())
            ).all()
            return [self._pack_from_model(model) for model in models]

    def packs_for_execution(self, execution_id: str) -> list[FailureDiagnosticPack]:
        with self._session_scope() as session:
            models = session.scalars(
                select(FailureDiagnosticPackModel)
                .where(FailureDiagnosticPackModel.execution_id == execution_id)
                .order_by(FailureDiagnosticPackModel.created_at.desc())
            ).all()
            return [self._pack_from_model(model) for model in models]

    def latest_for_run(self, run_id: str) -> FailureDiagnosticPack | None:
        with self._session_scope() as session:
            model = session.scalars(
                select(FailureDiagnosticPackModel)
                .where(FailureDiagnosticPackModel.run_id == run_id)
                .order_by(FailureDiagnosticPackModel.created_at.desc())
                .limit(1)
            ).one_or_none()
            return self._pack_from_model(model) if model else None

    @staticmethod
    def _pack_from_model(model: FailureDiagnosticPackModel) -> FailureDiagnosticPack:
        workflow = context_from_dict(model.workflow_context or {})
        evidence = evidence_from_dict(model.command_evidence) if model.command_evidence else None
        fault = PlatformFault(
            fault_code=model.fault_code,
            category=model.category,
            severity=model.severity,
            message=model.message,
            remediation=model.remediation,
            correlation_id=model.correlation_id,
            occurred_at=model.created_at,
        )
        return FailureDiagnosticPack(
            pack_id=model.id,
            correlation_id=model.correlation_id,
            fault=fault,
            workflow_context=workflow,
            command_evidence=evidence,
            sanitized_traceback=model.sanitized_traceback,
            created_at=model.created_at,
            checksum=model.checksum,
        )

    @staticmethod
    def model_payload(pack: FailureDiagnosticPack) -> dict[str, Any]:
        return pack.model_dump(mode="json")
