export type BaselineParityConfidence = "machine_proven" | "user_attested_only" | "not_configured" | "blocked_by_environment" | "unknown";

export type BaselineParityCaptureRequest = {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  prerequisite_artifact_ids?: string[];
  prerequisite_artifact_checksums?: Record<string, string>;
};

export type BaselineFailureFingerprint = {
  fingerprint: string;
  group: string;
  kind: string;
  message: string;
  origin: "pre-existing";
  severity: string;
  count: number;
  confidence: BaselineParityConfidence;
  parser_version: string;
  schema_version: string;
};

export type BaselineParityResponse = {
  run_id: string;
  evidence_id: string;
  status: string;
  schema_version: string;
  parser_version: string;
  baseline_checksum: string | null;
  runtime_profile_id: string | null;
  runtime_checksum: string | null;
  failures: BaselineFailureFingerprint[];
  routes: Array<Record<string, unknown>>;
  backend_integration: Record<string, unknown>;
  anchors: Array<Record<string, unknown>>;
  confidence: Record<string, BaselineParityConfidence>;
  source_artifact_ids: string[];
  artifact_ids: string[];
  artifact_checksums: Record<string, string>;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};
