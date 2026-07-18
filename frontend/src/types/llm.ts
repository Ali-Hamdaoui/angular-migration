export type LlmReadinessResponse = {
  status: "ready" | "blocked";
  provider: string;
  deployment_configured: boolean;
  model_capability: string;
  error_code: string | null;
};

export type LlmSmokeRequest = {
  run_id: string;
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  correlation_id?: string | null;
};

export type LlmInvocationResponse = {
  invocation_id: string;
  run_id: string;
  status: "in_progress" | "completed" | "failed" | "blocked";
  role: string;
  task_type: string;
  provider: string;
  deployment_alias: string;
  artifact_ids: string[];
  artifact_checksums: Record<string, string>;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  input_cost_usd: number;
  output_cost_usd: number;
  total_cost_usd: number;
  retries: number;
  latency_ms: number | null;
  failure_code: string | null;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
};

export type LlmActivityResponse = {
  run_id: string;
  invocations: LlmInvocationResponse[];
};

export type LlmUsageRecord = {
  invocation_id: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  pricing_version: string;
};

export type LlmUsageResponse = {
  run_id: string;
  invocation_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  input_cost_usd: number;
  output_cost_usd: number;
  total_cost_usd: number;
  pricing_versions: string[];
  records: LlmUsageRecord[];
};
