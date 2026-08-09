"""Bind command retry attempts without rewriting terminal history."""

from alembic import op
import sqlalchemy as sa


revision = "20260730_37"
down_revision = "20260730_36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("command_executions") as batch:
        batch.add_column(
            sa.Column("parent_execution_id", sa.String(length=64), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "attempt_number",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch.create_foreign_key(
            "fk_command_execution_parent",
            "command_executions",
            ["parent_execution_id"],
            ["id"],
        )
        batch.create_index(
            "ix_command_executions_parent_execution_id",
            ["parent_execution_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("command_executions") as batch:
        batch.drop_index("ix_command_executions_parent_execution_id")
        batch.drop_constraint(
            "fk_command_execution_parent",
            type_="foreignkey",
        )
        batch.drop_column("attempt_number")
        batch.drop_column("parent_execution_id")
