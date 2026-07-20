/** Types for the G03 Angular transformation, evidence, and G08 approval surfaces. */

export interface AngularUpdateRequest {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  source_version: string;
  target_version: string;
  toolchain_profile_id?: string;
  prerequisite_artifact_ids?: string[];
}

export interface AngularUpdateResponse {
  run_id: string;
  stage_id: string;
  status: "pending" | "running" | "succeeded" | "failed" | "interactive_blocked";
  target_version_status?: "verified" | "mismatch" | "failed" | "inconclusive";
  resolved_target_version?: string;
  command_execution_id?: string;
  prompt_detected?: string;
  artifact_ids: string[];
  state_version: number;
  event_sequence: number;
  error_message?: string;
  idempotent_replay: boolean;
}

export interface TransformationEvidenceRequest {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  prerequisite_artifact_ids?: string[];
  source_sandbox_path: string;
  target_sandbox_path: string;
}

export interface TransformationEvidenceResponse {
  run_id: string;
  stage_id: string;
  status: string;
  overall_risk_level: string;
  total_files_changed: number;
  diff_checksum: string;
  diff_summary: Record<string, unknown>;
  package_change?: Record<string, unknown>;
  migration_list: string[];
  forbidden_changes: Record<string, unknown>[];
  changed_file_classifications: Record<string, string>;
  evidence_complete: boolean;
  artifact_ids: string[];
  state_version: number;
  event_sequence: number;
  block_reason?: string;
  idempotent_replay: boolean;
}

export interface TargetVersionResponse {
  run_id: string;
  stage_id: string;
  target_version_status: "verified" | "mismatch" | "failed" | "inconclusive";
  resolved_target_version: string | null;
  evidence_sources: Record<string, string>;
  all_sources_agree: boolean;
  disagreements: string[];
  artifact_ids?: string[];
  state_version?: number;
  event_sequence?: number;
}

export type G08Decision = "approved" | "approved_with_comment" | "modification_requested" | "rejected";

export interface G08DecisionRequest {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  decision: G08Decision;
  comment?: string;
  gate_id: string;
}

export interface G08ReviewResponse {
  run_id: string;
  stage_id: string;
  gate_id: string;
  gate_version: string;
  status: string;
  decision?: string;
  package: Record<string, unknown>;
  package_checksum: string;
  artifact_set_checksum: string;
  workspace_fingerprint: string;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
  stale_reason?: string;
  comment?: string;
}
