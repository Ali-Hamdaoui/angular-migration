"""Add durable Transformer workflow, gate, checkpoint, and command claim state."""

from alembic import op
import sqlalchemy as sa


revision = "20260730_36"
down_revision = "20260729_35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transformation_continuations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("current_stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("thread_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_node", sa.String(64), nullable=False),
        sa.Column("g06_approval_id", sa.String(64), sa.ForeignKey("g06_approvals.id"), nullable=False),
        sa.Column("plan_id", sa.String(64), sa.ForeignKey("migration_plans.id"), nullable=False),
        sa.Column("plan_checksum", sa.String(128), nullable=False),
        sa.Column("stage_plan_id", sa.String(64), sa.ForeignKey("stage_execution_plans.id"), nullable=False),
        sa.Column("stage_plan_checksum", sa.String(128), nullable=False),
        sa.Column("worker_id", sa.String(128)),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("wake_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_checksum", sa.String(128), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_error_code", sa.String(128)),
        sa.Column("last_error_message", sa.Text()),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_requested_by", sa.String(128)),
        sa.Column("cancel_idempotency_key", sa.String(128)),
        sa.Column("cancel_request_checksum", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("run_id", name="uq_transformation_continuation_run"),
        sa.UniqueConstraint("thread_id", name="uq_transformation_continuation_thread"),
    )
    op.create_index(
        "ix_transformation_continuation_due",
        "transformation_continuations",
        ["status", "next_attempt_at", "lease_expires_at"],
    )

    op.create_table(
        "stage_checkpoints",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("source_checkpoint_id", sa.String(64), sa.ForeignKey("stage_checkpoints.id")),
        sa.Column("workspace_alias", sa.String(128), nullable=False),
        sa.Column("workspace_path", sa.Text(), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(128), nullable=False),
        sa.Column("manifest_artifact_id", sa.String(128)),
        sa.Column("manifest_checksum", sa.String(128)),
        sa.Column("created_from_execution_id", sa.String(64), sa.ForeignKey("command_executions.id")),
        sa.Column("safe_for_resume", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sealed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stage_id", "sequence", name="uq_stage_checkpoint_sequence"),
    )
    op.create_index("ix_stage_checkpoints_stage_kind", "stage_checkpoints", ["stage_id", "kind"])
    op.create_index(
        "uq_stage_checkpoint_sealed",
        "stage_checkpoints",
        ["stage_id"],
        unique=True,
        sqlite_where=sa.text("sealed = 1"),
    )

    op.create_table(
        "stage_prompt_requests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("execution_id", sa.String(64), sa.ForeignKey("command_executions.id"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("detector_version", sa.String(64), nullable=False),
        sa.Column("normalized_prompt", sa.Text(), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=False),
        sa.Column("context_artifact_ids", sa.JSON(), nullable=False),
        sa.Column("prompt_checksum", sa.String(128), nullable=False),
        sa.Column("pre_command_fingerprint", sa.String(128), nullable=False),
        sa.Column("observed_fingerprint", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("explanation_invocation_id", sa.String(64), sa.ForeignKey("llm_invocations.id")),
        sa.Column("explanation_artifact_id", sa.String(128)),
        sa.Column("selected_option_id", sa.String(128)),
        sa.Column("decision_actor", sa.String(128)),
        sa.Column("decision_idempotency_key", sa.String(128)),
        sa.Column("decision_request_checksum", sa.String(128)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("reconstruction_checkpoint_id", sa.String(64), sa.ForeignKey("stage_checkpoints.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("execution_id", "prompt_checksum", name="uq_stage_prompt_execution_checksum"),
    )
    op.create_index("ix_stage_prompt_status", "stage_prompt_requests", ["run_id", "status"])

    op.create_table(
        "stage_gate_packages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("gate_id", sa.String(16), nullable=False),
        sa.Column("gate_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("package_artifact_id", sa.String(128), nullable=False),
        sa.Column("package_checksum", sa.String(128), nullable=False),
        sa.Column("artifact_set_checksum", sa.String(128), nullable=False),
        sa.Column("plan_id", sa.String(64), sa.ForeignKey("migration_plans.id"), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("stage_plan_id", sa.String(64), sa.ForeignKey("stage_execution_plans.id"), nullable=False),
        sa.Column("stage_plan_checksum", sa.String(128), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(128), nullable=False),
        sa.Column("expected_state_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stale_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("run_id", "stage_id", "gate_id", "gate_version", name="uq_stage_gate_package"),
    )
    op.create_index("ix_stage_gate_status", "stage_gate_packages", ["run_id", "status"])

    op.create_table(
        "stage_gate_decisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("gate_package_id", sa.String(64), sa.ForeignKey("stage_gate_packages.id"), nullable=False),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_id", sa.String(64), sa.ForeignKey("migration_stages.id"), nullable=False),
        sa.Column("gate_id", sa.String(16), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_checksum", sa.String(128), nullable=False),
        sa.Column("expected_state_version", sa.Integer(), nullable=False),
        sa.Column("package_checksum", sa.String(128), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(128), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("reason_code", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_stage_gate_decision_idempotency"),
    )

    _add_columns()
    op.create_index(
        "uq_command_executions_active_run",
        "command_executions",
        ["run_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued', 'pending', 'running')"),
    )


def _add_columns() -> None:
    with op.batch_alter_table("stage_workspace_bindings") as batch:
        batch.add_column(sa.Column("source_checkpoint_id", sa.String(64)))
        batch.add_column(sa.Column("input_fingerprint", sa.String(128)))
        batch.add_column(sa.Column("last_verified_fingerprint", sa.String(128)))
        batch.add_column(sa.Column("last_verified_at", sa.DateTime(timezone=True)))
        batch.create_foreign_key(
            "fk_stage_workspace_source_checkpoint",
            "stage_checkpoints",
            ["source_checkpoint_id"],
            ["id"],
        )
    with op.batch_alter_table("stage_steps") as batch:
        batch.add_column(sa.Column("execution_id", sa.String(64)))
        batch.add_column(sa.Column("input_checksum", sa.String(128)))
        batch.add_column(sa.Column("output_checksum", sa.String(128)))
        batch.add_column(sa.Column("workspace_fingerprint", sa.String(128)))
        batch.add_column(sa.Column("artifact_ids", sa.JSON()))
        batch.add_column(sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True)))
        batch.create_index("ix_stage_steps_execution_id", ["execution_id"])
    with op.batch_alter_table("command_executions") as batch:
        batch.add_column(sa.Column("claim_attempt", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("claim_expires_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("prompt_request_id", sa.String(64)))
        batch.add_column(sa.Column("operation_kind", sa.String(32), nullable=False, server_default="read_only"))
        batch.add_column(sa.Column("checkpoint_id", sa.String(64)))
        batch.create_index("ix_command_executions_claim_expires_at", ["claim_expires_at"])
        batch.create_index("ix_command_executions_prompt_request_id", ["prompt_request_id"])
        batch.create_index("ix_command_executions_checkpoint_id", ["checkpoint_id"])
    with op.batch_alter_table("repair_attempts") as batch:
        for name in (
            "failure_evidence_artifact_id",
            "failure_evidence_checksum",
            "failure_route_artifact_id",
            "failure_route_checksum",
            "context_pack_artifact_id",
            "context_pack_checksum",
            "proposal_artifact_id",
            "proposal_checksum",
            "proposer_invocation_id",
            "review_artifact_id",
            "review_checksum",
            "reviewer_invocation_id",
            "g10_gate_package_id",
            "apply_ledger_artifact_id",
            "apply_ledger_checksum",
            "pre_fingerprint",
            "post_fingerprint",
            "validation_summary_artifact_id",
            "validation_summary_checksum",
            "failure_fingerprint",
            "parent_attempt_id",
        ):
            batch.add_column(sa.Column(name, sa.String(128)))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True)))
        batch.create_index("ix_repair_attempts_failure_fingerprint", ["failure_fingerprint"])


def downgrade() -> None:
    op.drop_index("uq_command_executions_active_run", table_name="command_executions")
    with op.batch_alter_table("repair_attempts") as batch:
        batch.drop_index("ix_repair_attempts_failure_fingerprint")
        batch.drop_column("completed_at")
        batch.drop_column("updated_at")
        for name in reversed(
            (
                "failure_evidence_artifact_id",
                "failure_evidence_checksum",
                "failure_route_artifact_id",
                "failure_route_checksum",
                "context_pack_artifact_id",
                "context_pack_checksum",
                "proposal_artifact_id",
                "proposal_checksum",
                "proposer_invocation_id",
                "review_artifact_id",
                "review_checksum",
                "reviewer_invocation_id",
                "g10_gate_package_id",
                "apply_ledger_artifact_id",
                "apply_ledger_checksum",
                "pre_fingerprint",
                "post_fingerprint",
                "validation_summary_artifact_id",
                "validation_summary_checksum",
                "failure_fingerprint",
                "parent_attempt_id",
            )
        ):
            batch.drop_column(name)
    with op.batch_alter_table("command_executions") as batch:
        batch.drop_index("ix_command_executions_checkpoint_id")
        batch.drop_index("ix_command_executions_prompt_request_id")
        batch.drop_index("ix_command_executions_claim_expires_at")
        for name in ("checkpoint_id", "operation_kind", "prompt_request_id", "claim_expires_at", "claim_attempt"):
            batch.drop_column(name)
    with op.batch_alter_table("stage_steps") as batch:
        batch.drop_index("ix_stage_steps_execution_id")
        for name in (
            "updated_at",
            "state_version",
            "artifact_ids",
            "workspace_fingerprint",
            "output_checksum",
            "input_checksum",
            "execution_id",
        ):
            batch.drop_column(name)
    with op.batch_alter_table("stage_workspace_bindings") as batch:
        batch.drop_constraint("fk_stage_workspace_source_checkpoint", type_="foreignkey")
        for name in (
            "last_verified_at",
            "last_verified_fingerprint",
            "input_fingerprint",
            "source_checkpoint_id",
        ):
            batch.drop_column(name)
    op.drop_table("stage_gate_decisions")
    op.drop_index("ix_stage_gate_status", table_name="stage_gate_packages")
    op.drop_table("stage_gate_packages")
    op.drop_index("ix_stage_prompt_status", table_name="stage_prompt_requests")
    op.drop_table("stage_prompt_requests")
    op.drop_index("uq_stage_checkpoint_sealed", table_name="stage_checkpoints")
    op.drop_index("ix_stage_checkpoints_stage_kind", table_name="stage_checkpoints")
    op.drop_table("stage_checkpoints")
    op.drop_index("ix_transformation_continuation_due", table_name="transformation_continuations")
    op.drop_table("transformation_continuations")
