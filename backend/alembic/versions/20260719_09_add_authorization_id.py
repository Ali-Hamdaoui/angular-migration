"""Add authorization_id column to command_executions for G01 gap fix.

The frozen schema command_execution_record.schema.json requires
authorization_id. This migration adds the nullable column to the
existing command_executions table.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260719_09"
down_revision = "20260719_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "command_executions",
        sa.Column("authorization_id", sa.String(64), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_index("ix_command_executions_authorization_id", table_name="command_executions")
    op.drop_column("command_executions", "authorization_id")
