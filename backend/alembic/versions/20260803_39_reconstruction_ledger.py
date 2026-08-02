"""Add the durable governed workspace reconstruction ledger (T03)."""

from alembic import op
import sqlalchemy as sa


revision = "20260803_39"
down_revision = "20260802_38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stage_reconstruction_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("checkpoint_id", sa.String(64), sa.ForeignKey("stage_checkpoints.id")),
        sa.Column("reason", sa.String(128), nullable=False),
        sa.Column("source_workspace_fingerprint", sa.String(128), nullable=False),
        sa.Column("restored_workspace_fingerprint", sa.String(128), nullable=False),
        sa.Column("created_from_execution_id", sa.String(64), sa.ForeignKey("command_executions.id")),
        sa.Column("attempt_id", sa.String(64), sa.ForeignKey("repair_attempts.id")),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_stage_reconstruction_stage",
        "stage_reconstruction_records",
        ["run_id", "stage_id"],
    )
    op.create_index(
        "ix_stage_reconstruction_checkpoint",
        "stage_reconstruction_records",
        ["checkpoint_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_stage_reconstruction_checkpoint", table_name="stage_reconstruction_records")
    op.drop_index("ix_stage_reconstruction_stage", table_name="stage_reconstruction_records")
    op.drop_table("stage_reconstruction_records")
