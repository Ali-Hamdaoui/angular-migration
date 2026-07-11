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


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "migration_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("run_phase", sa.String(length=64), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("source_version_family", sa.String(length=32), nullable=True),
        sa.Column("target_version_family", sa.String(length=32), nullable=True),
        sa.Column("source_version_detected", sa.String(length=64), nullable=True),
        sa.Column("target_version_resolved", sa.String(length=64), nullable=True),
        sa.Column("source_angular_version", sa.String(length=32), nullable=True),
        sa.Column("target_angular_version", sa.String(length=32), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_migration_runs_status", "migration_runs", ["status"])

    op.create_table(
        "migration_stages",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("stage_order", sa.Integer(), nullable=False),
        sa.Column("source_version_family", sa.String(length=32), nullable=True),
        sa.Column("target_version_family", sa.String(length=32), nullable=True),
        sa.Column("source_version_detected", sa.String(length=64), nullable=True),
        sa.Column("target_version_resolved", sa.String(length=64), nullable=True),
        sa.Column("source_angular_version", sa.String(length=32), nullable=True),
        sa.Column("target_angular_version", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("current_agent", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "stage_order", name="uq_migration_stages_run_order"),
    )
    op.create_index("ix_migration_stages_run_id", "migration_stages", ["run_id"])
    op.create_index("ix_migration_stages_status", "migration_stages", ["status"])

    op.create_table(
        "stage_steps",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("stage_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("component_type", sa.String(length=64), nullable=False),
        sa.Column("attempt_id", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]),
        sa.ForeignKeyConstraint(["stage_id"], ["migration_stages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stage_steps_run_id", "stage_steps", ["run_id"])
    op.create_index("ix_stage_steps_stage_id", "stage_steps", ["stage_id"])
    op.create_index("ix_stage_steps_status", "stage_steps", ["status"])
    op.create_index("ix_stage_steps_attempt_id", "stage_steps", ["attempt_id"])
    op.create_index("ix_stage_steps_run_stage", "stage_steps", ["run_id", "stage_id"])

    op.create_table(
        "agent_executions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("stage_id", sa.String(length=64), nullable=True),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]),
        sa.ForeignKeyConstraint(["stage_id"], ["migration_stages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_executions_run_id", "agent_executions", ["run_id"])
    op.create_index("ix_agent_executions_stage_id", "agent_executions", ["stage_id"])
    op.create_index("ix_agent_executions_status", "agent_executions", ["status"])

    op.create_table(
        "workflow_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("stage_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]),
        sa.ForeignKeyConstraint(["stage_id"], ["migration_stages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_workflow_events_run_sequence"),
    )
    op.create_index("ix_workflow_events_run_id", "workflow_events", ["run_id"])
    op.create_index("ix_workflow_events_stage_id", "workflow_events", ["stage_id"])
    op.create_index("ix_workflow_events_event_type", "workflow_events", ["event_type"])

    op.create_table(
        "approval_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("stage_id", sa.String(length=64), nullable=True),
        sa.Column("decision", sa.String(length=64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]),
        sa.ForeignKeyConstraint(["stage_id"], ["migration_stages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_events_run_id", "approval_events", ["run_id"])
    op.create_index("ix_approval_events_stage_id", "approval_events", ["stage_id"])
    op.create_index("ix_approval_events_decision", "approval_events", ["decision"])

    op.create_table(
        "approval_policy_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=64), nullable=False),
        sa.Column("changed_by", sa.String(length=128), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_policy_events_run_id", "approval_policy_events", ["run_id"])

    op.create_table(
        "artifact_metadata",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("stage_id", sa.String(length=64), nullable=True),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]),
        sa.ForeignKeyConstraint(["stage_id"], ["migration_stages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_artifact_metadata_run_id", "artifact_metadata", ["run_id"])
    op.create_index("ix_artifact_metadata_stage_id", "artifact_metadata", ["stage_id"])

    op.create_table(
        "command_executions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("stage_id", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("requested_by", sa.String(length=128), nullable=True),
        sa.Column("executable", sa.String(length=128), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("working_directory_alias", sa.String(length=128), nullable=True),
        sa.Column("runtime_profile_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]),
        sa.ForeignKeyConstraint(["stage_id"], ["migration_stages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_command_executions_run_idempotency"),
    )
    op.create_index("ix_command_executions_run_id", "command_executions", ["run_id"])
    op.create_index("ix_command_executions_stage_id", "command_executions", ["stage_id"])
    op.create_index("ix_command_executions_idempotency_key", "command_executions", ["idempotency_key"])
    op.create_index("ix_command_executions_status", "command_executions", ["status"])

    op.create_table(
        "worker_leases",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_worker_leases_run_id", "worker_leases", ["run_id"])
    op.create_index("ix_worker_leases_expires_at", "worker_leases", ["expires_at"])
    op.create_index("ix_worker_leases_run_owner", "worker_leases", ["run_id", "worker_id"])

    op.create_table(
        "repair_attempts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("stage_id", sa.String(length=64), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("diagnosis", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]),
        sa.ForeignKeyConstraint(["stage_id"], ["migration_stages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "stage_id", "attempt_number", name="uq_repair_attempts_stage_attempt"),
    )
    op.create_index("ix_repair_attempts_run_id", "repair_attempts", ["run_id"])
    op.create_index("ix_repair_attempts_stage_id", "repair_attempts", ["stage_id"])
    op.create_index("ix_repair_attempts_status", "repair_attempts", ["status"])

    op.create_table(
        "llm_usage_records",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("input_price_per_million", sa.Float(), nullable=False),
        sa.Column("output_price_per_million", sa.Float(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_usage_records_run_id", "llm_usage_records", ["run_id"])

    op.create_table(
        "run_assurance_statuses",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("technical_upgrade_status", sa.String(length=64), nullable=False),
        sa.Column("functional_parity_status", sa.String(length=64), nullable=False),
        sa.Column("security_assurance_status", sa.String(length=64), nullable=False),
        sa.Column("quality_assurance_status", sa.String(length=64), nullable=False),
        sa.Column("delivery_readiness", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )


def downgrade() -> None:
    for table_name in (
        "run_assurance_statuses",
        "llm_usage_records",
        "repair_attempts",
        "worker_leases",
        "command_executions",
        "artifact_metadata",
        "approval_policy_events",
        "approval_events",
        "workflow_events",
        "agent_executions",
        "stage_steps",
        "migration_stages",
        "migration_runs",
    ):
        op.drop_table(table_name)
