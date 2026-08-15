"""Runtime execution authority API (V2 F01)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.runtime_contracts import (
    DiscoverRuntimeDescriptorsResponse,
    ListRuntimeEvidenceResponse,
    RecordRuntimeEvidenceRequest,
    RecordRuntimeEvidenceResponse,
    ResolveRuntimeRequirementsRequest,
    ResolveRuntimeRequirementsResponse,
    RuntimeExecutableDescriptorDto,
    RuntimeRequirementBindingDto,
    RuntimeRequirementDto,
)
from app.core.config import get_settings
from app.domain.runtime_execution import RuntimeRequirement
from app.services.runtime_resolution_application_service import (
    RuntimeResolutionApplicationService,
    RuntimeResolutionError,
    _descriptor_from_row,
)

router = APIRouter(tags=["runtime-execution-authority"])


def get_runtime_resolution_service() -> RuntimeResolutionApplicationService:
    return RuntimeResolutionApplicationService(get_settings())


def _raise(error: RuntimeResolutionError) -> None:
    raise HTTPException(status_code=400, detail={"error_code": error.code, "message": error.message})


def _descriptor_dto(item) -> RuntimeExecutableDescriptorDto:
    return RuntimeExecutableDescriptorDto(
        kind=item.kind.value,
        executable_name=item.executable_name,
        resolved_path=item.resolved_path,
        version_exact=item.version_exact,
        sha256=item.sha256,
        operating_system=item.operating_system,
        architecture=item.architecture,
        installation_root=item.installation_root,
        source=item.source,
        runtime_id=item.runtime_id,
        probed_at=item.probed_at,
    )


def _binding_dto(item) -> RuntimeRequirementBindingDto:
    return RuntimeRequirementBindingDto(
        requirement=RuntimeRequirementDto(
            kind=item.requirement.kind.value,
            runtime_id=item.requirement.runtime_id,
            version_exact=item.requirement.version_exact,
            minimum_version=item.requirement.minimum_version,
            required_sha256=item.requirement.required_sha256,
        ),
        descriptor=_descriptor_dto(item.descriptor) if item.descriptor else None,
        blocked_reason=item.blocked_reason,
        resolved_at=item.resolved_at,
    )


def _requirements(request) -> list[RuntimeRequirement]:
    return [
        RuntimeRequirement(
            kind=item.kind,
            runtime_id=item.runtime_id,
            version_exact=item.version_exact,
            minimum_version=item.minimum_version,
            required_sha256=item.required_sha256,
        )
        for item in request.requirements
    ]


@router.post("/runtime/requirements/resolve", response_model=ResolveRuntimeRequirementsResponse)
def resolve_runtime_requirements(
    request: ResolveRuntimeRequirementsRequest,
    service: RuntimeResolutionApplicationService = Depends(get_runtime_resolution_service),
) -> ResolveRuntimeRequirementsResponse:
    try:
        bindings = service.resolve(_requirements(request))
    except RuntimeResolutionError as error:
        _raise(error)
    return ResolveRuntimeRequirementsResponse(bindings=[_binding_dto(item) for item in bindings])


@router.get("/runtime/executables", response_model=DiscoverRuntimeDescriptorsResponse)
def discover_runtime_executables(
    service: RuntimeResolutionApplicationService = Depends(get_runtime_resolution_service),
) -> DiscoverRuntimeDescriptorsResponse:
    descriptors = service.discover()
    return DiscoverRuntimeDescriptorsResponse(descriptors=[_descriptor_dto(item) for item in descriptors])


@router.post("/runs/{run_id}/runtime/evidence", response_model=RecordRuntimeEvidenceResponse)
def record_runtime_evidence(
    run_id: str,
    request: RecordRuntimeEvidenceRequest,
    service: RuntimeResolutionApplicationService = Depends(get_runtime_resolution_service),
) -> RecordRuntimeEvidenceResponse:
    try:
        records = service.record_evidence(
            run_id,
            service.resolve(_requirements(request)),
            execution_id=request.execution_id,
            actor=request.actor,
        )
    except RuntimeResolutionError as error:
        _raise(error)
    return RecordRuntimeEvidenceResponse(
        recorded=len(records), evidence=[_descriptor_dto(_descriptor_from_row(item)) for item in records]
    )


@router.get("/runs/{run_id}/runtime/evidence", response_model=ListRuntimeEvidenceResponse)
def list_runtime_evidence(
    run_id: str,
    service: RuntimeResolutionApplicationService = Depends(get_runtime_resolution_service),
) -> ListRuntimeEvidenceResponse:
    evidence = service.list_evidence(run_id)
    return ListRuntimeEvidenceResponse(evidence=[_descriptor_dto(item) for item in evidence])
