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
  correlation_id?: string;
  expected_angular_update_record_id?: string;
  expected_angular_update_binding_checksum?: string;
}

export type TransformationArtifactKind =
  | "unified_diff"
  | "package_lock_diff"
  | "migration_list"
  | "changed_file_inventory"
  | "risk_report"
  | "forbidden_change_report"
  | "builder_comparison"
  | "artifact_manifest";

export interface TransformationArtifactRef {
  kind: TransformationArtifactKind;
  artifact_id: string;
  artifact_type: string;
  checksum: string;
  size_bytes: number;
  relative_path: string;
}

export type TransformationIntegrityStatus =
  | "valid"
  | "stale"
  | "tampered"
  | "missing"
  | "in_progress"
  | "blocked"
  | "failed";

export interface TransformationEvidenceResponse {
  run_id: string;
  stage_id: string;
  evidence_id: string;
  status: string;
  overall_risk_level: string;
  total_files_changed: number;
  diff_checksum: string;
  inventory_checksum: string;
  diff_summary: Record<string, unknown>;
  package_change?: Record<string, unknown>;
  builder_comparison: Record<string, unknown>;
  risk_report: Record<string, unknown>;
  migration_list: string[];
  forbidden_changes: Record<string, unknown>[];
  changed_file_classifications: Record<string, string>;
  evidence_complete: boolean;
  artifacts: TransformationArtifactRef[];
  artifact_set_checksum: string;
  integrity_status: TransformationIntegrityStatus;
  stale_reason?: string;
  evidence_schema_version: string;
  angular_update_record_id: string;
  angular_update_binding_checksum: string;
  state_version: number;
  event_sequence: number;
  block_reason?: string;
  idempotent_replay: boolean;
  correlation_id?: string;
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

export interface G08InitializeRequest {
  expected_state_version: number;
  idempotency_key: string;
  gate_id: string;
}

export interface G08DecisionRequest {
  expected_state_version: number;
  idempotency_key: string;
  actor?: string;
  decision: G08Decision;
  comment?: string;
  gate_id: string;
  gate_version: string;
  package_checksum: string;
  artifact_set_checksum: string;
  workspace_fingerprint: string;
  plan_version?: string;
  plan_checksum?: string;
}

export interface G08ArtifactRef {
  artifact_id: string;
  kind: string;
  relative_path: string;
  checksum: string;
  size_bytes: number;
}

export interface G08EvidencePackage {
  package_id: string;
  transformation_result?: Record<string, unknown>;
  evidence_result?: Record<string, unknown>;
  angular_update_record_id?: string;
  angular_update_binding_checksum?: string;
  artifacts: G08ArtifactRef[];
  created_at: string;
}

export interface G08ReviewResponse {
  run_id: string;
  stage_id: string;
  gate_id: string;
  gate_version: string;
  status: string;
  decision?: string;
  package: G08EvidencePackage;
  package_checksum: string;
  artifact_set_checksum: string;
  workspace_fingerprint: string;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
  stale_reason?: string;
  comment?: string;
  plan_version?: string;
  plan_checksum?: string;
  artifact_ids?: string[];
  artifact_links?: Record<string, string>;
  package_artifact_id?: string;
  technical_blockers?: string[];
  correlation_id?: string;
}
