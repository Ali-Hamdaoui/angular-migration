"""Add immutable AMFA-171 G07 business-decision history."""

from alembic import op
import sqlalchemy as sa


revision = "20260721_02"
down_revision = "20260721_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stage_workspaces", sa.Column("copy_report_artifact_id", sa.String(64)))
    op.add_column("stage_workspaces", sa.Column("copy_report_artifact_checksum", sa.String(128)))
    op.add_column("stage_workspaces", sa.Column("verification_artifact_id", sa.String(64)))
    op.add_column("stage_workspaces", sa.Column("verification_artifact_checksum", sa.String(128)))
    op.create_table(
        "g07_decision_history",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("gate_id", sa.String(64), sa.ForeignKey("g07_approvals.id"), nullable=False),
        sa.Column("gate_version", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("payload_checksum", sa.String(128), nullable=False),
        sa.Column("request_checksum", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("bindings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_g07_decision_history_run_idempotency"),
    )
    op.create_index("ix_g07_decision_history_run_id", "g07_decision_history", ["run_id"])
    op.create_index("ix_g07_decision_history_stage_id", "g07_decision_history", ["stage_id"])
    op.create_index("ix_g07_decision_history_gate_id", "g07_decision_history", ["gate_id"])
    op.create_index("ix_g07_decision_history_correlation_id", "g07_decision_history", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_g07_decision_history_correlation_id", table_name="g07_decision_history")
    op.drop_index("ix_g07_decision_history_stage_id", table_name="g07_decision_history")
    op.drop_index("ix_g07_decision_history_gate_id", table_name="g07_decision_history")
    op.drop_index("ix_g07_decision_history_run_id", table_name="g07_decision_history")
    op.drop_table("g07_decision_history")
    op.drop_column("stage_workspaces", "verification_artifact_checksum")
    op.drop_column("stage_workspaces", "verification_artifact_id")
    op.drop_column("stage_workspaces", "copy_report_artifact_checksum")
    op.drop_column("stage_workspaces", "copy_report_artifact_id")
