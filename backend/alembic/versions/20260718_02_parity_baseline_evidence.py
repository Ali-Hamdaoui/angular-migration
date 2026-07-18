from alembic import op
import sqlalchemy as sa

revision = "20260718_02"
down_revision = "20260718_01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "parity_baseline_evidence",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_checksum", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("artifact_checksums", sa.JSON(), nullable=False),
        sa.Column("prerequisite_artifact_ids", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(128)),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_parity_baseline_run_idempotency"),
    )
    op.create_index("ix_parity_baseline_evidence_run_id", "parity_baseline_evidence", ["run_id"])


def downgrade():
    op.drop_index("ix_parity_baseline_evidence_run_id", table_name="parity_baseline_evidence")
    op.drop_table("parity_baseline_evidence")
