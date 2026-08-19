"""Persist structured stage knowledge rules (V2.1 Section 9)."""

from alembic import op
import sqlalchemy as sa


revision = "20260817_71"
down_revision = "20260817_70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stage_knowledge_entries", sa.Column("dependency_rules", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("stage_knowledge_entries", sa.Column("migration_actions", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("stage_knowledge_entries", "migration_actions")
    op.drop_column("stage_knowledge_entries", "dependency_rules")
