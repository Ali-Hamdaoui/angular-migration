"""Persist distinct proposer/reviewer Analysis invocation lineage."""

from alembic import op
import sqlalchemy as sa

revision = "20260726_24"
down_revision = "20260725_23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_metadata") as batch:
        batch.add_column(sa.Column("cause_code", sa.String(128), nullable=True))
        batch.add_column(sa.Column("proposer_invocation_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("reviewer_invocation_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("failed_invocation_id", sa.String(64), nullable=True))
        batch.create_foreign_key("fk_analysis_metadata_proposer_invocation", "llm_invocations", ["proposer_invocation_id"], ["id"])
        batch.create_foreign_key("fk_analysis_metadata_reviewer_invocation", "llm_invocations", ["reviewer_invocation_id"], ["id"])
        batch.create_foreign_key("fk_analysis_metadata_failed_invocation", "llm_invocations", ["failed_invocation_id"], ["id"])
    op.execute("UPDATE analysis_metadata SET proposer_invocation_id = invocation_id WHERE proposer_invocation_id IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("analysis_metadata") as batch:
        batch.drop_constraint("fk_analysis_metadata_failed_invocation", type_="foreignkey")
        batch.drop_constraint("fk_analysis_metadata_reviewer_invocation", type_="foreignkey")
        batch.drop_constraint("fk_analysis_metadata_proposer_invocation", type_="foreignkey")
        batch.drop_column("failed_invocation_id")
        batch.drop_column("reviewer_invocation_id")
        batch.drop_column("proposer_invocation_id")
        batch.drop_column("cause_code")
