"""Stage runtime requirement and binding API (V2 F02)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.runtime_contracts import (
    RuntimeExecutableDescriptorDto,
    RuntimeRequirementBindingDto,
    RuntimeRequirementDto,
)
from app.api.stage_runtime_contracts import (
    RecordStageRuntimeBindingRequest,
    ResolveStageRuntimeRequest,
    StageRuntimeBindingDto,
    StageRuntimeBindingListDto,
    StageRuntimeBindingRowDto,
    StageRuntimeRequirementDto,
)
from app.core.config import get_settings
from app.services.stage_runtime_service import StageRuntimeApplicationService, StageRuntimeError

router = APIRouter(tags=["stage-runtime"])


def get_stage_runtime_service() -> StageRuntimeApplicationService:
    return StageRuntimeApplicationService(settings=get_settings())


def _raise(error: StageRuntimeError) -> None:
    raise HTTPException(status_code=404 if error.code in {"STAGE_NOT_FOUND", "CATALOGUE_ENTRY_MISSING", "RUN_NOT_FOUND"} else 422,
                        detail={"error_code": error.code, "message": error.message})


def _requirement_dto(requirement) -> StageRuntimeRequirementDto:
    return StageRuntimeRequirementDto(
        stage_id=requirement.stage_id,
        source_family=requirement.source_family,
        target_family=requirement.target_family,
        catalogue_version=requirement.catalogue_version,
        requirements=[
            RuntimeRequirementDto(
                kind=r.kind.value, runtime_id=r.runtime_id, version_exact=r.version_exact,
                minimum_version=r.minimum_version, required_sha256=r.required_sha256,
            )
            for r in requirement.requirements
        ],
    )


def _binding_full_dto(b, resolved_at) -> RuntimeRequirementBindingDto:
    d = b.descriptor
    return RuntimeRequirementBindingDto(
        requirement=RuntimeRequirementDto(
            kind=b.requirement.kind.value, runtime_id=b.requirement.runtime_id,
            version_exact=b.requirement.version_exact, minimum_version=b.requirement.minimum_version,
            required_sha256=b.requirement.required_sha256,
        ),
        descriptor=RuntimeExecutableDescriptorDto(
            kind=d.kind.value, executable_name=d.executable_name, resolved_path=d.resolved_path,
            version_exact=d.version_exact, sha256=d.sha256, operating_system=d.operating_system,
            architecture=d.architecture, installation_root=d.installation_root, source=d.source,
            runtime_id=d.runtime_id, probed_at=d.probed_at,
        ),
        resolved_at=resolved_at,
    )


def _binding_dto(binding) -> StageRuntimeBindingDto:
    return StageRuntimeBindingDto(
        stage_id=binding.stage_id,
        requirement=_requirement_dto(binding.requirement),
        bindings=[
            _binding_full_dto(b, binding.resolved_at) if b.descriptor is not None
            else RuntimeRequirementBindingDto(
                requirement=RuntimeRequirementDto(
                    kind=b.requirement.kind.value, runtime_id=b.requirement.runtime_id,
                    version_exact=b.requirement.version_exact, minimum_version=b.requirement.minimum_version,
                    required_sha256=b.requirement.required_sha256,
                ),
                blocked_reason=b.blocked_reason,
                resolved_at=binding.resolved_at,
            )
            for b in binding.bindings
        ],
        status=binding.status,
        blocked_reason=binding.blocked_reason,
        resolved_at=binding.resolved_at,
        checksum=binding.checksum,
    )


def _row_dto(row) -> StageRuntimeBindingRowDto:
    return StageRuntimeBindingRowDto(
        id=row.id, run_id=row.run_id, stage_id=row.stage_id, kind=row.kind,
        runtime_id=row.runtime_id, version_exact=row.version_exact, sha256=row.sha256,
        resolved_path=row.resolved_path, source=row.source, status=row.status,
        blocked_reason=row.blocked_reason, created_at=row.created_at,
    )


@router.post("/runs/{run_id}/stages/{stage_id}/runtime/resolve", response_model=StageRuntimeBindingDto)
def resolve_stage_runtime(
    run_id: str,
    stage_id: str,
    request: ResolveStageRuntimeRequest,
    service: StageRuntimeApplicationService = Depends(get_stage_runtime_service),
) -> StageRuntimeBindingDto:
    try:
        binding = service.resolve_stage(stage_id, request.source_family, request.target_family, request.catalogue_version)
    except StageRuntimeError as error:
        _raise(error)
    return _binding_dto(binding)


@router.post("/runs/{run_id}/stages/{stage_id}/runtime/bindings", response_model=StageRuntimeBindingListDto)
def record_stage_runtime_binding(
    run_id: str,
    stage_id: str,
    request: RecordStageRuntimeBindingRequest,
    service: StageRuntimeApplicationService = Depends(get_stage_runtime_service),
) -> StageRuntimeBindingListDto:
    try:
        families = service.stage_version_families(stage_id)
        binding = service.resolve_stage(stage_id, families[0], families[1])
        rows = service.record_binding(run_id, binding, actor=request.actor)
    except StageRuntimeError as error:
        _raise(error)
    return StageRuntimeBindingListDto(bindings=[_row_dto(row) for row in rows])


@router.get("/runs/{run_id}/stages/{stage_id}/runtime/bindings", response_model=StageRuntimeBindingListDto)
def list_stage_runtime_bindings(
    run_id: str,
    stage_id: str,
    service: StageRuntimeApplicationService = Depends(get_stage_runtime_service),
) -> StageRuntimeBindingListDto:
    return StageRuntimeBindingListDto(bindings=[_row_dto(row) for row in service.list_stage_bindings(stage_id)])
