"""Register complete immutable metadata for command execution artifacts."""

from alembic import op
import sqlalchemy as sa

revision = "20260720_12"
down_revision = "20260720_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = (
        ("execution_id", sa.String(64)), ("owner_reference", sa.String(128)),
        ("mime_type", sa.String(128)), ("size_bytes", sa.Integer()),
        ("finalized_at", sa.DateTime(timezone=True)), ("immutable", sa.Boolean()),
        ("redacted", sa.Boolean()), ("truncated", sa.Boolean()),
        ("correlation_id", sa.String(128)), ("safe_metadata", sa.JSON()),
    )
    for name, column_type in columns:
        op.add_column("artifact_metadata", sa.Column(name, column_type, nullable=True))
    op.create_index("ix_artifact_metadata_execution_id", "artifact_metadata", ["execution_id"])


def downgrade() -> None:
    op.drop_index("ix_artifact_metadata_execution_id", table_name="artifact_metadata")
    for name in ("safe_metadata", "correlation_id", "truncated", "redacted", "immutable", "finalized_at", "size_bytes", "mime_type", "owner_reference", "execution_id"):
        op.drop_column("artifact_metadata", name)
