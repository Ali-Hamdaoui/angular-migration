"""Allow immutable command-template versions to coexist."""

from alembic import op


revision = "20260727_31"
down_revision = "20260727_30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("command_templates") as batch:
        batch.drop_constraint("uq_command_templates_command_id", type_="unique")
        batch.create_unique_constraint("uq_command_templates_command_version", ["command_id", "version"])


def downgrade() -> None:
    with op.batch_alter_table("command_templates") as batch:
        batch.drop_constraint("uq_command_templates_command_version", type_="unique")
        batch.create_unique_constraint("uq_command_templates_command_id", ["command_id"])
