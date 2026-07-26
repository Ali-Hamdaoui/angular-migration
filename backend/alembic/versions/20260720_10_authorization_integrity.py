"""Add authoritative authorization version, payload identity, and trace fields."""

from alembic import op
import sqlalchemy as sa

revision = "20260720_10"
down_revision = "20260719_09"
depends_on = "20260724_20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = (
        ("template_id", sa.String(64)),
        ("template_version", sa.Integer()),
        ("plan_id", sa.String(64)),
        ("plan_version", sa.Integer()),
        ("request_payload_hash", sa.String(128)),
        ("expected_state_version", sa.Integer()),
        ("execution_profile_id", sa.String(128)),
        ("workspace_alias", sa.String(128)),
        ("network_profile", sa.String(64)),
        ("correlation_id", sa.String(128)),
    )
    for name, column_type in columns:
        op.add_column("command_authorization_audits", sa.Column(name, column_type, nullable=True))

    # Existing rows predate this contract. Backfill conservatively; new writes
    # are non-null at the ORM/application boundary.
    op.execute(sa.text("UPDATE command_authorization_audits SET request_payload_hash = 'legacy', expected_state_version = state_version, correlation_id = id WHERE request_payload_hash IS NULL"))
    with op.batch_alter_table("command_authorization_audits") as batch_op:
        batch_op.alter_column("request_payload_hash", nullable=False)
        batch_op.alter_column("expected_state_version", nullable=False)
        batch_op.alter_column("correlation_id", nullable=False)


def downgrade() -> None:
    for name in ("correlation_id", "network_profile", "workspace_alias", "execution_profile_id", "expected_state_version", "request_payload_hash", "plan_version", "plan_id", "template_version", "template_id"):
        op.drop_column("command_authorization_audits", name)
