"""Add one durable owner for stage recovery operations."""

from alembic import op
import sqlalchemy as sa


revision = "20260819_75"
down_revision = "20260819_74"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stage_recovery_operations",
        sa.UniqueConstraint(
            "run_id", "idempotency_key", name="uq_stage_recovery_operations_idempotency"
        ),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(length=64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("causal_execution_id", sa.String(length=64), nullable=False),
        sa.Column("interrupted_execution_id", sa.String(length=64), nullable=True),
        sa.Column("causal_evidence_checksum", sa.String(length=128), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=64), sa.ForeignKey("stage_checkpoints.id"), nullable=False),
        sa.Column("source_state_version", sa.Integer(), nullable=False),
        sa.Column("source_workspace_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("request_checksum", sa.String(length=128), nullable=False),
        sa.Column("recovery_checksum", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("repair_attempt_id", sa.String(length=64), nullable=True),
        sa.Column("command_execution_id", sa.String(length=64), nullable=True),
        sa.Column("preparation_artifact_id", sa.String(length=128), nullable=True),
        sa.Column("preparation_checksum", sa.String(length=128), nullable=True),
        sa.Column("stale_lock_checksum", sa.String(length=128), nullable=True),
        sa.Column("manifest_checksum", sa.String(length=128), nullable=True),
        sa.Column("prepared_workspace_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("source_error_code", sa.String(length=128), nullable=True),
        sa.Column("source_error_message", sa.Text(), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_stage_recovery_operations_run_id", "stage_recovery_operations", ["run_id"])
    op.create_index("ix_stage_recovery_operations_stage_id", "stage_recovery_operations", ["stage_id"])
    op.create_index("ix_stage_recovery_operations_causal_execution_id", "stage_recovery_operations", ["causal_execution_id"])
    op.create_index("ix_stage_recovery_operations_interrupted_execution_id", "stage_recovery_operations", ["interrupted_execution_id"])
    op.create_index("ix_stage_recovery_operations_checkpoint_id", "stage_recovery_operations", ["checkpoint_id"])
    op.create_index("ix_stage_recovery_operations_recovery_checksum", "stage_recovery_operations", ["recovery_checksum"])
    op.create_index("ix_stage_recovery_operations_repair_attempt_id", "stage_recovery_operations", ["repair_attempt_id"])
    op.create_index("ix_stage_recovery_operations_command_execution_id", "stage_recovery_operations", ["command_execution_id"])
    op.create_index("ix_stage_recovery_operations_preparation_artifact_id", "stage_recovery_operations", ["preparation_artifact_id"])
    op.create_index(
        "uq_stage_recovery_operations_active",
        "stage_recovery_operations",
        ["run_id", "stage_id"],
        unique=True,
        sqlite_where=sa.text("status NOT IN ('COMPLETED', 'FAILED')"),
    )
def downgrade() -> None:
    op.drop_table("stage_recovery_operations")
