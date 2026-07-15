"""Persist source-compatible execution profile resolutions."""
from alembic import op
import sqlalchemy as sa
revision="20260715_05"
down_revision="20260715_04"
branch_labels=None
depends_on=None
def upgrade():
    op.create_table("execution_profiles",sa.Column("id",sa.String(64),primary_key=True),sa.Column("run_id",sa.String(64),sa.ForeignKey("migration_runs.id"),nullable=False),sa.Column("idempotency_key",sa.String(128),nullable=False),sa.Column("request_checksum",sa.String(128),nullable=False),sa.Column("policy_version",sa.String(128),nullable=False),sa.Column("status",sa.String(32),nullable=False),sa.Column("source_angular_exact",sa.String(64),nullable=False),sa.Column("selected_profile_id",sa.String(128)),sa.Column("selected_checksum",sa.String(128)),sa.Column("profiles",sa.JSON(),nullable=False),sa.Column("blockers",sa.JSON(),nullable=False),sa.Column("guidance",sa.JSON(),nullable=False),sa.Column("artifact_ids",sa.JSON(),nullable=False),sa.Column("state_version",sa.Integer(),nullable=False),sa.Column("event_sequence",sa.Integer(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("run_id","idempotency_key",name="uq_execution_profiles_run_idempotency"))
    op.create_index("ix_execution_profiles_run_id","execution_profiles",["run_id"]); op.create_index("ix_execution_profiles_status","execution_profiles",["status"])
def downgrade():
    op.drop_index("ix_execution_profiles_status",table_name="execution_profiles"); op.drop_index("ix_execution_profiles_run_id",table_name="execution_profiles"); op.drop_table("execution_profiles")
