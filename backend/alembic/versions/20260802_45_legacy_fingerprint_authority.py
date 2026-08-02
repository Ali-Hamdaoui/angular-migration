"""Legacy fingerprint authority recovery: profile identity and lineage.

Additive schema support for recovering repair authorities whose workspace
fingerprints were persisted before fingerprint-profile identity existed:

* ``stage_workspace_bindings.fingerprint_profile_id``: the canonical profile
  identity of the persisted ``workspace_fingerprint``; NULL marks a legacy
  (pre-profile-identity) binding.
* ``repair_fingerprint_recoveries``: one immutable lineage row per
  (run, stage, attempt, checkpoint) recording the legacy-profile -> current
  profile migration of the authoritative workspace binding.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260802_45"
down_revision = "20260802_44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("stage_workspace_bindings") as batch:
        batch.add_column(sa.Column("fingerprint_profile_id", sa.String(128)))
    op.create_table(
        "repair_fingerprint_recoveries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("attempt_id", sa.String(64), sa.ForeignKey("repair_attempts.id"), nullable=False),
        sa.Column("checkpoint_id", sa.String(64), sa.ForeignKey("stage_checkpoints.id"), nullable=False),
        sa.Column("legacy_profile_id", sa.String(128), nullable=False),
        sa.Column("legacy_fingerprint", sa.String(128), nullable=False),
        sa.Column("replaced_binding_fingerprint", sa.String(128), nullable=False),
        sa.Column("current_profile_id", sa.String(128), nullable=False),
        sa.Column("current_fingerprint", sa.String(128), nullable=False),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "run_id", "stage_id", "attempt_id", "checkpoint_id",
            name="uq_repair_fingerprint_recovery",
        ),
    )
    with op.batch_alter_table("repair_fingerprint_recoveries") as batch:
        batch.create_index("ix_repair_fingerprint_recovery_run", ["run_id"])
        batch.create_index("ix_repair_fingerprint_recovery_stage", ["stage_id"])
        batch.create_index("ix_repair_fingerprint_recovery_attempt", ["attempt_id"])


def downgrade() -> None:
    with op.batch_alter_table("repair_fingerprint_recoveries") as batch:
        batch.drop_index("ix_repair_fingerprint_recovery_attempt")
        batch.drop_index("ix_repair_fingerprint_recovery_stage")
        batch.drop_index("ix_repair_fingerprint_recovery_run")
    op.drop_table("repair_fingerprint_recoveries")
    with op.batch_alter_table("stage_workspace_bindings") as batch:
        batch.drop_column("fingerprint_profile_id")
