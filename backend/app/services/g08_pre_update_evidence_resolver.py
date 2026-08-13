"""Resolve immutable pre-update evidence for automatic and recovery G08 creation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from app.repositories.models import MigrationStageModel, StageCheckpointModel


class G08PreUpdateEvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class G08PreUpdateEvidence:
    checkpoint_id: str
    path: str
    fingerprint: str


class G08PreUpdateEvidenceResolver:
    def resolve(self, session, run, continuation, angular_checkpoint) -> G08PreUpdateEvidence:
        current_stage = session.get(MigrationStageModel, continuation.current_stage_id)
        if current_stage is None:
            raise G08PreUpdateEvidenceError(
                "G08_PRE_UPDATE_EVIDENCE_UNAVAILABLE", "Current migration stage is missing."
            )
        pre_bootstrap = session.scalar(
            select(StageCheckpointModel)
            .where(
                StageCheckpointModel.run_id == run.id,
                StageCheckpointModel.stage_id == current_stage.id,
                StageCheckpointModel.kind == "pre_bootstrap",
            )
            .order_by(StageCheckpointModel.sequence.desc())
        )
        previous_stage = (
            session.scalar(
                select(MigrationStageModel).where(
                    MigrationStageModel.run_id == run.id,
                    MigrationStageModel.stage_order == current_stage.stage_order - 1,
                )
            )
            if current_stage.stage_order > 1
            else None
        )
        sealed_source = (
            session.scalar(
                select(StageCheckpointModel)
                .where(
                    StageCheckpointModel.run_id == run.id,
                    StageCheckpointModel.stage_id == previous_stage.id,
                    StageCheckpointModel.kind == "sealed_output",
                    StageCheckpointModel.sealed.is_(True),
                )
                .order_by(StageCheckpointModel.sequence.desc())
            )
            if previous_stage is not None
            else None
        )
        return self.resolve_records(
            stage_order=current_stage.stage_order,
            baseline_path=str((run.workspace_aliases or {}).get("BASELINE_SANDBOX", "")),
            angular_checkpoint=angular_checkpoint,
            pre_bootstrap=pre_bootstrap,
            previous_stage=previous_stage,
            sealed_source=sealed_source,
        )

    @staticmethod
    def resolve_records(
        *,
        stage_order: int,
        baseline_path: str,
        angular_checkpoint,
        pre_bootstrap,
        previous_stage,
        sealed_source,
    ) -> G08PreUpdateEvidence:
        if (
            angular_checkpoint is None
            or angular_checkpoint.kind != "pre_angular_update"
            or not angular_checkpoint.safe_for_resume
        ):
            raise G08PreUpdateEvidenceError(
                "G08_PRE_UPDATE_EVIDENCE_UNAVAILABLE",
                "The execution-bound pre-update checkpoint is missing or unsafe.",
            )
        if stage_order == 1:
            if not baseline_path:
                raise G08PreUpdateEvidenceError(
                    "G08_PRE_UPDATE_EVIDENCE_UNAVAILABLE", "Baseline sandbox is unavailable."
                )
            return G08PreUpdateEvidence(
                checkpoint_id=angular_checkpoint.id,
                path=str(Path(baseline_path)),
                fingerprint=angular_checkpoint.workspace_fingerprint,
            )
        if (
            previous_stage is None
            or previous_stage.status != "sealed"
            or sealed_source is None
            or not sealed_source.sealed
            or not sealed_source.safe_for_resume
            or pre_bootstrap is None
            or not pre_bootstrap.safe_for_resume
            or pre_bootstrap.workspace_fingerprint != sealed_source.workspace_fingerprint
            or angular_checkpoint.workspace_fingerprint != sealed_source.workspace_fingerprint
        ):
            raise G08PreUpdateEvidenceError(
                "G08_PRE_UPDATE_EVIDENCE_UNAVAILABLE",
                "Successor G08 is not bound to the previous immutable sealed output.",
            )
        return G08PreUpdateEvidence(
            checkpoint_id=sealed_source.id,
            path=sealed_source.workspace_path,
            fingerprint=sealed_source.workspace_fingerprint,
        )
