"""Add durable Factory runtime generation fencing."""

from alembic import op
import sqlalchemy as sa

revision = "20260819_74"
down_revision = "20260817_73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "factory_runtimes",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("factory_git_sha", sa.String(length=64), nullable=False),
        sa.Column("database_identity", sa.String(length=128), nullable=False),
        sa.Column("alembic_head", sa.String(length=128), nullable=False),
        sa.Column("launcher_pid", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_factory_runtimes_database_identity", "factory_runtimes", ["database_identity"])
    op.create_index("ix_factory_runtimes_status", "factory_runtimes", ["status"])
    op.create_index(
        "uq_factory_runtimes_active_database", "factory_runtimes", ["database_identity"],
        unique=True, sqlite_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_table("factory_runtimes")
