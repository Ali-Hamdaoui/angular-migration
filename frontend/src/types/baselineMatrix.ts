export type BaselineMatrixKind = "build" | "test" | "lint";
export type BaselineMatrixStatus = "passed" | "failed" | "skipped_not_configured" | "skipped_not_applicable" | "blocked" | "interrupted" | "cancelled";

export type BaselineMatrixTarget = {
  target_id: string;
  kind: BaselineMatrixKind;
  project: string | null;
  configuration: string | null;
  command_id: string;
  executable: string;
  arguments: string[];
  supported: boolean;
  blocker: string | null;
};

export type BaselineMatrixResult = {
  target_id: string;
  kind: BaselineMatrixKind;
  status: BaselineMatrixStatus;
  exit_code: number | null;
  duration_ms: number | null;
  warnings: string[];
  test_count: number | null;
  failed_tests: string[];
  output_location: string | null;
  blocker: string | null;
};

export type BaselineTargetInventoryResponse = {
  run_id: string;
  targets: BaselineMatrixTarget[];
  package_json_checksum: string;
  angular_json_present: boolean;
  state_version: number;
  event_sequence: number;
};

export type BaselineValidationResponse = {
  validation_id: string;
  run_id: string;
  kind: BaselineMatrixKind;
  status: BaselineMatrixStatus | "running";
  targets: BaselineMatrixTarget[];
  results: BaselineMatrixResult[];
  parser_summary: Record<string, unknown> | null;
  artifact_ids: string[];
  baseline_checksum: string | null;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};

export type BaselineValidationRequest = {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  prerequisite_artifact_ids?: string[];
};
