"""Allow preserved source-intake retry attempts per run."""

from alembic import op


revision = "20260721_17"
down_revision = "20260721_16"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("source_intake_jobs") as batch:
        batch.drop_constraint("uq_source_intake_jobs_run", type_="unique")


def downgrade() -> None:
    with op.batch_alter_table("source_intake_jobs") as batch:
        batch.create_unique_constraint("uq_source_intake_jobs_run", ["run_id"])
