"""Add evidence fingerprint columns to transformation_evidence."""

from alembic import op
import sqlalchemy as sa


revision = "20260720_01"
down_revision = "20260719_07"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("transformation_evidence", sa.Column("correlation_id", sa.String(64), nullable=True))
    op.add_column("transformation_evidence", sa.Column("input_fingerprint", sa.String(128), nullable=True))
    op.add_column("transformation_evidence", sa.Column("target_fingerprint", sa.String(128), nullable=True))
    op.add_column("transformation_evidence", sa.Column("request_checksum", sa.String(128), nullable=True))
    op.add_column("transformation_evidence", sa.Column("gate_version", sa.String(32), nullable=False, server_default="g03-evidence-v1"))
    op.add_column("transformation_evidence", sa.Column("source_sandbox_path", sa.String(512), nullable=True))
    op.add_column("transformation_evidence", sa.Column("target_sandbox_path", sa.String(512), nullable=True))


def downgrade():
    op.drop_column("transformation_evidence", "target_sandbox_path")
    op.drop_column("transformation_evidence", "source_sandbox_path")
    op.drop_column("transformation_evidence", "gate_version")
    op.drop_column("transformation_evidence", "request_checksum")
    op.drop_column("transformation_evidence", "target_fingerprint")
    op.drop_column("transformation_evidence", "input_fingerprint")
    op.drop_column("transformation_evidence", "correlation_id")
