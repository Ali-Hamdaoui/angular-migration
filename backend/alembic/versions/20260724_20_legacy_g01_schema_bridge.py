"""Repair the known legacy DB stamped at 20260720_03 before G01 alters run."""
from alembic import op
import sqlalchemy as sa

revision = "20260724_20"
down_revision = "20260720_03"
branch_labels = None
depends_on = None

def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "command_templates" not in tables:
        op.create_table("command_templates", sa.Column("id", sa.String(64), primary_key=True), sa.Column("command_id", sa.String(128), nullable=False), sa.Column("executable", sa.String(128), nullable=False), sa.Column("arguments", sa.JSON(), nullable=False), sa.Column("executable_aliases", sa.JSON(), nullable=False), sa.Column("description", sa.String(512), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("allowed_env_vars", sa.JSON(), nullable=False), sa.Column("max_output_bytes", sa.Integer()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("command_id", name="uq_command_templates_command_id"))
    if "command_authorization_audits" not in tables:
        op.create_table("command_authorization_audits", sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False), sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id")), sa.Column("command_id", sa.String(128), nullable=False), sa.Column("executable", sa.String(128), nullable=False), sa.Column("arguments", sa.JSON(), nullable=False), sa.Column("decision", sa.String(32), nullable=False), sa.Column("reasons", sa.JSON(), nullable=False), sa.Column("policy_version", sa.String(64), nullable=False), sa.Column("idempotency_key", sa.String(128), nullable=False), sa.Column("actor", sa.String(128)), sa.Column("artifact_ids", sa.JSON(), nullable=False), sa.Column("state_version", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("run_id", "idempotency_key", name="uq_cmd_auth_audit_run_idempotency"))

def downgrade():
    pass
