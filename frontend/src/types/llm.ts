export type LlmReadinessResponse = {
  status: "ready" | "blocked";
  provider: string;
  deployment_configured: boolean;
  model_capability?: string;
  error_code: string | null;
};

export type LlmSmokeRequest = {
  run_id: string;
  expected_state_version: number;
  idempotency_key: string;
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
  model_capability?: string;
  artifact_ids: string[];
  artifact_checksums: Record<string, string>;
  artifact_links?: Record<string, string>;
  correlation_id?: string | null;
  prompt_version?: string | null;
  schema_version?: string | null;
  pricing_version?: string | null;
  stage?: string | null;
  input_hashes?: string[];
  redacted_summary?: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  input_cost_usd: number;
  output_cost_usd: number;
  total_cost_usd: number;
  retries: number;
  latency_ms: number | null;
  failure_code: string | null;
  provider_http_status?: number | null;
  provider_error_code?: string | null;
  sanitized_provider_message?: string | null;
  provider_request_id?: string | null;
  failure_stage?: string | null;
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
