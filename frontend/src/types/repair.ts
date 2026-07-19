/** Proposer status values as returned by the backend. */
export type ProposerStatus = "candidate" | "insufficient_context" | "not_repairable";

/* ------------------------------------------------------------------ */
/*  Reviewer types (S4-F05)                                            */
/* ------------------------------------------------------------------ */

/** Reviewer decision values. */
export type ReviewerDecisionValue =
  | "accept"
  | "request_revision"
  | "reject"
  | "insufficient_context";

/** The non-authoring review decision model. */
export type ReviewDecision = {
  review_id: string;
  proposal_id: string;
  reviewer_invocation_id: string;
  decision: ReviewerDecisionValue;
  proposal_diff_checksum: string;
  review_checksum: string;
  critique: string[];
  revision_instructions: string[];
  requested_context: string[];
};

/** Response from GET /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer */
export type ReviewerResponse = {
  run_id: string;
  repair_attempt_id: string;
  proposal_id: string;
  decision: ReviewerDecisionValue;
  review_decision: ReviewDecision;
  revision_count: number;
  review_output_checksum: string;
  model_provenance: Record<string, string>;
  usage: Record<string, number | string>;
  prompt_version: string;
  schema_version: string;
  workspace_fingerprint: string;
  correlation_id: string | null;
  artifact_ids: string[];
  artifact_checksums: Record<string, string>;
  artifact_links: Record<string, string>;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};

/** Request body for POST /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer */
export type ReviewerInvokeRequest = {
  expected_state_version: number;
  idempotency_key: string;
  correlation_id?: string | null;
};

/* ------------------------------------------------------------------ */
/*  G10 approval gate types (S4-F06)                                   */
/* ------------------------------------------------------------------ */

/** G10 decision values for human apply/reject. */
export type G10DecisionValue =
  | "approve"
  | "approve_with_comment"
  | "reject"
  | "modification_requested";

/** G10 status lifecycle values. */
export type G10StatusValue =
  | "pending"
  | "approved"
  | "approved_with_comment"
  | "modification_requested"
  | "rejected"
  | "stale";

/** Response from GET /api/v1/runs/{id}/repair-proposals/{proposalId} */
export type RepairProposalResponse = {
  proposal_id: string;
  failure_id: string;
  context_pack_id: string;
  proposer_invocation_id: string;
  status: ProposerStatus;
  summary: string | null;
  root_cause: string | null;
  fix_strategy: string | null;
  diff_checksum: string;
  changed_files: string[];
  workspace_fingerprint: string;
  risk_notes: string[];
  g10_status: G10StatusValue;
  g10_decision: string | null;
  g10_approval_id: string | null;
  state_version: number;
  event_sequence: number;
};

/** Response from POST /api/v1/runs/{id}/approvals/G10/decisions */
export type G10DecisionResponse = {
  run_id: string;
  proposal_id: string;
  decision: G10DecisionValue;
  accepted: boolean;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
  stale: boolean;
  reason: string | null;
};

/** Request body for POST /api/v1/runs/{id}/approvals/G10/decisions */
export type G10DecisionRequest = {
  proposal_id: string;
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  decision: G10DecisionValue;
  rationale: string | null;
  workspace_fingerprint: string;
  diff_checksum: string;
  lineage_checksum: string;
};

/** AI diagnosis of the failure evidence. */
export type ProposerDiagnosis = {
  root_cause: string;
  fix_strategy: string;
  evidence_references: string[];
  confidence: string;
  deterministic_input_checksum: string;
};

/** The candidate diff produced by the Proposer LLM. */
export type ProposerCandidate = {
  diff_content: string;
  diff_checksum: string;
  changed_files: string[];
  risk_notes: string[];
  validation_notes: string[];
};

/** Response from GET /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer */
export type ProposerResponse = {
  proposer_id: string;
  run_id: string;
  repair_attempt_id: string;
  status: ProposerStatus | "in_progress" | "failed" | "blocked";
  diagnosis: ProposerDiagnosis | null;
  candidate: ProposerCandidate | null;
  model_provenance: Record<string, string>;
  usage: Record<string, number | string>;
  prompt_version: string;
  schema_version: string;
  correlation_id: string | null;
  artifact_ids: string[];
  artifact_checksums: Record<string, string>;
  artifact_links: Record<string, string>;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};

/** Request body for POST /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer */
export type ProposerInvokeRequest = {
  expected_state_version: number;
  idempotency_key: string;
  correlation_id?: string | null;
};
