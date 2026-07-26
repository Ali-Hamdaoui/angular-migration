"""Persist Analysis failure origin and transport boundary metadata."""

from alembic import op
import sqlalchemy as sa

revision = "20260726_25"
down_revision = "20260726_24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_metadata") as batch:
        batch.add_column(sa.Column("failure_origin", sa.String(32), nullable=True))
        batch.add_column(sa.Column("technical_stage", sa.String(128), nullable=True))
        batch.add_column(sa.Column("transport_started", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("provider_request_id", sa.String(256), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("analysis_metadata") as batch:
        for name in ("provider_request_id", "transport_started", "technical_stage", "failure_origin"):
            batch.drop_column(name)
