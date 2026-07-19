"""Add reconciliation and assistant tables for G08.

Revision ID: 20260720_01_reconciliation_assistant
Revises: 20260719_06_planning_review_evidence
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260720_01_reconciliation_assistant"
down_revision: str | None = "20260719_06_planning_review_evidence"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Reconciliation runs
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("backend_instance_id", sa.String(128), nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stale_leases_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("interrupted_commands_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("artifact_mismatches_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("recovered_runs", sa.Integer, nullable=False, server_default="0"),
        sa.Column("quarantined_runs", sa.Integer, nullable=False, server_default="0"),
        sa.Column("graph_reconstructed", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("artifact_ids", sa.JSON, nullable=True),
        sa.Column("errors", sa.JSON, nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True, index=True),
    )
    # Artifact integrity findings
    op.create_table(
        "artifact_integrity_findings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("reconciliation_id", sa.String(64), sa.ForeignKey("reconciliation_runs.id"), nullable=False, index=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=True, index=True),
        sa.Column("artifact_id", sa.String(128), nullable=True),
        sa.Column("expected_checksum", sa.String(128), nullable=True),
        sa.Column("actual_checksum", sa.String(128), nullable=True),
        sa.Column("file_path", sa.Text, nullable=True),
        sa.Column("finding_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Assistant conversations
    op.create_table(
        "assistant_conversations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False, index=True),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("artifact_ids", sa.JSON, nullable=True),
        sa.Column("state_version", sa.Integer, nullable=False, server_default="1"),
    )
    # Assistant messages
    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("conversation_id", sa.String(64), sa.ForeignKey("assistant_conversations.id"), nullable=False, index=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False, index=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content_summary", sa.Text, nullable=True),
        sa.Column("artifact_refs", sa.JSON, nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("assistant_messages")
    op.drop_table("assistant_conversations")
    op.drop_table("artifact_integrity_findings")
    op.drop_table("reconciliation_runs")
