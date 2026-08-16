"""Failure diagnostics API (V2 F03-06)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.diagnostics_contracts import (
    CommandFailureEvidenceDto,
    FailureDiagnosticPackDto,
    FailureDiagnosticPackListDto,
    PlatformFaultDto,
    WorkflowFailureContextDto,
)
from app.services.diagnostics_application_service import DiagnosticsApplicationService

router = APIRouter(prefix="/diagnostics", tags=["failure-diagnostics"])


def get_diagnostics_service() -> DiagnosticsApplicationService:
    return DiagnosticsApplicationService()


def _pack_dto(pack) -> FailureDiagnosticPackDto:
    fault = pack.fault
    workflow = pack.workflow_context
    evidence = pack.command_evidence
    return FailureDiagnosticPackDto(
        pack_id=pack.pack_id,
        correlation_id=pack.correlation_id,
        fault=PlatformFaultDto(
            fault_code=fault.fault_code,
            category=fault.category.value,
            severity=fault.severity.value,
            message=fault.message,
            remediation=fault.remediation,
            correlation_id=fault.correlation_id,
            occurred_at=fault.occurred_at,
            context=fault.context,
        ),
        workflow_context=WorkflowFailureContextDto(
            run_id=workflow.run_id,
            stage_id=workflow.stage_id,
            step_id=workflow.step_id,
            execution_id=workflow.execution_id,
            command_id=workflow.command_id,
            state_version=workflow.state_version,
            event_sequence=workflow.event_sequence,
            workflow_node=workflow.workflow_node,
            phase=workflow.phase,
        ),
        command_evidence=CommandFailureEvidenceDto(
            command=list(evidence.command),
            exit_code=evidence.exit_code,
            stdout=evidence.stdout,
            stderr=evidence.stderr,
            working_directory_alias=evidence.working_directory_alias,
            runtime_profile_id=evidence.runtime_profile_id,
            timeout_seconds=evidence.timeout_seconds,
            cancelled=evidence.cancelled,
            timed_out=evidence.timed_out,
        )
        if evidence
        else None,
        sanitized_traceback=pack.sanitized_traceback,
        created_at=pack.created_at,
        checksum=pack.checksum,
    )


def _not_found(pack_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"error_code": "DIAGNOSTIC_PACK_NOT_FOUND", "message": f"Diagnostic pack {pack_id} not found."})


@router.get("/packs/{pack_id}", response_model=FailureDiagnosticPackDto)
def get_diagnostic_pack(
    pack_id: str,
    service: DiagnosticsApplicationService = Depends(get_diagnostics_service),
) -> FailureDiagnosticPackDto:
    pack = service.get_pack(pack_id)
    if pack is None:
        raise _not_found(pack_id)
    return _pack_dto(pack)


@router.get("/runs/{run_id}/packs", response_model=FailureDiagnosticPackListDto)
def list_run_diagnostic_packs(
    run_id: str,
    service: DiagnosticsApplicationService = Depends(get_diagnostics_service),
) -> FailureDiagnosticPackListDto:
    return FailureDiagnosticPackListDto(packs=[_pack_dto(pack) for pack in service.list_packs(run_id)])


@router.get("/runs/{run_id}/executions/{execution_id}/packs", response_model=FailureDiagnosticPackListDto)
def list_execution_diagnostic_packs(
    run_id: str,
    execution_id: str,
    service: DiagnosticsApplicationService = Depends(get_diagnostics_service),
) -> FailureDiagnosticPackListDto:
    return FailureDiagnosticPackListDto(packs=[_pack_dto(pack) for pack in service.packs_for_execution(execution_id)])
