"""Workspace generation authority contracts (V2 F07).

A workspace is a durable, generation-ordered artifact: each promotion produces a
strictly higher generation, and only the highest generation may be active.  An
old workspace can never become active accidentally because generations are
monotonic and promotion is guarded by that invariant.

This module has no process, filesystem, database, or network side effects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WorkspaceGenerationRecord(_ImmutableModel):
    """One immutable generation of a workspace for a run/stage/alias."""

    run_id: str = Field(min_length=1)
    stage_id: str | None = None
    alias: str = Field(min_length=1)
    generation: int = Field(ge=1)
    workspace_path: str = Field(min_length=1)
    fingerprint: str = Field(min_length=1)
    input_fingerprint: str | None = None
    status: Literal["prepared", "active", "retired"] = "prepared"
    created_at: datetime


class WorkspacePromotionRequest(_ImmutableModel):
    """A request to promote a prepared workspace generation to active."""

    run_id: str = Field(min_length=1)
    stage_id: str | None = None
    alias: str = Field(min_length=1)
    generation: int = Field(ge=1)
    workspace_path: str = Field(min_length=1)
    fingerprint: str = Field(min_length=1)
    input_fingerprint: str | None = None


class WorkspacePromotionDecision(_ImmutableModel):
    """Deterministic result of the guarded promotion check."""

    run_id: str
    stage_id: str | None
    alias: str
    generation: int
    current_active_generation: int | None = None
    allowed: bool
    reason: str | None = None


def evaluate_promotion(
    request: WorkspacePromotionRequest,
    current_active_generation: int | None,
) -> WorkspacePromotionDecision:
    """Guard: a promotion is allowed only when its generation is strictly newer.

    ``None`` current generation means no active workspace exists yet (first
    promotion allowed).
    """
    if current_active_generation is None:
        return WorkspacePromotionDecision(
            run_id=request.run_id, stage_id=request.stage_id, alias=request.alias,
            generation=request.generation, current_active_generation=None, allowed=True,
            reason="first workspace generation",
        )
    if request.generation <= current_active_generation:
        return WorkspacePromotionDecision(
            run_id=request.run_id, stage_id=request.stage_id, alias=request.alias,
            generation=request.generation, current_active_generation=current_active_generation,
            allowed=False,
            reason=f"generation {request.generation} is not strictly newer than active generation {current_active_generation}",
        )
    return WorkspacePromotionDecision(
        run_id=request.run_id, stage_id=request.stage_id, alias=request.alias,
        generation=request.generation, current_active_generation=current_active_generation,
        allowed=True, reason="strictly newer generation",
    )
