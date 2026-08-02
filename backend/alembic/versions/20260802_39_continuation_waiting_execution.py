"""Bind a parked continuation to the exact command execution it waits on."""

from alembic import op
import sqlalchemy as sa


revision = "20260802_39"
down_revision = "20260803_39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("transformation_continuations") as batch:
        batch.add_column(sa.Column("waiting_execution_id", sa.String(64)))
        batch.create_foreign_key(
            "fk_transformation_continuations_waiting_execution",
            "command_executions",
            ["waiting_execution_id"],
            ["id"],
        )
        batch.create_index(
            "ix_transformation_continuations_waiting_execution_id",
            ["waiting_execution_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("transformation_continuations") as batch:
        batch.drop_index("ix_transformation_continuations_waiting_execution_id")
        batch.drop_constraint(
            "fk_transformation_continuations_waiting_execution", type_="foreignkey"
        )
        batch.drop_column("waiting_execution_id")
