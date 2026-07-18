"""Persist external generated-output layout aliases for migration runs."""

from alembic import op
import sqlalchemy as sa

revision = "20260715_02"
down_revision = "20260715_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, column in (
        ("target_parent_path", sa.Text()), ("generated_output_name", sa.String(255)),
        ("resolved_output_root", sa.Text()), ("run_root", sa.Text()), ("artifact_root", sa.Text()),
        ("log_root", sa.Text()), ("report_root", sa.Text()), ("temporary_root", sa.Text()),
        ("migrated_app_path", sa.Text()), ("workspace_aliases", sa.JSON()),
        ("output_layout_version", sa.String(64)),
    ):
        op.add_column("migration_runs", sa.Column(name, column, nullable=True))
    op.create_index("ix_migration_runs_resolved_output_root", "migration_runs", ["resolved_output_root"])


def downgrade() -> None:
    op.drop_index("ix_migration_runs_resolved_output_root", table_name="migration_runs")
    for name in ("output_layout_version", "workspace_aliases", "migrated_app_path", "temporary_root", "report_root", "log_root", "artifact_root", "run_root", "resolved_output_root", "generated_output_name", "target_parent_path"):
        op.drop_column("migration_runs", name)

