/**
 * Temporary UI shape synchronized with the AMF-S0-05 MigrationRunDto mock.
 * AMF-S0-07 replaces this with the centralized typed API client contract.
 */
export type MigrationRun = {
  run_id: string;
  status: string;
  source_angular_version: string;
  target_angular_version: string;
  created_at: string;
  updated_at: string;
  stages: Array<{ stage_id: string; stage_order: number; source_angular_version: string; target_angular_version: string; status: string; current_agent?: string | null }>;
  agent_executions: Array<{ execution_id: string; agent_name: string; status: string; summary?: string | null }>;
  validation_gates: Array<{ gate_id: string; name: string; status: string; details?: string | null }>;
  approval_events: Array<{ approval_id: string; decision: string; rationale?: string | null }>;
  artifacts: Array<{ artifact_id: string; artifact_type: string; relative_path: string; checksum?: string | null }>;
  command_requests: Array<{ command_id: string; requester: string; executable: string; arguments: string[]; working_directory: string }>;
  command_results: Array<{ command_id: string; status: string }>;
  patch_ledger: Array<{ patch_id: string; affected_files: string[]; change_summary: string; risk_level: string; validation_status: string }>;
  repair_attempts: Array<{ repair_attempt_id: string; attempt_number: number; status: string; risk_level: string; diagnosis?: string | null }>;
  workflow_events: Array<{ event_id: string; event_type: string }>;
};