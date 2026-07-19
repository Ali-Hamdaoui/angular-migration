"""Align indexes declared by authoritative ORM models."""
from alembic import op
import sqlalchemy as sa
revision = "20260719_02"
down_revision = "20260719_01"
branch_labels = None
depends_on = None
def upgrade():
    for name, table, column in [("ix_baseline_assessments_status", "baseline_assessments", "status"), ("ix_discovery_evidence_status", "discovery_evidence", "status"), ("ix_g03_approvals_status", "g03_approvals", "status"), ("ix_llm_invocations_stage_id", "llm_invocations", "stage_id"), ("ix_parity_baseline_evidence_status", "parity_baseline_evidence", "status"), ("ix_usage_cost_records_stage_id", "usage_cost_records", "stage_id")]:
        op.create_index(name, table, [column])
def downgrade():
    for name, table in [("ix_usage_cost_records_stage_id", "usage_cost_records"), ("ix_parity_baseline_evidence_status", "parity_baseline_evidence"), ("ix_llm_invocations_stage_id", "llm_invocations"), ("ix_g03_approvals_status", "g03_approvals"), ("ix_discovery_evidence_status", "discovery_evidence"), ("ix_baseline_assessments_status", "baseline_assessments")]:
        op.drop_index(name, table_name=table)
