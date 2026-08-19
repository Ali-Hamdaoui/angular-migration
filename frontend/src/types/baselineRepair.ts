export const BASELINE_TEST_RECIPE_ID = "BASELINE-TEST-001";

export type BaselineRepairRequest = {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  recipe_id: typeof BASELINE_TEST_RECIPE_ID;
  g03_package_checksum: string;
};

export type BaselineRepairResponse = {
  run_id: string;
  recipe_id: string;
  attempt_id: string;
  status: string;
  g03_package_checksum: string;
  proposal_checksum: string;
  pre_fingerprint: string;
  post_fingerprint: string;
  artifact_ids: string[];
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};
