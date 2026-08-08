export type TransformationProjection = {
  run_id: string;
  continuation_id: string;
  stage_id: string;
  status: string;
  current_node: string;
  state_version: number;
  stage_status: string;
  source_version: string | null;
  target_version: string | null;
  checkpoint_kind: string | null;
  workspace_fingerprint: string | null;
  active_gate: string | null;
  active_gate_package_checksum: string | null;
  active_command_id: string | null;
  active_command_status: string | null;
  active_prompt_id: string | null;
  active_prompt_checksum: string | null;
  active_prompt_text: string | null;
  active_prompt_options: Array<{ option_id: string; label: string }>;
  active_prompt_explanation: {
    summary: string;
    option_effects: string[];
    risk_note: string;
    source: string;
  } | null;
  repair_attempt_id: string | null;
  repair_attempt_number: number | null;
  repair_parent_attempt_id?: string | null;
  repair_status: string | null;
  repair_risk_level: string | null;
  repair_proposal_checksum: string | null;
  repair_review_checksum: string | null;
  repair_proposal_id: string | null;
  repair_base_checksum: string | null;
  repair_diff_artifact_id?: string | null;
  repair_diff_checksum?: string | null;
  repair_proposal_operations?: Array<{
    operation: string | null;
    path: string | null;
    preimage_sha256: string | null;
    postimage_sha256: string | null;
  }>;
  repair_safe_diff: string | null;
  repair_review: {
    decision: "accept" | "request_changes" | "reject";
    findings: string[];
    policy_checks: string[];
    risk_assessment: string;
    required_validation_targets: string[];
    limitations: string[];
  } | null;
  repair_rationale: string[];
  repair_apply_checksum: string | null;
  repair_validation_checksum: string | null;
  next_backend_action?: string | null;
  angular_update_retry_attempt?: number | null;
  angular_update_retry_status?: string | null;
  workflow_step: string;
  active_command_phase: string | null;
  stage_start_fingerprint: string | null;
  repair_contract: {
    attempt_id: string;
    stage_id: string;
    failure_execution_id: string | null;
    failure_type: string | null;
    repair_kind: string;
    strategy: string | null;
    operations: Array<Record<string, unknown>>;
    risk_level: string;
    validation_targets: string[];
    proposal_checksum: string | null;
    reviewer_result: TransformationProjection["repair_review"];
    human_decision: {
      decision: string;
      actor: string;
      comment: string | null;
      accepted: boolean;
    } | null;
    lifecycle_status: string;
  } | null;
  dependency_operation:
    | {
        operation: "dependency_transition";
        repair_kind: string;
        failure_type: string;
        strategy: string;
        path: string;
        blocking_dependency: {
          package: string;
          installed_version: string;
          required_peer_ranges: Array<{ package: string; version_range: string }>;
        };
        target_state: { package: string; target_version: string; angular_major: number };
        checkpoint_id: string;
      }
    | {
        operation: "dependency_add";
        path: string;
        section: string;
        package: string;
        new_version: string;
        strategy: string | null;
        provenance: Array<Record<string, string>> | null;
      }
    | null;
  completed_transition_phases: Array<{
    phase: string;
    execution_id: string | null;
    artifact_id: string | null;
    status: string;
    package_json_change: {
      before_checksum: string | null;
      after_checksum: string | null;
      unified_diff: string | null;
    } | null;
    lockfile_changes: {
      before: Record<string, unknown> | null;
      after: Record<string, unknown> | null;
    } | null;
    installed_verification: Record<string, unknown> | null;
  }>;
  repair_verification: {
    pre_fingerprint: string | null;
    post_fingerprint: string | null;
    apply_ledger_checksum: string | null;
    validation_summary_checksum: string | null;
    verified: boolean;
  } | null;
  dependency_closure: Record<string, unknown> | null;
  validation_results: Record<string, {
    status: string;
    execution_id: string | null;
    command_status: string | null;
  }>;
  active_error: { code: string; message: string } | null;
  historical_diagnostics: Array<{
    code: string;
    message: string | null;
    status: "resolved";
  }>;
  route_stages: Array<{
    stage_id: string;
    source_version: string | null;
    target_version: string | null;
    status: string;
  }>;
  sealed_chain_hash: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  runtime_profile_binding: {
    expected: {
      statuses: string[];
      profile_id: string | null;
      checksums: string[];
    };
    actual: {
      status: string | null;
      profile_id: string | null;
      checksum: string | null;
      persisted_profile_checksum: string | null;
    };
    mismatches: string[];
  } | null;
  cancel_requested_at: string | null;
};
