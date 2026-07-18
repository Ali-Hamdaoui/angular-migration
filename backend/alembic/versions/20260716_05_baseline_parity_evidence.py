"""Persist S1-F13 baseline parity evidence."""
from alembic import op
import sqlalchemy as sa
revision = "20260716_05"
down_revision = "20260716_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("baseline_parity_evidence",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False), sa.Column("actor", sa.String(128), nullable=False), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("parser_version", sa.String(128), nullable=False), sa.Column("schema_version", sa.String(128), nullable=False), sa.Column("baseline_checksum", sa.String(128)),
        sa.Column("runtime_profile_id", sa.String(128)), sa.Column("runtime_checksum", sa.String(128)), sa.Column("failures", sa.JSON(), nullable=False),
        sa.Column("routes", sa.JSON(), nullable=False), sa.Column("backend_integration", sa.JSON(), nullable=False), sa.Column("anchors", sa.JSON(), nullable=False),
        sa.Column("diagnostics", sa.JSON(), nullable=False), sa.Column("confidence", sa.JSON(), nullable=False), sa.Column("source_artifact_ids", sa.JSON(), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False), sa.Column("artifact_checksums", sa.JSON(), nullable=False), sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_baseline_parity_run_idempotency"))
    op.create_index("ix_baseline_parity_evidence_run_id", "baseline_parity_evidence", ["run_id"])
    op.create_index("ix_baseline_parity_evidence_status", "baseline_parity_evidence", ["status"])


def downgrade() -> None:
    op.drop_index("ix_baseline_parity_evidence_status", table_name="baseline_parity_evidence")
    op.drop_index("ix_baseline_parity_evidence_run_id", table_name="baseline_parity_evidence")
    op.drop_table("baseline_parity_evidence")
