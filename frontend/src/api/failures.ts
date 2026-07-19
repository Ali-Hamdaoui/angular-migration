import { apiClient, type createApiClient } from "./client";
import type {
  AuthoritativeRunMutationResultDto,
  FailureEvidenceDto,
} from "@/types/generated/api";

type ApiClient = ReturnType<typeof createApiClient>;

/**
 * Submit command output for failure evidence capture and deterministic diagnostics.
 * POST /api/v1/runs/{runId}/commands/{commandId}/failure-evidence
 */
export function captureFailureEvidence(
  runId: string,
  commandId: string,
  request: FailureEvidenceCaptureRequestDto,
  client: ApiClient = apiClient,
): Promise<AuthoritativeRunMutationResultDto> {
  return client.post<AuthoritativeRunMutationResultDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/commands/${encodeURIComponent(commandId)}/failure-evidence`,
    request,
  );
}

/**
 * Retrieve a captured failure evidence record with diagnostics.
 * GET /api/v1/runs/{runId}/failures/{failureId}
 */
export function getFailureEvidence(
  runId: string,
  failureId: string,
  client: ApiClient = apiClient,
): Promise<FailureEvidenceDto> {
  return client.get<FailureEvidenceDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/failures/${encodeURIComponent(failureId)}`,
  );
}

/**
 * Classify a failure using C-Lite routing.
 * POST /api/v1/runs/{runId}/failures/{failureId}/classify
 */
export function classifyFailureRoute(
  runId: string,
  failureId: string,
  request: FailureRouteClassifyRequestDto,
  client: ApiClient = apiClient,
): Promise<AuthoritativeRunMutationResultDto> {
  return client.post<AuthoritativeRunMutationResultDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/failures/${encodeURIComponent(failureId)}/classify`,
    request,
  );
}

/**
 * Get the C-Lite route decision for a failure.
 * GET /api/v1/runs/{runId}/failures/{failureId}/route
 */
export function getFailureRoute(
  runId: string,
  failureId: string,
  client: ApiClient = apiClient,
): Promise<FailureRouteDto> {
  return client.get<FailureRouteDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/failures/${encodeURIComponent(failureId)}/route`,
  );
}

/**
 * Request a retry for a retryable external failure.
 * POST /api/v1/runs/{runId}/failures/{failureId}/retry
 */
export function retryFailure(
  runId: string,
  failureId: string,
  request: FailureRetryRequestDto,
  client: ApiClient = apiClient,
): Promise<AuthoritativeRunMutationResultDto> {
  return client.post<AuthoritativeRunMutationResultDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/failures/${encodeURIComponent(failureId)}/retry`,
    request,
  );
}

/**
 * Build a bounded sanitized RepairContextPack for a failure.
 * POST /api/v1/runs/{runId}/failures/{failureId}/repair-context
 */
export function buildRepairContext(
  runId: string,
  failureId: string,
  request: RepairContextBuildRequestDto,
  client: ApiClient = apiClient,
): Promise<AuthoritativeRunMutationResultDto> {
  return client.post<AuthoritativeRunMutationResultDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/failures/${encodeURIComponent(failureId)}/repair-context`,
    request,
  );
}

/**
 * Get a built RepairContextPack.
 * GET /api/v1/runs/{runId}/repair-contexts/{contextId}
 */
export function getRepairContext(
  runId: string,
  contextId: string,
  client: ApiClient = apiClient,
): Promise<RepairContextPackDto> {
  return client.get<RepairContextPackDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/repair-contexts/${encodeURIComponent(contextId)}`,
  );
}

// ---------------------------------------------------------------------------
// Request / response types used by the failures API
// ---------------------------------------------------------------------------

export interface FailureEvidenceCaptureRequestDto {
  command_id: string;
  exit_code: number;
  stdout: string;
  stderr: string;
  workspace_fingerprint: string;
  expected_state_version: number;
  idempotency_key: string;
  actor?: string;
  baseline_artifact_ids?: string[];
}

export interface FailureRouteClassifyRequestDto {
  expected_state_version: number;
  idempotency_key: string;
  actor?: string;
}

export interface FailureRetryRequestDto {
  expected_state_version: number;
  idempotency_key: string;
  actor?: string;
}

export interface RepairContextBuildRequestDto {
  expected_state_version: number;
  idempotency_key: string;
  actor?: string;
  max_tokens?: number;
}

export interface FailureEvidenceDto {
  failure_id: string;
  run_id: string;
  stage_id: string;
  execution_id: string;
  failure_fingerprint: string;
  origin: string;
  diagnostics: FailureDiagnosticDto[];
  workspace_fingerprint: string;
  status: string;
  raw_log_artifacts?: { artifact_id: string; checksum: string; content_type: string }[];
  state_version: number;
  created_at?: string;
}

export interface FailureDiagnosticDto {
  parser_type: string;
  parser_confidence: number;
  message: string;
  code?: string;
  file_path?: string;
  line_number?: number;
  column?: number;
  severity?: string;
  raw_excerpt?: string;
}

export interface FailureRouteDto {
  failure_id: string;
  route: string;
  policy_version: string;
  decision_checksum: string;
  actions: string[];
  risk: string;
}

export interface RepairContextPackDto {
  context_pack_id: string;
  failure_id: string;
  stage_id: string;
  repair_attempt: number;
  workspace_fingerprint: string;
  selection_policy_version: string;
  sanitization_checksum: string;
  content_checksum: string;
  segments: any[];
  token_budget?: number;
  status: string;
}
