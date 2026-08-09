"""Per-run atomic workflow-event sequence counters (T06).

Workflow-event writers previously allocated sequences with independent
MAX+1 reads, so concurrent appends for one run could collide on
uq_workflow_events_run_sequence. Each run now owns one counter row whose
atomic increment allocates every sequence.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260803_41"
down_revision = "20260803_40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_event_sequences",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"], name="fk_run_event_sequences_run"),
        sa.PrimaryKeyConstraint("run_id", name="pk_run_event_sequences"),
    )
    op.execute(
        """
        INSERT INTO run_event_sequences (run_id, last_sequence)
        SELECT run_id, MAX(sequence)
        FROM workflow_events
        GROUP BY run_id
        """
    )


def downgrade() -> None:
    op.drop_table("run_event_sequences")
