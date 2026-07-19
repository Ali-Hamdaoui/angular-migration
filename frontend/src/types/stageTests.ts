export type StageTestSuiteKind = "unit" | "integration" | "e2e" | "lint";

export type StageTestStatus = "pending" | "running" | "passed" | "failed" | "blocked" | "not_configured" | "cancelled" | "accepted_risk";

export type StageTestSuite = {
  suite_id: string;
  name: string;
  kind: StageTestSuiteKind;
  mandatory: boolean;
  status: StageTestStatus;
  test_count: number | null;
  passed: number | null;
  failed: number | null;
  skipped: number | null;
  duration_ms: number | null;
  warnings: string[];
  failed_tests: string[];
  artifact_ids: string[];
  is_baseline: boolean;
};

export type StageTestGroup = "baseline" | "new" | "resolved" | "not_configured";

export type StageTestChange = {
  test_id: string;
  name: string;
  suite_name: string;
  kind: StageTestSuiteKind;
  group: StageTestGroup;
  previous_status: StageTestStatus | null;
  current_status: StageTestStatus;
  previous_duration_ms: number | null;
  current_duration_ms: number | null;
};

export type StageTestRequest = {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  suite_ids?: string[];
};

export type StageTestResponse = {
  test_id: string;
  run_id: string;
  stage_id: string | null;
  status: "running" | "passed" | "passed_with_manual_items" | "failed" | "cancelled";
  suites: StageTestSuite[];
  changes: StageTestChange[];
  logs: string[];
  artifact_ids: string[];
  artifact_checksums: Record<string, string>;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};
