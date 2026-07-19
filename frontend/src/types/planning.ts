export type PlanArtifactInput = { artifact_id: string; checksum: string };

export type PlanCommand = {
  command_id: string;
  executable: string;
  arguments: string[];
  shell: false;
  working_directory_alias: string;
  timeout_seconds: number;
  network_profile: string;
  conditional: boolean;
};

export type PlanCreateRequest = {
  expected_state_version: number;
  idempotency_key: string;
  source_exact: string;
  source_family: string;
  target_family: string;
  catalogue_version: string;
  input_fingerprint: string;
  execution_profile_id: string;
  stage_route: ([string, string, string, string] | [string, string, string, string, string])[];
  target_cli_exact?: string | null;
  builder: string;
  prerequisite_artifacts: PlanArtifactInput[];
  validation_policy_id?: string;
  recovery_policy_id?: string;
  repair_policy_id?: string;
  correlation_id?: string | null;
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
