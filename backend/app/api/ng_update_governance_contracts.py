"""API contracts for Angular update governance (V2 F14)."""

from app.domain.contracts import ContractModel


class NgUpdateSpecDto(ContractModel):
    source_major: int
    target_major: int
    template_id: str
    executable: str
    target_exact: str
    target_cli_exact: str
    rendered_arguments: list[str]
    checksum: str


class NgUpdateAuthorizationDto(ContractModel):
    source_major: int
    target_major: int
    spec_checksum: str
    certified: bool
    allowed: bool
    reason: str | None = None
