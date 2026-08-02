"""Bind repair attempts to their referenced pre-repair workspace checkpoint."""

from alembic import op
import sqlalchemy as sa


revision = "20260802_38"
down_revision = "20260730_37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("repair_attempts") as batch:
        batch.add_column(sa.Column("checkpoint_id", sa.String(64)))
        batch.create_foreign_key(
            "fk_repair_attempts_checkpoint",
            "stage_checkpoints",
            ["checkpoint_id"],
            ["id"],
        )
        batch.create_index("ix_repair_attempts_checkpoint_id", ["checkpoint_id"])


def downgrade() -> None:
    with op.batch_alter_table("repair_attempts") as batch:
        batch.drop_index("ix_repair_attempts_checkpoint_id")
        batch.drop_constraint("fk_repair_attempts_checkpoint", type_="foreignkey")
        batch.drop_column("checkpoint_id")
