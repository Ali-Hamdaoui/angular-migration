"""Add command_templates and command_authorization_audits tables for G01 S3-F01.

Adds the structured command registry and authorization audit persistence
required for Sprint 3 governed command runtime.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260719_07"
down_revision = "20260719_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "command_templates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("command_id", sa.String(128), nullable=False, index=True),
        sa.Column("executable", sa.String(128), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False, default=list),
        sa.Column("executable_aliases", sa.JSON(), nullable=False, default=list),
        sa.Column("description", sa.String(512), nullable=False, default=""),
        sa.Column("status", sa.String(32), nullable=False, default="active", index=True),
        sa.Column("version", sa.Integer(), nullable=False, default=1),
        sa.Column("allowed_env_vars", sa.JSON(), nullable=False, default=list),
        sa.Column("max_output_bytes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("command_id", name="uq_command_templates_command_id"),
    )
    op.create_table(
        "command_authorization_audits",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False, index=True),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=True, index=True),
        sa.Column("command_id", sa.String(128), nullable=False, index=True),
        sa.Column("executable", sa.String(128), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False, default=list),
        sa.Column("decision", sa.String(32), nullable=False, index=True),
        sa.Column("reasons", sa.JSON(), nullable=False, default=list),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=True),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, default=list),
        sa.Column("state_version", sa.Integer(), nullable=False, default=1),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_cmd_auth_audit_run_idempotency"),
    )


def downgrade() -> None:
    op.drop_table("command_authorization_audits")
    op.drop_table("command_templates")
