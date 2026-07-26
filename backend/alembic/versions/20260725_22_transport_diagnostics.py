"""Persist safe transport diagnostics for LLM invocations."""

from alembic import op
import sqlalchemy as sa

revision = "20260725_22"
down_revision = "20260725_21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("llm_invocations") as batch:
        batch.add_column(sa.Column("transport_category", sa.String(64), nullable=True))
        batch.add_column(sa.Column("transport_exception_type", sa.String(128), nullable=True))
        batch.add_column(sa.Column("endpoint_host", sa.String(255), nullable=True))
        batch.add_column(sa.Column("endpoint_path", sa.String(128), nullable=True))
        batch.add_column(sa.Column("retryable", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("response_received", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("response_content_type", sa.String(128), nullable=True))
        batch.add_column(sa.Column("response_bytes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("response_sha256", sa.String(128), nullable=True))
        batch.add_column(sa.Column("response_kind", sa.String(32), nullable=True))
        batch.add_column(sa.Column("transport_started", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("llm_invocations") as batch:
        for name in ("transport_started", "response_kind", "response_sha256", "response_bytes", "response_content_type", "response_received", "retryable", "endpoint_path", "endpoint_host", "transport_exception_type", "transport_category"):
            batch.drop_column(name)
