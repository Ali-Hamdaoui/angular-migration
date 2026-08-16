"""Angular update governance contracts (V2 F14).

Each adjacent-major transition resolves to exactly one ``ng update`` command
spec (template + catalogue-derived bindings), frozen by a checksum.  Update
execution is governed: it must target a certified runtime for the stage and the
rendered command must match the catalogue-derived spec.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NgUpdateCommandSpec(_ImmutableModel):
    """The exact, checksum-bound ng update command for one transition."""

    source_major: int = Field(ge=11, le=21)
    target_major: int = Field(ge=11, le=21)
    template_id: str = Field(min_length=1)
    executable: str = Field(min_length=1)
    target_exact: str = Field(min_length=1)
    target_cli_exact: str = Field(min_length=1)
    rendered_arguments: tuple[str, ...] = Field(min_length=1)
    checksum: str = ""

    def bind_checksum(self) -> "NgUpdateCommandSpec":
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


class NgUpdateAuthorization(_ImmutableModel):
    """Deterministic authorization result for an update execution."""

    source_major: int
    target_major: int
    spec_checksum: str
    certified: bool
    allowed: bool
    reason: str | None = None
