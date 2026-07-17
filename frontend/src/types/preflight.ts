export type G01Decision = "approved" | "approved_with_comment" | "modification_requested" | "rejected";

export type ProductionPreflight = {
  snapshot: {
    preflight_id: string;
    gate_id: string;
    gate_version: string;
    state_version: number;
    status: "passed" | "passed_with_warnings" | "blocked" | "expired" | "stale";
    created_at: string;
    expires_at: string;
    input_checksum: string;
    artifact_set_checksum: string;
    target_angular_family: string;
    migration_mode: string;
    source_path: string;
    target_parent_path: string;
    generated_output_name: string;
    resolved_output_root: string;
    platform_repository_root: string;
    target_output_path: string;
    target_reservation_id: string | null;
    blockers: string[];
    warnings: string[];
    artifacts: Record<string, { artifact_id: string; checksum: string; relative_path: string }>;
    approval_status: "pending" | "approved" | "approved_with_comment" | "modification_requested" | "rejected" | "expired" | "stale";
    decision_history: G01DecisionResponse[];
  };
};

export type G01DecisionResponse = {
  decision_id: string;
  preflight_id: string;
  gate_id: string;
  decision: G01Decision;
  actor: string;
  comment: string | null;
  decided_at: string;
  input_checksum: string;
  artifact_set_checksum: string;
  state_version: number;
  idempotent_replay: boolean;
};
