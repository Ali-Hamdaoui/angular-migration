"""Workspace authority service: generation registry, active resolver, guarded promotion (V2 F07)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.workspace_authority import (
    WorkspaceGenerationRecord,
    WorkspacePromotionDecision,
    WorkspacePromotionRequest,
    evaluate_promotion,
)
from app.repositories.models import MigrationRunModel, StageWorkspaceBindingModel, WorkspaceGenerationModel
from app.repositories.session import session_scope


class WorkspaceAuthorityError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class WorkspaceAuthorityService:
    """Deterministic generation-ordered workspace authority.

    Promotion is guarded: only a strictly newer generation can become active,
    so an old workspace can never become active accidentally.
    """

    def __init__(
        self,
        *,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def current_generation(self, run_id: str, stage_id: str | None, alias: str) -> int | None:
        """Highest generation recorded for this workspace; None when none exists."""
        with self._session_scope() as session:
            row = session.execute(
                select(WorkspaceGenerationModel.generation)
                .where(
                    WorkspaceGenerationModel.run_id == run_id,
                    WorkspaceGenerationModel.stage_id == stage_id,
                    WorkspaceGenerationModel.alias == alias,
                )
                .order_by(WorkspaceGenerationModel.generation.desc())
                .limit(1)
            ).first()
            return row[0] if row else None

    def resolve_active(
        self, run_id: str, stage_id: str | None, alias: str
    ) -> WorkspaceGenerationRecord | None:
        """Resolve the active workspace, verifying it is the highest generation.

        Returns None when no active generation exists for the workspace.
        """
        with self._session_scope() as session:
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == run_id,
                    StageWorkspaceBindingModel.stage_id == stage_id,
                    StageWorkspaceBindingModel.alias == alias,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if binding is None:
                return None
            generation = session.scalar(
                select(WorkspaceGenerationModel.generation)
                .where(
                    WorkspaceGenerationModel.run_id == run_id,
                    WorkspaceGenerationModel.stage_id == stage_id,
                    WorkspaceGenerationModel.alias == alias,
                    WorkspaceGenerationModel.active_binding_id == binding.id,
                    WorkspaceGenerationModel.status == "active",
                )
                .order_by(WorkspaceGenerationModel.generation.desc())
                .limit(1)
            )
            highest = session.execute(
                select(WorkspaceGenerationModel.generation)
                .where(
                    WorkspaceGenerationModel.run_id == run_id,
                    WorkspaceGenerationModel.stage_id == stage_id,
                    WorkspaceGenerationModel.alias == alias,
                )
                .order_by(WorkspaceGenerationModel.generation.desc())
                .limit(1)
            ).first()
            if generation is None or (highest is not None and generation < highest[0]):
                # The active binding is not the newest generation: the workspace
                # is stale. Never return it as authoritative.
                return None
            return WorkspaceGenerationRecord(
                run_id=run_id,
                stage_id=stage_id,
                alias=alias,
                generation=generation,
                workspace_path=binding.workspace_path,
                fingerprint=binding.workspace_fingerprint,
                input_fingerprint=binding.input_fingerprint,
                status="active",
                created_at=binding.created_at,
            )

    def promote(self, request: WorkspacePromotionRequest) -> WorkspacePromotionDecision:
        """Register a generation and promote it to active under the monotonic guard.

        The promotion is atomic: the previous active binding is retired and the
        new generation's binding becomes active in one transaction.  A request
        whose generation is not strictly newer is rejected (STALE_GENERATION).
        """
        decision = evaluate_promotion(request, self.current_generation(request.run_id, request.stage_id, request.alias))
        if not decision.allowed:
            raise WorkspaceAuthorityError(
                "STALE_GENERATION",
                decision.reason or "generation is not strictly newer",
                {"current_active_generation": decision.current_active_generation, "requested_generation": decision.generation},
            )
        now = self._now_provider()
        with self._session_scope() as session:
            if session.get(MigrationRunModel, request.run_id) is None:
                raise WorkspaceAuthorityError("RUN_NOT_FOUND", f"Migration run {request.run_id} not found")
            binding_id = _binding_id(request.run_id, request.stage_id, request.alias)
            previous = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == request.run_id,
                    StageWorkspaceBindingModel.stage_id == request.stage_id,
                    StageWorkspaceBindingModel.alias == request.alias,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if previous is not None:
                previous.active = False
            binding = session.get(StageWorkspaceBindingModel, binding_id)
            if binding is None:
                binding = StageWorkspaceBindingModel(
                    id=binding_id,
                    run_id=request.run_id,
                    stage_id=request.stage_id,
                    alias=request.alias,
                    workspace_path=request.workspace_path,
                    workspace_fingerprint=request.fingerprint,
                    fingerprint_profile_id=None,
                    input_fingerprint=request.input_fingerprint,
                    active=True,
                    created_at=now,
                )
                session.add(binding)
            else:
                binding.active = True
                binding.workspace_path = request.workspace_path
                binding.workspace_fingerprint = request.fingerprint
                binding.input_fingerprint = request.input_fingerprint
            session.add(
                WorkspaceGenerationModel(
                    id=_generation_id(request.run_id, request.stage_id, request.alias, request.generation),
                    run_id=request.run_id,
                    stage_id=request.stage_id,
                    alias=request.alias,
                    generation=request.generation,
                    workspace_path=request.workspace_path,
                    fingerprint=request.fingerprint,
                    input_fingerprint=request.input_fingerprint,
                    status="active",
                    active_binding_id=binding_id,
                    created_at=now,
                )
            )
            session.commit()
        return decision

    def list_generations(self, run_id: str, stage_id: str | None, alias: str) -> list[WorkspaceGenerationModel]:
        with self._session_scope() as session:
            return list(
                session.scalars(
                    select(WorkspaceGenerationModel)
                    .where(
                        WorkspaceGenerationModel.run_id == run_id,
                        WorkspaceGenerationModel.stage_id == stage_id,
                        WorkspaceGenerationModel.alias == alias,
                    )
                    .order_by(WorkspaceGenerationModel.generation.asc())
                ).all()
            )


def _binding_id(run_id: str, stage_id: str | None, alias: str) -> str:
    import hashlib

    return "stage-workspace-" + hashlib.sha256(f"{run_id}:{stage_id}:{alias}".encode()).hexdigest()[:24]


def _generation_id(run_id: str, stage_id: str | None, alias: str, generation: int) -> str:
    import hashlib

    return "gen-" + hashlib.sha256(f"{run_id}:{stage_id}:{alias}:{generation}".encode()).hexdigest()[:24]
