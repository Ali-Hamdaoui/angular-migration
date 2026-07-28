export type PlanArtifactInput = { artifact_id: string; checksum: string };

export type PlanCommand = {
  command_id: string;
  template_id: string;
  template_version: number;
  parameter_bindings: Record<string, string>;
  executable: string;
  arguments: string[];
  shell: false;
  working_directory_alias: string;
  timeout_seconds: number;
  network_profile: string;
  runtime_profile_checksum: string | null;
  cancellation_policy: string;
  conditional: boolean;
};

export type PlanRouteStage = { stage_id: string; source_family: string; target_family: string; target_exact: string };

export type PlanResponse = {
  run_id: string;
  status: string;
  plan: {
    plan_id: string;
    run_id: string;
    version: number;
    source_family: string;
    source_exact: string;
    target_family: string;
    route: string[];
    mode: string;
    catalogue_version: string;
    stage_plan_strategy: string;
    approval_policy: string;
    repair_policy: { policy_id: string; enabled: boolean; proposer_reviewer_required: boolean; human_apply_required: boolean };
    command_policy: string;
    artifact_policy: string;
    checksum: string;
  };
  stage_plan: {
    stage_plan_id: string;
    stage_id: string;
    plan_version: number;
    input_fingerprint: string;
    evidence_set_checksum: string | null;
    input_workspace_fingerprint: string | null;
    source_family: string;
    source_exact: string;
    target_family: string;
    target_exact: string;
    target_cli_exact?: string;
    execution_profile_id: string;
    commands: Record<string, PlanCommand[]>;
    build_system_decision: { decision_id: string; builder: string; action: string; rationale: string; checksum: string };
    validation_policy: { policy_id: string; baseline_comparison_required: boolean; route_comparison_required: boolean; backend_comparison_required: boolean; required_checks: string[] };
    recovery_policy: { policy_id: string; safe_boundaries: string[]; rerun_read_only_steps: boolean; reconstruct_mutating_steps: boolean };
    repair_policy: { policy_id: string; enabled: boolean; proposer_reviewer_required: boolean; human_apply_required: boolean };
    forbidden_change_policy: { policy_id: string; actions: string[] };
    checksum: string;
  };
  plan_checksum: string;
  stage_plan_checksum: string;
  artifact_ids: string[];
  artifact_checksums: Record<string, string>;
  artifact_links: Record<string, string>;
  builder_decision: Record<string, unknown>;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};

export type PlanReviewResponse = {
  run_id: string;
  status: string;
  plan: Record<string, unknown> | null;
  stage_plan: Record<string, unknown> | null;
  plan_checksum: string | null;
  stage_plan_checksum: string | null;
  diff: { from_version?: number; to_version?: number; changed_fields?: string[]; changes?: Record<string, unknown>; checksum?: string } | null;
  package: Record<string, unknown> | null;
  artifact_ids: string[];
  artifact_checksums: Record<string, string>;
  artifact_links: Record<string, string>;
  gate_id: string;
  gate_version: string;
  gate_status: string;
  gate_decision: G06Decision | null;
  package_checksum: string | null;
  artifact_set_checksum?: string | null;
  computed_artifact_set_checksum?: string | null;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};

export type PlanReviewChanges = Partial<{
  catalogue_version: string;
  execution_profile_id: string;
  target_cli_exact: string;
  validation_policy_id: string;
  recovery_policy_id: string;
  repair_policy_id: string;
  builder: string;
}>;

export type PlanRevisionRequest = {
  expected_state_version: number;
  idempotency_key: string;
  plan: Record<string, unknown>;
  stage_plan: Record<string, unknown>;
  changes: PlanReviewChanges;
  artifact_set_checksum: string;
  prerequisite_artifacts: PlanArtifactInput[];
  workspace_fingerprint?: string | null;
  correlation_id?: string | null;
};

export type PlanningExplanationRequest = Omit<PlanRevisionRequest, "changes"> & { plan_version: number };
export type G06Decision = "approve" | "approve_with_comment" | "request_modification" | "reject";
export type G06DecisionRequest = {
  expected_state_version: number;
  idempotency_key: string;
  gate_version: string;
  package_checksum?: string | null;
  artifact_set_checksum: string;
  plan_checksum: string;
  stage_plan_checksum: string;
  workspace_fingerprint?: string | null;
  decision: G06Decision;
  comment?: string | null;
  correlation_id?: string | null;
};
export type G06DecisionResponse = {
  run_id: string;
  gate_id: "G06" | string;
  gate_version: string;
  decision: G06Decision;
  status: string;
  accepted: boolean;
  package_checksum: string;
  artifact_set_checksum: string;
  plan_checksum: string;
  stage_plan_checksum: string;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};
