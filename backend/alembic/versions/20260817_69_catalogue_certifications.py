"""Persist catalogue certification evidence (V2 F30-04)."""

from alembic import op
import sqlalchemy as sa


revision = "20260817_69"
down_revision = "20260817_68"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalogue_certifications",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("source_family", sa.String(length=32), nullable=False),
        sa.Column("target_family", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("runtime_proof", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("catalogue_version", sa.String(length=128), nullable=False),
        sa.Column("deterministic", sa.Boolean(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_family", "target_family", "run_id", name="uq_catalogue_cert_source_target_run"),
    )
    op.create_index("ix_catalogue_certifications_run_id", "catalogue_certifications", ["run_id"])
    op.create_index("ix_catalogue_certifications_source_family", "catalogue_certifications", ["source_family"])
    op.create_index("ix_catalogue_certifications_target_family", "catalogue_certifications", ["target_family"])
    op.create_index("ix_catalogue_certifications_status", "catalogue_certifications", ["status"])


def downgrade() -> None:
    op.drop_index("ix_catalogue_certifications_status", table_name="catalogue_certifications")
    op.drop_index("ix_catalogue_certifications_target_family", table_name="catalogue_certifications")
    op.drop_index("ix_catalogue_certifications_source_family", table_name="catalogue_certifications")
    op.drop_index("ix_catalogue_certifications_run_id", table_name="catalogue_certifications")
    op.drop_table("catalogue_certifications")
