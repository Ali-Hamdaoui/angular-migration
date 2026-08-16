"""Stage validation and sealing service (V2 F24)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domain.stage_validation import StageSeal, StageValidationResult
from app.repositories.models import MigrationStageModel, StageValidationSealModel
from app.repositories.session import session_scope
from app.services.workspace_fingerprint import STAGE_FINGERPRINT_PROFILE


class StageValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class StageValidationSealService:
    """Deterministic per-stage validation and immutable sealing (F24)."""

    def __init__(
        self,
        *,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def validate_stage(self, stage_id: str, workspace: Path) -> StageValidationResult:
        """Deterministic per-stage validation (F24-01).

        Runs the standard checks: the workspace exists, package.json is present,
        and the stage's target Angular version is resolvable.  A checksum-bound
        result freezes the outcome.
        """
        with self._session_scope() as session:
            stage = session.get(MigrationStageModel, stage_id)
            if stage is None:
                raise StageValidationError("STAGE_NOT_FOUND", f"Migration stage {stage_id} not found")
        checks = ("workspace_present", "package_json", "target_version")
        blockers: list[str] = []
        if not workspace.is_dir():
            blockers.append("STAGE_WORKSPACE_MISSING")
        elif not (workspace / "package.json").is_file():
            blockers.append("STAGE_PACKAGE_JSON_MISSING")
        if not stage.target_angular_version:
            blockers.append("STAGE_TARGET_VERSION_MISSING")
        fingerprint = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace) if workspace.is_dir() else ""
        result = StageValidationResult(
            stage_id=stage_id,
            checks=tuple(checks),
            passed=not blockers,
            blockers=tuple(blockers),
            workspace_fingerprint=fingerprint,
        )
        return result.bind_checksum()

    def seal_stage(self, stage_id: str, workspace: Path, *, run_id: str | None = None) -> StageSeal:
        """Seal the stage's validated evidence (F24-02).

        A stage can be sealed only when its validation passes; the seal freezes
        the validation checksum and workspace fingerprint immutably.
        """
        result = self.validate_stage(stage_id, workspace)
        if not result.passed:
            raise StageValidationError("STAGE_NOT_VALIDATED", f"stage {stage_id} validation did not pass")
        with self._session_scope() as session:
            stage = session.get(MigrationStageModel, stage_id)
            if stage is None:
                raise StageValidationError("STAGE_NOT_FOUND", f"Migration stage {stage_id} not found")
            if run_id is not None and stage.run_id != run_id:
                raise StageValidationError("STAGE_NOT_FOUND", f"stage {stage_id} does not belong to run {run_id}")
            existing = session.scalar(
                select(StageValidationSealModel).where(StageValidationSealModel.stage_id == stage_id)
            )
            if existing is not None:
                raise StageValidationError("STAGE_ALREADY_SEALED", f"stage {stage_id} is already sealed")
            seal = StageSeal(
                stage_id=stage_id,
                source_major=_major(stage.source_version_family),
                target_major=_major(stage.target_version_family),
                validation_checksum=result.checksum,
                workspace_fingerprint=result.workspace_fingerprint,
                sealed_at=self._now_provider(),
            ).bind_checksum()
            try:
                session.add(
                    StageValidationSealModel(
                        id="svs-" + hashlib.sha256(stage_id.encode()).hexdigest()[:24],
                        stage_id=stage_id,
                        stage_order=stage.stage_order,
                        run_id=stage.run_id,
                        source_major=seal.source_major,
                        target_major=seal.target_major,
                        validation_checksum=seal.validation_checksum,
                        workspace_fingerprint=seal.workspace_fingerprint,
                        sealed_at=seal.sealed_at,
                        checksum=seal.checksum,
                        created_at=self._now_provider(),
                    )
                )
                session.commit()
            except IntegrityError:
                session.rollback()
                raise StageValidationError("STAGE_ALREADY_SEALED", f"stage {stage_id} is already sealed") from None
        return seal

    def is_sealed(self, stage_id: str) -> StageValidationSealModel | None:
        """Immutability enforcement: a sealed stage's evidence cannot change (F24-04)."""
        with self._session_scope() as session:
            return session.scalar(
                select(StageValidationSealModel).where(StageValidationSealModel.stage_id == stage_id)
            )

    def assert_unsealed(self, stage_id: str) -> None:
        if self.is_sealed(stage_id) is not None:
            raise StageValidationError("STAGE_ALREADY_SEALED", f"stage {stage_id} is sealed; evidence is immutable")

    def list_stage_seals(self, run_id: str) -> list[StageValidationSealModel]:
        with self._session_scope() as session:
            return list(
                session.scalars(
                    select(StageValidationSealModel)
                    .where(StageValidationSealModel.run_id == run_id)
                    .order_by(StageValidationSealModel.created_at.asc())
                ).all()
            )


def _major(family: str | None) -> int:
    if not family:
        return 0
    try:
        return int(family.removeprefix("angular-").removesuffix(".x"))
    except ValueError:
        return 0
