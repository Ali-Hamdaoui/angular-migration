"""Persist authoritative run bindings, policy snapshots, and active claims."""

from alembic import op
import sqlalchemy as sa

revision = "20260715_01"
down_revision = "20260714_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, column in (
        ("preflight_id", sa.String(64)),
        ("source_path", sa.Text()),
        ("target_output_path", sa.Text()),
        ("graph_thread_id", sa.String(128)),
        ("client_constraints", sa.JSON()),
        ("target_policy_snapshot", sa.JSON()),
        ("run_policy_snapshot", sa.JSON()),
        ("pricing_snapshot", sa.JSON()),
        ("actor", sa.String(128)),
    ):
        op.add_column("migration_runs", sa.Column(name, column, nullable=True))
    op.create_index("ix_migration_runs_preflight_id", "migration_runs", ["preflight_id"])
    op.create_index("uq_migration_runs_graph_thread", "migration_runs", ["graph_thread_id"], unique=True)
    op.create_table(
        "active_run_claims",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("target_output_path", sa.Text(), nullable=False),
        sa.Column("lease_owner", sa.String(128), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", name="uq_active_run_claim_run"),
        sa.UniqueConstraint("target_output_path", name="uq_active_run_claim_target"),
    )
    op.create_index("ix_active_run_claims_run_id", "active_run_claims", ["run_id"])
    op.create_index("ix_active_run_claims_expires_at", "active_run_claims", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_active_run_claims_expires_at", table_name="active_run_claims")
    op.drop_index("ix_active_run_claims_run_id", table_name="active_run_claims")
    op.drop_table("active_run_claims")
    op.drop_index("uq_migration_runs_graph_thread", table_name="migration_runs")
    op.drop_index("ix_migration_runs_preflight_id", table_name="migration_runs")
    for name in ("actor", "pricing_snapshot", "run_policy_snapshot", "target_policy_snapshot", "client_constraints", "graph_thread_id", "target_output_path", "source_path", "preflight_id"):
        op.drop_column("migration_runs", name)
