"""Add authoritative AMFA-147 evidence bindings and artifact integrity metadata."""

from alembic import op
import sqlalchemy as sa


revision = "20260720_02"
down_revision = "20260720_01"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("transformation_evidence") as batch:
        batch.add_column(sa.Column("evidence_schema_version", sa.String(64), nullable=False, server_default="transformation-evidence-v2"))
        batch.add_column(sa.Column("angular_update_record_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("angular_update_binding_checksum", sa.String(128), nullable=True))
        batch.add_column(sa.Column("inventory_checksum", sa.String(128), nullable=True))
        batch.add_column(sa.Column("builder_comparison", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        batch.add_column(sa.Column("risk_report", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        batch.add_column(sa.Column("artifact_manifest", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        batch.add_column(sa.Column("artifact_set_checksum", sa.String(128), nullable=True))
        batch.add_column(sa.Column("integrity_status", sa.String(32), nullable=False, server_default="in_progress"))
        batch.add_column(sa.Column("stale_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("failure_code", sa.String(128), nullable=True))
        batch.add_column(sa.Column("computation_started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("computation_completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_transformation_evidence_stage",
            "migration_stages",
            ["stage_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_transformation_evidence_angular_update",
            "angular_update_records",
            ["angular_update_record_id"],
            ["id"],
        )
        batch.create_index("ix_transformation_evidence_integrity_status", ["integrity_status"], unique=False)
        batch.create_index("ix_transformation_evidence_angular_update_record_id", ["angular_update_record_id"], unique=False)
        batch.create_index("ix_transformation_evidence_run_stage_created", ["run_id", "stage_id", "created_at"], unique=False)


def downgrade():
    with op.batch_alter_table("transformation_evidence") as batch:
        batch.drop_index("ix_transformation_evidence_run_stage_created")
        batch.drop_index("ix_transformation_evidence_angular_update_record_id")
        batch.drop_index("ix_transformation_evidence_integrity_status")
        batch.drop_constraint("fk_transformation_evidence_angular_update", type_="foreignkey")
        batch.drop_constraint("fk_transformation_evidence_stage", type_="foreignkey")
        batch.drop_column("computation_completed_at")
        batch.drop_column("computation_started_at")
        batch.drop_column("failure_code")
        batch.drop_column("stale_reason")
        batch.drop_column("integrity_status")
        batch.drop_column("artifact_set_checksum")
        batch.drop_column("artifact_manifest")
        batch.drop_column("risk_report")
        batch.drop_column("builder_comparison")
        batch.drop_column("inventory_checksum")
        batch.drop_column("angular_update_binding_checksum")
        batch.drop_column("angular_update_record_id")
        batch.drop_column("evidence_schema_version")
