from alembic import op
import sqlalchemy as sa
revision="20260717_01"
down_revision="20260716_05"
branch_labels=None
depends_on=None
def upgrade():
    for table, cols, uniques in [("baseline_assessments",[("id",sa.String(64),False),("run_id",sa.String(64),False),("idempotency_key",sa.String(128),False),("actor",sa.String(128),False),("status",sa.String(64),False),("policy",sa.String(64),False),("policy_version",sa.String(128),False),("blockers",sa.JSON(),False),("warnings",sa.JSON(),False),("known_failures",sa.JSON(),False),("evidence_confidence",sa.JSON(),False),("evidence_set_checksum",sa.String(128),False),("sandbox_fingerprint",sa.String(128),False),("execution_profile_checksum",sa.String(128),False),("source_artifact_ids",sa.JSON(),False),("artifact_ids",sa.JSON(),False),("artifact_checksums",sa.JSON(),False),("package_checksum",sa.String(128),False),("state_version",sa.Integer(),False),("event_sequence",sa.Integer(),False),("created_at",sa.DateTime(timezone=True),False),("updated_at",sa.DateTime(timezone=True),False)],"uq_baseline_assessments_run_idempotency"),("g03_approvals",[("id",sa.String(64),False),("run_id",sa.String(64),False),("gate_id",sa.String(16),False),("gate_version",sa.String(64),False),("idempotency_key",sa.String(128),False),("actor",sa.String(128),False),("status",sa.String(32),False),("decision",sa.String(64),True),("package_checksum",sa.String(128),False),("evidence_set_checksum",sa.String(128),False),("qualification_status",sa.String(64),False),("policy_version",sa.String(128),False),("state_version",sa.Integer(),False),("event_sequence",sa.Integer(),False),("sandbox_fingerprint",sa.String(128),False),("execution_profile_checksum",sa.String(128),False),("package",sa.JSON(),False),("artifact_ids",sa.JSON(),False),("stale_reason",sa.Text(),True),("comment",sa.Text(),True),("created_at",sa.DateTime(timezone=True),False),("updated_at",sa.DateTime(timezone=True),False)],"uq_g03_approvals_run_idempotency")]:
        op.create_table(table,sa.Column(cols[0][0],cols[0][1],primary_key=True,nullable=False),*[sa.Column(n,t,nullable=nullable) for n,t,nullable in cols[1:]],sa.ForeignKeyConstraint(["run_id"],["migration_runs.id"]),sa.UniqueConstraint("run_id","idempotency_key",name=uniques))
        op.create_index("ix_"+table+"_run_id",table,["run_id"])
def downgrade():
    for t in ("g03_approvals","baseline_assessments"):
        op.drop_index("ix_"+t+"_run_id",table_name=t); op.drop_table(t)
