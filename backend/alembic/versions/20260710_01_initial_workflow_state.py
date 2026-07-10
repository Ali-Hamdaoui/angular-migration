"""Create initial backend-owned workflow-state tables.

Revision ID: 20260710_01
Revises:
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa

revision = "20260710_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "migration_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("source_angular_version", sa.String(length=32), nullable=True),
        sa.Column("target_angular_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_migration_runs_status", "migration_runs", ["status"])
    op.create_table(
        "migration_stages",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("stage_order", sa.Integer(), nullable=False),
        sa.Column("source_angular_version", sa.String(length=32), nullable=False),
        sa.Column("target_angular_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_migration_stages_run_id", "migration_stages", ["run_id"])
    op.create_index("ix_migration_stages_status", "migration_stages", ["status"])
    for table_name, stage_nullable in (("agent_executions", True), ("artifact_metadata", True), ("approval_events", True), ("workflow_events", True)):
        columns = [
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("stage_id", sa.String(length=64), nullable=stage_nullable),
        ]
        if table_name == "agent_executions":
            columns += [sa.Column("agent_name", sa.String(length=128), nullable=False), sa.Column("status", sa.String(length=64), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True), sa.Column("summary", sa.Text(), nullable=True)]
        elif table_name == "artifact_metadata":
            columns += [sa.Column("artifact_type", sa.String(length=64), nullable=False), sa.Column("relative_path", sa.Text(), nullable=False), sa.Column("checksum", sa.String(length=128), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)]
        elif table_name == "approval_events":
            columns += [sa.Column("decision", sa.String(length=64), nullable=False), sa.Column("actor", sa.String(length=128), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("rationale", sa.Text(), nullable=True)]
        else:
            columns += [sa.Column("event_type", sa.String(length=128), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)]
        columns += [sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]), sa.ForeignKeyConstraint(["stage_id"], ["migration_stages.id"]), sa.PrimaryKeyConstraint("id")]
        op.create_table(table_name, *columns)
        op.create_index(f"ix_{table_name}_run_id", table_name, ["run_id"])
    op.create_index("ix_agent_executions_status", "agent_executions", ["status"])
    op.create_index("ix_workflow_events_event_type", "workflow_events", ["event_type"])


def downgrade() -> None:
    for table_name in ("workflow_events", "approval_events", "artifact_metadata", "agent_executions", "migration_stages", "migration_runs"):
        op.drop_table(table_name)