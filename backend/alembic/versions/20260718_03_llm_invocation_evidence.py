from alembic import op
import sqlalchemy as sa

revision = '20260718_03'
down_revision = '20260718_02'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('llm_invocations',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('run_id', sa.String(64), sa.ForeignKey('migration_runs.id'), nullable=False),
        sa.Column('stage_id', sa.String(64), sa.ForeignKey('migration_stages.id')),
        sa.Column('idempotency_key', sa.String(128), nullable=False),
        sa.Column('request_checksum', sa.String(128), nullable=False),
        sa.Column('correlation_id', sa.String(128), nullable=False),
        sa.Column('actor', sa.String(128), nullable=False),
        sa.Column('role', sa.String(64), nullable=False),
        sa.Column('task_type', sa.String(64), nullable=False),
        sa.Column('provider', sa.String(64), nullable=False),
        sa.Column('deployment_alias', sa.String(128), nullable=False),
        sa.Column('prompt_version', sa.String(128), nullable=False),
        sa.Column('schema_version', sa.String(128), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('failure_code', sa.String(64)),
        sa.Column('artifact_ids', sa.JSON(), nullable=False),
        sa.Column('artifact_checksums', sa.JSON(), nullable=False),
        sa.Column('state_version', sa.Integer(), nullable=False),
        sa.Column('event_sequence', sa.Integer(), nullable=False),
        sa.Column('retries', sa.Integer(), nullable=False),
        sa.Column('latency_ms', sa.Integer()),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('run_id', 'idempotency_key', name='uq_llm_invocations_run_idempotency'))
    op.create_index('ix_llm_invocations_run_id', 'llm_invocations', ['run_id'])
    op.create_index('ix_llm_invocations_status', 'llm_invocations', ['status'])
    op.create_table('usage_cost_records',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('invocation_id', sa.String(64), sa.ForeignKey('llm_invocations.id'), nullable=False, unique=True),
        sa.Column('run_id', sa.String(64), sa.ForeignKey('migration_runs.id'), nullable=False),
        sa.Column('stage_id', sa.String(64), sa.ForeignKey('migration_stages.id')),
        sa.Column('pricing_version', sa.String(128), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('total_tokens', sa.Integer(), nullable=False),
        sa.Column('input_price_per_million', sa.Float(), nullable=False),
        sa.Column('output_price_per_million', sa.Float(), nullable=False),
        sa.Column('input_cost_usd', sa.Float(), nullable=False),
        sa.Column('output_cost_usd', sa.Float(), nullable=False),
        sa.Column('total_cost_usd', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_usage_cost_records_run_id', 'usage_cost_records', ['run_id'])


def downgrade():
    op.drop_index('ix_usage_cost_records_run_id', table_name='usage_cost_records')
    op.drop_table('usage_cost_records')
    op.drop_index('ix_llm_invocations_status', table_name='llm_invocations')
    op.drop_index('ix_llm_invocations_run_id', table_name='llm_invocations')
    op.drop_table('llm_invocations')
