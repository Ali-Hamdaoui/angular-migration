export type AssuranceGateName = "install_static" | "build_matrix" | "test_suite" | "parity_evidence" | "security_scan" | "quality_gate";

export type AssuranceGateStatus = "passed" | "failed" | "conditional" | "manual_required" | "deferred" | "not_evaluated" | "accepted_risk";

export type AssuranceGate = {
  gate_id: string;
  name: AssuranceGateName;
  label: string;
  status: AssuranceGateStatus;
  checked_at: string | null;
  detail: string | null;
  artifact_ids: string[];
  artifact_checksums: Record<string, string>;
};

export type RouteDelta = {
  route: string;
  type: "added" | "removed" | "modified" | "unchanged";
  previous_controller: string | null;
  current_controller: string | null;
  previous_template: string | null;
  current_template: string | null;
};

export type ApiDelta = {
  endpoint: string;
  method: string;
  type: "added" | "removed" | "modified" | "unchanged";
  previous_proxy: string | null;
  current_proxy: string | null;
};

export type AssuranceCard = {
  card_id: string;
  title: string;
  status: AssuranceGateStatus;
  summary: string;
  evidence_artifact_ids: string[];
  proof_label: "machine_proven" | "user_attested" | "not_applicable" | "unknown";
};

export type AssuranceManualItem = {
  item_id: string;
  description: string;
  required: boolean;
  completed: boolean;
  completed_at: string | null;
  completed_by: string | null;
};

export type AssuranceDecision = "PENDING" | "ACCEPT_ALL" | "ACCEPT_WITH_RISK" | "REJECT" | "MODIFICATION_REQUESTED";

export type StageAssuranceRequest = {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  decision?: AssuranceDecision;
  rationale?: string;
  accepted_risk_item_ids?: string[];
};

export type StageAssuranceResponse = {
  assurance_id: string;
  run_id: string;
  stage_id: string | null;
  status: "running" | "passed" | "passed_with_manual_items" | "failed" | "cancelled";
  gates: AssuranceGate[];
  route_deltas: RouteDelta[];
  api_deltas: ApiDelta[];
  cards: AssuranceCard[];
  manual_items: AssuranceManualItem[];
  artifact_ids: string[];
  artifact_checksums: Record<string, string>;
  g09_decision: AssuranceDecision | null;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};
