"""Code context intelligence contracts (V2 F20).

Extracts bounded, relevant code context (TypeScript/Angular template excerpts)
for the symbols affected by a failure, under a token budget.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CodeContextUnit(_ImmutableModel):
    """One bounded code excerpt for an affected symbol."""

    path: str = Field(min_length=1)
    kind: str  # "typescript" | "template"
    symbol: str = Field(default="")
    excerpt: str = Field(min_length=1)
    start_line: int = Field(default=1, ge=1)
    end_line: int = Field(default=1, ge=1)
    token_count: int = Field(default=0, ge=0)


class CodeContextBundle(_ImmutableModel):
    """The assembled context: units bounded under a token budget."""

    units: tuple[CodeContextUnit, ...] = Field(default_factory=tuple)
    total_tokens: int = Field(default=0, ge=0)
    budget: int = Field(default=0, ge=0)
    truncated: bool = False
    checksum: str = ""

    def bind_checksum(self) -> CodeContextBundle:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})
