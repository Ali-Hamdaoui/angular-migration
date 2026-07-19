"""Create G04 stage validation, build, test, assurance, seal, and approval gate tables."""
from alembic import op
import sqlalchemy as sa

revision = "20260719_07"
down_revision = "20260719_06"
branch_labels = None
depends_on = None


def upgrade():
    # Stage validations (S3-F10)
    op.create_table(
        "stage_validations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("step_config", sa.JSON()),
        sa.Column("install_status", sa.String(32)),
        sa.Column("static_checks_status", sa.String(32)),
        sa.Column("aggregate_result", sa.JSON()),
        sa.Column("install_log_artifact_id", sa.String(128)),
        sa.Column("static_checks_report_artifact_id", sa.String(128)),
        sa.Column("dependency_tree_artifact_id", sa.String(128)),
        sa.Column("validation_summary_artifact_id", sa.String(128)),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, default=list),
        sa.Column("artifact_checksums", sa.JSON(), nullable=False, default=dict),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "stage_id", name="uq_stage_validations_run_stage"),
    )
    op.create_index("ix_stage_validations_run_id", "stage_validations", ["run_id"])
    op.create_index("ix_stage_validations_stage_id", "stage_validations", ["stage_id"])
    op.create_index("ix_stage_validations_status", "stage_validations", ["status"])

    # Stage builds (S3-F11)
    op.create_table(
        "stage_builds",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("per_target_statuses", sa.JSON(), nullable=False, default=list),
        sa.Column("results", sa.JSON(), nullable=False, default=list),
        sa.Column("parser_summary", sa.JSON()),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, default=list),
        sa.Column("artifact_checksums", sa.JSON(), nullable=False, default=dict),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "stage_id", name="uq_stage_builds_run_stage"),
    )
    op.create_index("ix_stage_builds_run_id", "stage_builds", ["run_id"])
    op.create_index("ix_stage_builds_stage_id", "stage_builds", ["stage_id"])
    op.create_index("ix_stage_builds_status", "stage_builds", ["status"])

    # Stage tests (S3-F12)
    op.create_table(
        "stage_tests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("test_status", sa.String(32)),
        sa.Column("lint_status", sa.String(32)),
        sa.Column("test_results", sa.JSON(), nullable=False, default=list),
        sa.Column("lint_results", sa.JSON(), nullable=False, default=list),
        sa.Column("failure_comparison", sa.JSON()),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, default=list),
        sa.Column("artifact_checksums", sa.JSON(), nullable=False, default=dict),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "stage_id", name="uq_stage_tests_run_stage"),
    )
    op.create_index("ix_stage_tests_run_id", "stage_tests", ["run_id"])
    op.create_index("ix_stage_tests_stage_id", "stage_tests", ["stage_id"])
    op.create_index("ix_stage_tests_status", "stage_tests", ["status"])

    # Stage assurances (S3-F13)
    op.create_table(
        "stage_assurances",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("comparison_summary", sa.JSON()),
        sa.Column("assurance_dimensions", sa.JSON()),
        sa.Column("route_comparison_artifact_id", sa.String(128)),
        sa.Column("backend_comparison_artifact_id", sa.String(128)),
        sa.Column("risk_rollup_artifact_id", sa.String(128)),
        sa.Column("parity_checklist_artifact_id", sa.String(128)),
        sa.Column("assurance_summary_artifact_id", sa.String(128)),
        sa.Column("g09_package_artifact_id", sa.String(128)),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, default=list),
        sa.Column("artifact_checksums", sa.JSON(), nullable=False, default=dict),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "stage_id", name="uq_stage_assurances_run_stage"),
    )
    op.create_index("ix_stage_assurances_run_id", "stage_assurances", ["run_id"])
    op.create_index("ix_stage_assurances_stage_id", "stage_assurances", ["stage_id"])
    op.create_index("ix_stage_assurances_status", "stage_assurances", ["status"])

    # G09 approvals
    op.create_table(
        "g09_approvals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("gate_id", sa.String(16), nullable=False),
        sa.Column("gate_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(64)),
        sa.Column("package_checksum", sa.String(128), nullable=False),
        sa.Column("artifact_set_checksum", sa.String(128), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(128)),
        sa.Column("plan_version", sa.String(128)),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, default=list),
        sa.Column("comment", sa.Text()),
        sa.Column("stale_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_g09_approvals_run_idempotency"),
    )
    op.create_index("ix_g09_approvals_run_id", "g09_approvals", ["run_id"])
    op.create_index("ix_g09_approvals_status", "g09_approvals", ["status"])

    # Stage seals (S3-F14)
    op.create_table(
        "stage_seals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("output_fingerprint", sa.JSON()),
        sa.Column("completeness_report", sa.JSON()),
        sa.Column("cleanup_report_artifact_id", sa.String(128)),
        sa.Column("cleanliness_report_artifact_id", sa.String(128)),
        sa.Column("output_manifest_artifact_id", sa.String(128)),
        sa.Column("stage_evidence_index_artifact_id", sa.String(128)),
        sa.Column("g12_package_artifact_id", sa.String(128)),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, default=list),
        sa.Column("artifact_checksums", sa.JSON(), nullable=False, default=dict),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "stage_id", name="uq_stage_seals_run_stage"),
    )
    op.create_index("ix_stage_seals_run_id", "stage_seals", ["run_id"])
    op.create_index("ix_stage_seals_stage_id", "stage_seals", ["stage_id"])
    op.create_index("ix_stage_seals_status", "stage_seals", ["status"])

    # G12 approvals
    op.create_table(
        "g12_approvals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("gate_id", sa.String(16), nullable=False),
        sa.Column("gate_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(64)),
        sa.Column("package_checksum", sa.String(128), nullable=False),
        sa.Column("artifact_set_checksum", sa.String(128), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(128)),
        sa.Column("plan_version", sa.String(128)),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, default=list),
        sa.Column("comment", sa.Text()),
        sa.Column("stale_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_g12_approvals_run_idempotency"),
    )
    op.create_index("ix_g12_approvals_run_id", "g12_approvals", ["run_id"])
    op.create_index("ix_g12_approvals_status", "g12_approvals", ["status"])

    # Stage copy-forward records
    op.create_table(
        "stage_copy_forward_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("source_stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("target_stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("next_stage_created", sa.Boolean(), nullable=False, default=False),
        sa.Column("sandbox_ready", sa.Boolean(), nullable=False, default=False),
        sa.Column("artifact_ids", sa.JSON(), nullable=False, default=list),
        sa.Column("artifact_checksums", sa.JSON(), nullable=False, default=dict),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "source_stage_id", name="uq_copy_forward_run_source"),
    )
    op.create_index("ix_copy_forward_run_id", "stage_copy_forward_records", ["run_id"])
    op.create_index("ix_copy_forward_source", "stage_copy_forward_records", ["source_stage_id"])
    op.create_index("ix_copy_forward_target", "stage_copy_forward_records", ["target_stage_id"])
    op.create_index("ix_copy_forward_status", "stage_copy_forward_records", ["status"])

    # Output fingerprints
    op.create_table(
        "output_fingerprints",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("fingerprint", sa.JSON(), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False, default=0),
        sa.Column("total_size_bytes", sa.Integer(), nullable=False, default=0),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "stage_id", name="uq_output_fingerprints_run_stage"),
    )
    op.create_index("ix_output_fingerprints_run_id", "output_fingerprints", ["run_id"])
    op.create_index("ix_output_fingerprints_stage_id", "output_fingerprints", ["stage_id"])


def downgrade():
    op.drop_table("output_fingerprints")
    op.drop_table("stage_copy_forward_records")
    op.drop_table("g12_approvals")
    op.drop_table("stage_seals")
    op.drop_table("g09_approvals")
    op.drop_table("stage_assurances")
    op.drop_table("stage_tests")
    op.drop_table("stage_builds")
    op.drop_table("stage_validations")
