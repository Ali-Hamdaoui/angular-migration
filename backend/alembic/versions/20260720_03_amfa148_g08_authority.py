"""Add authoritative AMFA-148 G08 bindings, lineage, and correlation columns to g08_approvals."""

from alembic import op
import sqlalchemy as sa

revision = "20260720_03"
down_revision = "20260720_02"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("g08_approvals") as batch:
        batch.add_column(
            sa.Column(
                "request_checksum",
                sa.String(128),
                nullable=False,
                server_default=sa.text("'sha256:" + "0" * 64 + "'"),
            )
        )
        batch.add_column(sa.Column("correlation_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("plan_version", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("plan_checksum", sa.String(128), nullable=True))
        batch.add_column(sa.Column("package_artifact_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("parent_gate_record_id", sa.String(64), nullable=True))

    op.create_index(
        "ix_g08_approvals_parent_gate_record_id",
        "g08_approvals",
        ["parent_gate_record_id"],
    )


def downgrade():
    op.drop_index(
        "ix_g08_approvals_parent_gate_record_id",
        table_name="g08_approvals",
    )
    with op.batch_alter_table("g08_approvals") as batch:
        batch.drop_column("parent_gate_record_id")
        batch.drop_column("package_artifact_id")
        batch.drop_column("plan_checksum")
        batch.drop_column("plan_version")
        batch.drop_column("correlation_id")
        batch.drop_column("request_checksum")
