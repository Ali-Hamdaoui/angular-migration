"""Add repair proposer, reviewer, and G10 tables for G06 capability.

Revision ID: 695779d2b9ee
Revises: 20260719_08
Create Date: 2026-07-19 21:47:24.416541
"""
from alembic import op
import sqlalchemy as sa

revision = '695779d2b9ee'
down_revision = '20260719_08'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # proposer_results - Repair Proposer invocation and result metadata
    op.create_table('proposer_results',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('repair_attempt_id', sa.String(length=64), nullable=False),
        sa.Column('stage_id', sa.String(length=64), nullable=True),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('actor', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=64), nullable=False),
        sa.Column('proposer_invocation_id', sa.String(length=128), nullable=False),
        sa.Column('diagnosis', sa.JSON(), nullable=False),
        sa.Column('candidate', sa.JSON(), nullable=True),
        sa.Column('diff_checksum', sa.String(length=128), nullable=True),
        sa.Column('changed_files', sa.JSON(), nullable=False),
        sa.Column('artifact_set_checksum', sa.String(length=128), nullable=False),
        sa.Column('proposer_output_checksum', sa.String(length=128), nullable=False),
        sa.Column('model_provenance', sa.JSON(), nullable=False),
        sa.Column('usage', sa.JSON(), nullable=False),
        sa.Column('prompt_version', sa.String(length=128), nullable=False),
        sa.Column('schema_version', sa.String(length=128), nullable=False),
        sa.Column('workspace_fingerprint', sa.String(length=128), nullable=False),
        sa.Column('state_version', sa.Integer(), nullable=False),
        sa.Column('event_sequence', sa.Integer(), nullable=False),
        sa.Column('revision_of', sa.String(length=64), nullable=True),
        sa.Column('revision_count', sa.Integer(), nullable=False),
        sa.Column('failure_code', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['migration_runs.id'], ),
        sa.ForeignKeyConstraint(['stage_id'], ['migration_stages.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'repair_attempt_id', 'idempotency_key', name='uq_proposer_results_run_attempt_idempotency')
    )
    op.create_index(op.f('ix_proposer_results_run_id'), 'proposer_results', ['run_id'], unique=False)
    op.create_index(op.f('ix_proposer_results_repair_attempt_id'), 'proposer_results', ['repair_attempt_id'], unique=False)
    op.create_index(op.f('ix_proposer_results_stage_id'), 'proposer_results', ['stage_id'], unique=False)
    op.create_index(op.f('ix_proposer_results_status'), 'proposer_results', ['status'], unique=False)

    # review_decisions - Non-authoring Reviewer results
    op.create_table('review_decisions',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('repair_attempt_id', sa.String(length=64), nullable=False),
        sa.Column('stage_id', sa.String(length=64), nullable=True),
        sa.Column('proposal_id', sa.String(length=64), nullable=False),
        sa.Column('reviewer_invocation_id', sa.String(length=128), nullable=False),
        sa.Column('decision', sa.String(length=64), nullable=False),
        sa.Column('proposal_diff_checksum', sa.String(length=128), nullable=False),
        sa.Column('review_checksum', sa.String(length=128), nullable=False),
        sa.Column('critique', sa.JSON(), nullable=False),
        sa.Column('revision_instructions', sa.JSON(), nullable=False),
        sa.Column('requested_context', sa.JSON(), nullable=False),
        sa.Column('role', sa.String(length=64), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('actor', sa.String(length=128), nullable=False),
        sa.Column('model_provenance', sa.JSON(), nullable=False),
        sa.Column('usage', sa.JSON(), nullable=False),
        sa.Column('state_version', sa.Integer(), nullable=False),
        sa.Column('event_sequence', sa.Integer(), nullable=False),
        sa.Column('revision_of', sa.String(length=64), nullable=True),
        sa.Column('revision_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['migration_runs.id'], ),
        sa.ForeignKeyConstraint(['stage_id'], ['migration_stages.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'proposal_id', 'reviewer_invocation_id', name='uq_review_decisions_run_proposal_invocation')
    )
    op.create_index(op.f('ix_review_decisions_run_id'), 'review_decisions', ['run_id'], unique=False)
    op.create_index(op.f('ix_review_decisions_repair_attempt_id'), 'review_decisions', ['repair_attempt_id'], unique=False)
    op.create_index(op.f('ix_review_decisions_stage_id'), 'review_decisions', ['stage_id'], unique=False)
    op.create_index(op.f('ix_review_decisions_proposal_id'), 'review_decisions', ['proposal_id'], unique=False)
    op.create_index(op.f('ix_review_decisions_decision'), 'review_decisions', ['decision'], unique=False)

    # repair_proposals - Accepted proposal and G10 gate state
    op.create_table('repair_proposals',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('repair_attempt_id', sa.String(length=64), nullable=False),
        sa.Column('proposal_id', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=64), nullable=False),
        sa.Column('diff_checksum', sa.String(length=128), nullable=False),
        sa.Column('workspace_fingerprint', sa.String(length=128), nullable=False),
        sa.Column('lineage_checksum', sa.String(length=128), nullable=False),
        sa.Column('g10_status', sa.String(length=64), nullable=False),
        sa.Column('g10_decision', sa.String(length=64), nullable=True),
        sa.Column('g10_approval_id', sa.String(length=64), nullable=True),
        sa.Column('g10_decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('g10_actor', sa.String(length=128), nullable=True),
        sa.Column('g10_rationale', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('actor', sa.String(length=128), nullable=False),
        sa.Column('state_version', sa.Integer(), nullable=False),
        sa.Column('event_sequence', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['migration_runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'proposal_id', name='uq_repair_proposals_run_proposal')
    )
    op.create_index(op.f('ix_repair_proposals_run_id'), 'repair_proposals', ['run_id'], unique=False)
    op.create_index(op.f('ix_repair_proposals_repair_attempt_id'), 'repair_proposals', ['repair_attempt_id'], unique=False)
    op.create_index(op.f('ix_repair_proposals_proposal_id'), 'repair_proposals', ['proposal_id'], unique=False)
    op.create_index(op.f('ix_repair_proposals_status'), 'repair_proposals', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_repair_proposals_status'), table_name='repair_proposals')
    op.drop_index(op.f('ix_repair_proposals_proposal_id'), table_name='repair_proposals')
    op.drop_index(op.f('ix_repair_proposals_repair_attempt_id'), table_name='repair_proposals')
    op.drop_index(op.f('ix_repair_proposals_run_id'), table_name='repair_proposals')
    op.drop_table('repair_proposals')
    op.drop_index(op.f('ix_review_decisions_decision'), table_name='review_decisions')
    op.drop_index(op.f('ix_review_decisions_proposal_id'), table_name='review_decisions')
    op.drop_index(op.f('ix_review_decisions_repair_attempt_id'), table_name='review_decisions')
    op.drop_index(op.f('ix_review_decisions_run_id'), table_name='review_decisions')
    op.drop_index(op.f('ix_review_decisions_stage_id'), table_name='review_decisions')
    op.drop_table('review_decisions')
    op.drop_index(op.f('ix_proposer_results_status'), table_name='proposer_results')
    op.drop_index(op.f('ix_proposer_results_stage_id'), table_name='proposer_results')
    op.drop_index(op.f('ix_proposer_results_repair_attempt_id'), table_name='proposer_results')
    op.drop_index(op.f('ix_proposer_results_run_id'), table_name='proposer_results')
    op.drop_table('proposer_results')
