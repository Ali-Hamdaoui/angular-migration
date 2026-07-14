"""Persist path validations and target reservation eligibility."""

from alembic import op
import sqlalchemy as sa

revision = "20260714_03"
down_revision = "20260714_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "path_validations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_path_validation_idempotency"),
    )
    op.create_index("ix_path_validations_status", "path_validations", ["status"])
    op.create_table(
        "target_reservations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("validation_id", sa.String(length=64), nullable=False),
        sa.Column("target_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_target_reservations_validation_id", "target_reservations", ["validation_id"])
    op.create_index("ix_target_reservations_target_path", "target_reservations", ["target_path"])
    op.create_index("ix_target_reservations_status", "target_reservations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_target_reservations_status", table_name="target_reservations")
    op.drop_index("ix_target_reservations_target_path", table_name="target_reservations")
    op.drop_index("ix_target_reservations_validation_id", table_name="target_reservations")
    op.drop_table("target_reservations")
    op.drop_index("ix_path_validations_status", table_name="path_validations")
    op.drop_table("path_validations")