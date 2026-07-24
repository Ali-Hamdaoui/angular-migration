"""Persist safe provider failure evidence for governed LLM calls."""
from alembic import op
import sqlalchemy as sa

revision = "20260724_18"
down_revision = "20260721_17"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("llm_invocations") as batch:
        batch.add_column(sa.Column("provider_http_status", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("provider_error_code", sa.String(128), nullable=True))
        batch.add_column(sa.Column("sanitized_provider_message", sa.Text(), nullable=True))
        batch.add_column(sa.Column("provider_request_id", sa.String(256), nullable=True))
        batch.add_column(sa.Column("failure_stage", sa.String(128), nullable=True))

def downgrade() -> None:
    with op.batch_alter_table("llm_invocations") as batch:
        for name in ("failure_stage", "provider_request_id", "sanitized_provider_message", "provider_error_code", "provider_http_status"):
            batch.drop_column(name)
