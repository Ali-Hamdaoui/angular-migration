"""Normalize phase artifact ownership away from migration-stage foreign keys."""

from alembic import op
import sqlalchemy as sa


revision = "20260729_35"
down_revision = "20260729_34"
branch_labels = None
depends_on = None


_PHASE_STAGE_IDS = (
    "00_job_setup",
    "01_baseline",
    "02_analysis",
    "03_planning",
    "04_workflow_state",
    "global",
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE artifact_metadata
            SET stage_id = NULL
            WHERE stage_id IS NOT NULL
              AND relative_path NOT LIKE 'stages/%'
            """
        )
    )
    bind.execute(
        sa.text(
            """
            DELETE FROM migration_stages
            WHERE id IN :phase_stage_ids
              AND NOT EXISTS (
                  SELECT 1
                  FROM stage_execution_plans
                  WHERE stage_execution_plans.stage_id = migration_stages.id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM artifact_metadata
                  WHERE artifact_metadata.stage_id = migration_stages.id
              )
            """
        ).bindparams(sa.bindparam("phase_stage_ids", expanding=True)),
        {"phase_stage_ids": _PHASE_STAGE_IDS},
    )


def downgrade() -> None:
    # Restoring phase labels into a relational stage foreign key would
    # intentionally recreate invalid ownership, so this data repair is kept.
    pass
