/** TypeScript contracts for G09 assurance, delivery, and report domains. */

export type G13Decision = "approved" | "approved_with_comment" | "modification_requested" | "rejected";

export type G14Decision = "approved" | "approved_with_comment" | "modification_requested" | "rejected";

export type G15Decision = "approved" | "approved_with_comment" | "modification_requested" | "rejected";

export type FinalAssuranceSummary = {
  run_id: string;
  candidate_fingerprint: string;
  technical_status: string;
  parity_status: string;
  source_integrity_status: string;
  security_status?: string | null;
  quality_status?: string | null;
  artifact_refs: ArtifactRefDto[];
};

export type FinalAssuranceResponse = {
  run_id: string;
  gate_id: string;
  gate_version: string;
  status: string;
  decision?: string | null;
  summary?: Record<string, unknown> | null;
  state_version: number;
  event_sequence: number;
  idempotent_replay?: boolean;
  stale_reason?: string | null;
  comment?: string | null;
};

export type FinalAssuranceRequest = {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
};

export type G13DecisionRequest = {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  decision: G13Decision;
  comment?: string | null;
  gate_id: string;
};

export type DeliveryResponse = {
  run_id: string;
  gate_id: string;
  gate_version: string;
  status: string;
  decision?: string | null;
  candidate?: Record<string, unknown> | null;
  state_version: number;
  event_sequence: number;
  idempotent_replay?: boolean;
  stale_reason?: string | null;
  comment?: string | null;
};

export type DeliveryRequest = {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  destination?: string;
};

export type G14DecisionRequest = {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  decision: G14Decision;
  comment?: string | null;
  gate_id: string;
  destination?: string;
};

export type ReportResponse = {
  run_id: string;
  gate_id: string;
  gate_version: string;
  status: string;
  decision?: string | null;
  report?: Record<string, unknown> | null;
  state_version: number;
  event_sequence: number;
  idempotent_replay?: boolean;
  stale_reason?: string | null;
  comment?: string | null;
};

export type ReportRequest = {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  generate_narrative?: boolean;
};

export type G15DecisionRequest = {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  decision: G15Decision;
  comment?: string | null;
  gate_id: string;
};

export type ArtifactRefDto = {
  artifact_id: string;
  run_id: string;
  stage_id: string | null;
  artifact_type: string;
  relative_path: string;
  created_at: string;
  checksum: string;
};
