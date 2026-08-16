"""Persist immutable migration routes (V2 F10-04)."""

from alembic import op
import sqlalchemy as sa


revision = "20260816_53"
down_revision = "20260816_52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "migration_routes",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("source_major", sa.Integer(), nullable=False),
        sa.Column("target_major", sa.Integer(), nullable=False),
        sa.Column("catalogue_version", sa.String(length=128), nullable=False),
        sa.Column("stages", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_migration_routes_run_id", "migration_routes", ["run_id"])
    op.create_index("ix_migration_routes_checksum", "migration_routes", ["checksum"])


def downgrade() -> None:
    op.drop_index("ix_migration_routes_checksum", table_name="migration_routes")
    op.drop_index("ix_migration_routes_run_id", table_name="migration_routes")
    op.drop_table("migration_routes")
