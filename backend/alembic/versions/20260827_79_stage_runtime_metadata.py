"""Persist the complete runtime descriptor used by stage evidence."""

from alembic import op
import sqlalchemy as sa


revision = "20260827_79"
down_revision = "20260819_78"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("stage_runtime_bindings") as batch:
        batch.add_column(sa.Column("operating_system", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("architecture", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("installation_root", sa.String(length=1024), nullable=True))
        batch.add_column(sa.Column("installation_variant", sa.String(length=128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("stage_runtime_bindings") as batch:
        batch.drop_column("installation_variant")
        batch.drop_column("installation_root")
        batch.drop_column("architecture")
        batch.drop_column("operating_system")
