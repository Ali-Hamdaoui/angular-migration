"""Create final assurance, delivery candidate, and report records for G09."""

from alembic import op
import sqlalchemy as sa

revision = "20260719_09"
down_revision = "20260719_06"
branch_labels = None
depends_on = None


def upgrade():
    # Final Assurance records (S4-F12 / G13)
    op.create_table(
        "final_assurance_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("gate_id", sa.String(16), nullable=False),
        sa.Column("gate_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("decision", sa.String(64), nullable=True),
        sa.Column("package_checksum", sa.String(128), nullable=False),
        sa.Column("artifact_set_checksum", sa.String(128), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("package", sa.JSON(), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("stale_reason", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_final_assurance_run_idempotency"),
    )
    op.create_index("ix_final_assurance_records_run_id", "final_assurance_records", ["run_id"])
    op.create_index("ix_final_assurance_records_status", "final_assurance_records", ["status"], if_not_exists=True)

    # Delivery records (S4-F13 / G14)
    op.create_table(
        "delivery_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("gate_id", sa.String(16), nullable=False),
        sa.Column("gate_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("decision", sa.String(64), nullable=True),
        sa.Column("package_checksum", sa.String(128), nullable=False),
        sa.Column("artifact_set_checksum", sa.String(128), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("destination", sa.Text(), nullable=True),
        sa.Column("published_fingerprint", sa.String(128), nullable=True),
        sa.Column("package", sa.JSON(), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("stale_reason", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_delivery_records_run_idempotency"),
    )
    op.create_index("ix_delivery_records_run_id", "delivery_records", ["run_id"])
    op.create_index("ix_delivery_records_status", "delivery_records", ["status"], if_not_exists=True)

    # Report records (S4-F14 / G15)
    op.create_table(
        "report_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("gate_id", sa.String(16), nullable=False),
        sa.Column("gate_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("decision", sa.String(64), nullable=True),
        sa.Column("package_checksum", sa.String(128), nullable=False),
        sa.Column("artifact_set_checksum", sa.String(128), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("report_checksum", sa.String(128), nullable=True),
        sa.Column("narrative_generated", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("package", sa.JSON(), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("stale_reason", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_report_records_run_idempotency"),
    )
    op.create_index("ix_report_records_run_id", "report_records", ["run_id"])
    op.create_index("ix_report_records_status", "report_records", ["status"], if_not_exists=True)


def downgrade():
    op.drop_table("report_records")
    op.drop_table("delivery_records")
    op.drop_table("final_assurance_records")
