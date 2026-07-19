export type StageBuildStatus = "pending" | "running" | "passed" | "failed" | "blocked" | "not_configured" | "cancelled" | "skipped_not_applicable";

export type StageBuildTarget = {
  target_id: string;
  project: string | null;
  configuration: string | null;
  kind: "build" | "prod_build" | "ssr_build" | "conditional";
  mandatory: boolean;
  supported: boolean;
  command_id: string;
  executable: string;
  arguments: string[];
  blocker: string | null;
};

export type StageBuildResult = {
  target_id: string;
  status: StageBuildStatus;
  exit_code: number | null;
  duration_ms: number | null;
  warnings: string[];
  errors: string[];
  output_location: string | null;
  artifact_ids: string[];
  blocker: string | null;
};

export type StageBuildRequest = {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  target_ids?: string[];
};

export type StageBuildResponse = {
  build_id: string;
  run_id: string;
  stage_id: string | null;
  status: "running" | "passed" | "failed_with_conditional" | "failed" | "cancelled";
  targets: StageBuildTarget[];
  results: StageBuildResult[];
  artifact_ids: string[];
  artifact_checksums: Record<string, string>;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};
