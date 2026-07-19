export type SealCompletenessCheck = {
  check_id: string;
  name: string;
  status: "passed" | "failed" | "warning" | "skipped";
  detail: string | null;
};

export type SealCompletenessStatus = "passed" | "failed" | "warning" | "blocked" | "running";

export type SealCompleteness = {
  status: SealCompletenessStatus;
  checks: SealCompletenessCheck[];
};

export type OutputFingerprint = {
  fingerprint: string;
  algorithm: string;
  asset_count: number;
  total_size_bytes: number;
  created_at: string;
};

export type CopyForwardStatus = {
  status: "pending" | "running" | "completed" | "failed" | "blocked";
  source_stage_id: string | null;
  target_stage_id: string | null;
  copied_artifact_count: number | null;
  copied_artifact_ids: string[];
  detail: string | null;
};

export type G12Decision = "PENDING" | "APPROVED" | "REJECTED" | "APPROVED_WITH_RISK";

export type StageSealRequest = {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  g12_decision?: G12Decision;
  g12_rationale?: string;
};

export type StageSealResponse = {
  seal_id: string;
  run_id: string;
  stage_id: string | null;
  status: "sealed" | "pending_approval" | "failed" | "cancelled" | "rolled_back";
  completeness: SealCompleteness;
  fingerprint: OutputFingerprint | null;
  copy_forward: CopyForwardStatus | null;
  artifact_ids: string[];
  artifact_checksums: Record<string, string>;
  g12_decision: G12Decision | null;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};
