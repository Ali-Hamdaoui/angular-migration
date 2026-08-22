"""Bind stage recovery operations to their exact Transformer continuation."""

from alembic import op
import sqlalchemy as sa


revision = "20260819_77"
down_revision = "20260819_76"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    invalid = connection.execute(
        sa.text(
            """
            SELECT recovery.id, COUNT(continuation.id) AS match_count
            FROM stage_recovery_operations AS recovery
            LEFT JOIN transformation_continuations AS continuation
              ON continuation.run_id = recovery.run_id
             AND continuation.current_stage_id = recovery.stage_id
            GROUP BY recovery.id
            HAVING COUNT(continuation.id) <> 1
            """
        )
    ).all()
    if invalid:
        details = ", ".join(f"{row[0]}={row[1]}" for row in invalid)
        raise RuntimeError(
            "Cannot backfill stage recovery continuation identity: "
            f"each recovery must have exactly one run/stage continuation ({details})"
        )

    with op.batch_alter_table("stage_recovery_operations") as batch:
        batch.add_column(sa.Column("continuation_id", sa.String(length=64), nullable=True))
        batch.create_foreign_key(
            "fk_stage_recovery_operations_continuation",
            "transformation_continuations",
            ["continuation_id"],
            ["id"],
        )
        batch.create_index(
            "ix_stage_recovery_operations_continuation_id",
            ["continuation_id"],
        )

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
    with op.batch_alter_table("stage_recovery_operations") as batch:
        batch.drop_index("ix_stage_recovery_operations_continuation_id")
        batch.drop_constraint(
            "fk_stage_recovery_operations_continuation",
            type_="foreignkey",
        )
        batch.drop_column("continuation_id")
