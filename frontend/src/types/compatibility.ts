export type CompatibilityStage = {
  stage_id: string;
  source_family: string;
  target_family: string;
  support_level: "officially_supported" | "historical_validated" | "historical_experimental" | "blocked" | string;
  target_angular_exact: string;
  target_cli_exact: string;
  node_exact?: string | null;
  npm_exact?: string | null;
  blockers: string[];
  warnings: string[];
};

export type Stage1ExecutionProfile = {
  profile_id: string;
  angular_exact: string;
  angular_cli_exact: string;
  node_exact: string;
  npm_exact: string;
  npx_exact: string;
  node_executable: string;
  npm_executable: string;
  npx_executable: string;
  operating_system: string;
  architecture: string;
  catalogue_version: string;
  source_angular_exact: string;
  source_execution_profile_checksum?: string | null;
  stage1_profile_checksum?: string;
  checksum: string;
};

export type FeasibilityCreateRequest = {
  expected_state_version: number;
  idempotency_key: string;
  source_angular_exact: string;
  catalogue_version: string;
  registry_snapshot_id: string;
  registry_snapshot_checksum: string;
  prerequisite_artifacts: Array<{ artifact_id: string; checksum: string }>;
  runtime_candidates?: unknown[];
  workspace_topology?: string;
  dependency_findings?: string[];
  workspace_fingerprint?: string | null;
  plan_version?: string | null;
  correlation_id?: string | null;
};

export type FeasibilityResponse = {
  run_id: string;
  resolution_id: string;
  status: string;
  source_exact: string;
  source_family: string;
  target_family: string;
  support_level: string;
  catalogue_snapshot?: { version?: string; checksum?: string; [key: string]: unknown };
  registry_snapshot?: { snapshot_id?: string; checksum?: string; [key: string]: unknown };
  runtime_candidates?: Array<Record<string, unknown>>;
  route: CompatibilityStage[];
  selected_profile: Stage1ExecutionProfile | null;
  blockers: string[];
  warnings: string[];
  package: Record<string, unknown> & { artifact_set_checksum?: string; workspace_fingerprint?: string | null; plan_version?: string | null };
  package_checksum: string;
  artifact_ids: string[];
  artifact_checksums: Record<string, string>;
  artifact_links: Record<string, string>;
  gate_id: "G05";
  gate_version: string;
  gate_status: string;
  gate_decision: string | null;
  gate_created_at?: string | null;
  gate_expires_at?: string | null;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};

export type G05Decision = "approve" | "approve_with_comment" | "request_modification" | "reject";
export type G05DecisionRequest = {
  expected_state_version: number;
  idempotency_key: string;
  gate_version: string;
  package_checksum: string;
  artifact_set_checksum: string;
  workspace_fingerprint?: string | null;
  plan_version?: string | null;
  decision: G05Decision;
  comment?: string | null;
};
export type G05DecisionResponse = {
  run_id: string;
  gate_id: "G05";
  gate_version: string;
  decision: G05Decision;
  status: string;
  accepted: boolean;
  package_checksum: string;
  artifact_set_checksum: string;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};
