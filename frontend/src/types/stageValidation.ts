export type StageValidationStatus = "pending" | "running" | "passed" | "failed" | "blocked" | "not_configured" | "cancelled" | "accepted_risk";

export type StageValidationKind = "install" | "static";

export type StageValidationStep = {
  step_id: string;
  name: string;
  kind: StageValidationKind;
  status: StageValidationStatus;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  detail: string | null;
  error_code: string | null;
};

export type StageDiagnostic = {
  diagnostic_id: string;
  file: string | null;
  code: string;
  severity: "error" | "warning" | "info";
  message: string;
  line: number | null;
  column: number | null;
  artifact_id: string | null;
};

export type StageValidationRequest = {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  prerequisite_artifact_ids?: string[];
  prerequisite_artifact_checksums?: Record<string, string>;
};

export type StageValidationResponse = {
  validation_id: string;
  run_id: string;
  stage_id: string | null;
  status: StageValidationStatus;
  steps: StageValidationStep[];
  diagnostics: StageDiagnostic[];
  logs: string[];
  artifact_ids: string[];
  artifact_checksums: Record<string, string>;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};
