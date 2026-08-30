"""Add plan/generation scope to rebuildable stage-step projections."""

from alembic import op
import sqlalchemy as sa


revision = "20260831_80"
down_revision = "20260827_79"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("stage_steps") as batch:
        batch.add_column(sa.Column("stage_plan_id", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("workspace_generation_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("step_key", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("projection_version", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("source_record_type", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("source_record_id", sa.String(length=128), nullable=True))
        batch.create_index("ix_stage_steps_stage_plan_generation_key", ["stage_plan_id", "workspace_generation_id", "step_key"])
    with op.batch_alter_table("stage_workspace_bindings") as batch:
        batch.add_column(sa.Column("workspace_generation_id", sa.String(length=64), nullable=True))
    with op.batch_alter_table("candidate_promotions") as batch:
        batch.add_column(sa.Column("workspace_generation_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("g12_package_checksum", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("receipt_checksum", sa.String(length=128), nullable=True))
    with op.batch_alter_table("stage_checkpoints") as batch:
        batch.add_column(sa.Column("workspace_generation_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("promotion_receipt_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("g12_package_checksum", sa.String(length=128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("stage_workspace_bindings") as batch:
        batch.drop_column("workspace_generation_id")
    with op.batch_alter_table("candidate_promotions") as batch:
        batch.drop_column("receipt_checksum")
        batch.drop_column("g12_package_checksum")
        batch.drop_column("workspace_generation_id")
    with op.batch_alter_table("stage_checkpoints") as batch:
        batch.drop_column("g12_package_checksum")
        batch.drop_column("promotion_receipt_id")
        batch.drop_column("workspace_generation_id")
    with op.batch_alter_table("stage_steps") as batch:
        batch.drop_index("ix_stage_steps_stage_plan_generation_key")
        batch.drop_column("source_record_id")
        batch.drop_column("source_record_type")
        batch.drop_column("projection_version")
        batch.drop_column("step_key")
        batch.drop_column("workspace_generation_id")
        batch.drop_column("stage_plan_id")
