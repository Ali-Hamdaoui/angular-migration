"""Bind stage recovery operations to their exact Transformer continuation."""

from alembic import op
import sqlalchemy as sa


revision = "20260819_77"
down_revision = "20260819_76"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stage_recovery_operations",
        sa.Column(
            "continuation_id",
            sa.String(length=64),
            sa.ForeignKey("transformation_continuations.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_stage_recovery_operations_continuation_id",
        "stage_recovery_operations",
        ["continuation_id"],
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE stage_recovery_operations AS recovery
            SET continuation_id = (
                SELECT continuation.id
                FROM transformation_continuations AS continuation
                WHERE continuation.run_id = recovery.run_id
                  AND continuation.current_stage_id = recovery.stage_id
            )
            WHERE recovery.continuation_id IS NULL
              AND (
                SELECT COUNT(*)
                FROM transformation_continuations AS continuation
                WHERE continuation.run_id = recovery.run_id
                  AND continuation.current_stage_id = recovery.stage_id
              ) = 1
            """
        )
    )
    missing = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM stage_recovery_operations
            WHERE continuation_id IS NULL
            """
        )
    ).scalar_one()
    if missing:
        raise RuntimeError(
            "Cannot backfill stage recovery continuation identity: "
            f"{missing} row(s) have no unique run/stage continuation"
        )


def downgrade() -> None:
    op.drop_index(
        "ix_stage_recovery_operations_continuation_id",
        table_name="stage_recovery_operations",
    )
    op.drop_column("stage_recovery_operations", "continuation_id")
