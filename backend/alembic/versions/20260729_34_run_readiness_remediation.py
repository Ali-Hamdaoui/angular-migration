"""Repair run-readiness persistence and durable Planning review outcomes."""

from alembic import op
import re
import sqlalchemy as sa


revision = "20260729_34"
down_revision = "20260729_33"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("planning_reviews", sa.Column("proposer_output", sa.JSON(), nullable=True))
    op.add_column("planning_reviews", sa.Column("reviewer_output", sa.JSON(), nullable=True))
    op.add_column("planning_reviews", sa.Column("revision_count", sa.Integer(), nullable=True))
    op.add_column("planning_reviews", sa.Column("outcome", sa.String(length=64), nullable=True))
    op.create_index("ix_planning_reviews_outcome", "planning_reviews", ["outcome"], unique=False)
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE planning_reviews
            SET outcome = CASE
                WHEN status = 'completed' THEN 'accept'
                WHEN error_code = 'PLANNING_REVIEW_NOT_ACCEPTED' THEN 'unknown_nonaccept'
                ELSE outcome
            END
            WHERE outcome IS NULL
            """
        )
    )
    rows = bind.execute(
        sa.text(
            """
            SELECT artifacts.run_id, artifacts.stage_id, MIN(artifacts.created_at) AS created_at
            FROM artifact_metadata AS artifacts
            LEFT JOIN migration_stages AS stages ON stages.id = artifacts.stage_id
            WHERE artifacts.stage_id IS NOT NULL
              AND artifacts.relative_path LIKE 'stages/%'
              AND stages.id IS NULL
            GROUP BY artifacts.run_id, artifacts.stage_id
            ORDER BY artifacts.run_id, artifacts.stage_id
            """
        )
    ).mappings()
    next_orders: dict[str, int] = {}
    for row in rows:
        run_id = str(row["run_id"])
        if run_id not in next_orders:
            next_orders[run_id] = int(
                bind.execute(
                    sa.text(
                        "SELECT COALESCE(MAX(stage_order), 0) FROM migration_stages WHERE run_id = :run_id"
                    ),
                    {"run_id": run_id},
                ).scalar_one()
            )
        next_orders[run_id] += 1
        source_family, target_family = _version_families(str(row["stage_id"]))
        bind.execute(
            sa.text(
                """
                INSERT INTO migration_stages (
                    id, run_id, stage_order, source_version_family, target_version_family,
                    source_version_detected, target_version_resolved,
                    source_angular_version, target_angular_version,
                    status, current_agent, created_at, started_at, completed_at
                ) VALUES (
                    :id, :run_id, :stage_order, :source_family, :target_family,
                    NULL, NULL, NULL, NULL, 'planned', NULL, :created_at, NULL, NULL
                )
                """
            ),
            {
                "id": row["stage_id"],
                "run_id": run_id,
                "stage_order": next_orders[run_id],
                "source_family": source_family,
                "target_family": target_family,
                "created_at": row["created_at"],
            },
        )


def downgrade() -> None:
    # Historical parent rows are retained because deleting them would recreate
    # the foreign-key corruption this migration repairs.
    op.drop_index("ix_planning_reviews_outcome", table_name="planning_reviews")
    op.drop_column("planning_reviews", "outcome")
    op.drop_column("planning_reviews", "revision_count")
    op.drop_column("planning_reviews", "reviewer_output")
    op.drop_column("planning_reviews", "proposer_output")


def _version_families(stage_id: str) -> tuple[str | None, str | None]:
    match = re.fullmatch(r"angular-(\d+)-to-(\d+)", stage_id)
    if match is None:
        return None, None
    return f"angular-{match.group(1)}.x", f"angular-{match.group(2)}.x"
