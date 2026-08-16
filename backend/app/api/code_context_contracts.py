"""API contracts for code context intelligence (V2 F20)."""

from app.domain.contracts import ContractModel


class CodeContextUnitDto(ContractModel):
    path: str
    kind: str
    symbol: str = ""
    excerpt: str
    start_line: int
    end_line: int
    token_count: int


class CodeContextBundleDto(ContractModel):
    units: list[CodeContextUnitDto]
    total_tokens: int
    budget: int
    truncated: bool
    checksum: str


class RetrieveContextRequest(ContractModel):
    workspace_path: str
    symbols: list[str]
    template_selectors: list[str] | None = None
    budget: int | None = None
