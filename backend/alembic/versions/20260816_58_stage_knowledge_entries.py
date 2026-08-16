"""Persist stage knowledge entries (V2 F17-03)."""

from alembic import op
import sqlalchemy as sa


revision = "20260816_58"
down_revision = "20260816_57"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stage_knowledge_entries",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source_major", sa.Integer(), nullable=False),
        sa.Column("target_major", sa.Integer(), nullable=False),
        sa.Column("expected_transforms", sa.JSON(), nullable=False),
        sa.Column("validation_expectations", sa.JSON(), nullable=False),
        sa.Column("expected_dependency_changes", sa.JSON(), nullable=False),
        sa.Column("known_risks", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("change_reason", sa.String(length=512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_major", "target_major", "version", name="uq_stage_knowledge_transition_version"),
    )
    op.create_index("ix_stage_knowledge_source_major", "stage_knowledge_entries", ["source_major"])
    op.create_index("ix_stage_knowledge_target_major", "stage_knowledge_entries", ["target_major"])


def downgrade() -> None:
    op.drop_index("ix_stage_knowledge_target_major", table_name="stage_knowledge_entries")
    op.drop_index("ix_stage_knowledge_source_major", table_name="stage_knowledge_entries")
    op.drop_table("stage_knowledge_entries")
