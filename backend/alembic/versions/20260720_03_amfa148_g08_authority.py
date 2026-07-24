"""Add authoritative AMFA-148 G08 bindings and lineage."""
from alembic import op
import sqlalchemy as sa

revision = "20260720_03"
down_revision = "20260719_09"
branch_labels = None
depends_on = None

def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "g08_approvals" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("g08_approvals")}
    with op.batch_alter_table("g08_approvals") as batch:
        if "request_checksum" not in columns: batch.add_column(sa.Column("request_checksum", sa.String(128), nullable=False, server_default=sa.text("'sha256:" + "0" * 64 + "'")))
        if "correlation_id" not in columns: batch.add_column(sa.Column("correlation_id", sa.String(64), nullable=True))
        if "plan_version" not in columns: batch.add_column(sa.Column("plan_version", sa.Integer(), nullable=True))
        if "plan_checksum" not in columns: batch.add_column(sa.Column("plan_checksum", sa.String(128), nullable=True))
        if "package_artifact_id" not in columns: batch.add_column(sa.Column("package_artifact_id", sa.String(64), nullable=True))
        if "parent_gate_record_id" not in columns: batch.add_column(sa.Column("parent_gate_record_id", sa.String(64), nullable=True))
    if "ix_g08_approvals_parent_gate_record_id" not in {index["name"] for index in inspector.get_indexes("g08_approvals")}: op.create_index("ix_g08_approvals_parent_gate_record_id", "g08_approvals", ["parent_gate_record_id"])

def downgrade():
    op.drop_index("ix_g08_approvals_parent_gate_record_id", table_name="g08_approvals")
    with op.batch_alter_table("g08_approvals") as batch:
        for name in ("parent_gate_record_id", "package_artifact_id", "plan_checksum", "plan_version", "correlation_id", "request_checksum"):
            batch.drop_column(name)
