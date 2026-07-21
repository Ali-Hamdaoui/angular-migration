import { apiClient, type createApiClient } from "./client";

export interface StagePrepareRequest {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  stage_key: string;
  source_version_family: string;
  target_version_family: string;
  plan_version: string;
}

export interface StagePrepareResponse {
  run_id: string;
  stage_id: string;
  stage_key: string;
  status: string;
  state_version: number;
  event_sequence: number;
  plan: Record<string, unknown> | null;
  idempotent_replay: boolean;
}

export interface G07DecisionRequest {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  stage_id: string;
  decision: "approved" | "approved_with_comment" | "modification_requested" | "rejected";
  comment?: string | null;
  gate_id?: string;
}

export interface G07ReviewResponse {
  run_id: string;
  stage_id: string;
  gate_id: string;
  gate_version: string;
  status: string;
  decision: string | null;
  package: Record<string, unknown>;
  state_version: number;
  event_sequence: number;
  idempotent_replay: boolean;
  stale_reason: string | null;
  comment: string | null;
  decision_id?: string | null;
}

export interface StageSandboxRequest {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
}

export interface StageSandboxResponse {
  run_id: string;
  stage_id: string;
  sandbox_path: string;
  status: string;
  state_version: number;
  event_sequence: number;
  verification: Record<string, unknown> | null;
  idempotent_replay: boolean;
}

export interface StageBootstrapInstallRequest {
  expected_state_version: number;
  idempotency_key: string;
  actor: string;
  profile?: string | null;
}

export interface StageBootstrapInstallResponse {
  run_id: string;
  stage_id: string;
  step_id: string;
  status: string;
  command: string | null;
  exit_code: number | null;
  started_at: string | null;
  completed_at: string | null;
  state_version: number;
  event_sequence: number;
  artifact_ids: string[];
  idempotent_replay: boolean;
}

export interface StageBootstrapStatusResponse {
  run_id: string;
  stage_id: string;
  step_id: string;
  name: string;
  status: string;
  command: string | null;
  exit_code: number | null;
  started_at: string | null;
  completed_at: string | null;
  artifact_ids: string[];
}

type ApiClient = ReturnType<typeof createApiClient>;

export function prepareStage(
  runId: string,
  stageId: string,
  request: StagePrepareRequest,
  client: ApiClient = apiClient,
): Promise<StagePrepareResponse> {
  // Note: stage_key is in the request body; the backend route is /stages/prepare (no stage_id in URL)
  return client.post<StagePrepareResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/stages/prepare`,
    request,
  );
}

export function createSandbox(
  runId: string,
  stageId: string,
  request: StageSandboxRequest,
  client: ApiClient = apiClient,
): Promise<StageSandboxResponse> {
  return client.post<StageSandboxResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageId)}/sandbox`,
    request,
  );
}

export function getG07Status(
  runId: string,
  stageId: string,
  client: ApiClient = apiClient,
): Promise<G07ReviewResponse> {
  const params = new URLSearchParams({ stage_id: stageId });
  return client.get<G07ReviewResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/approvals/G07?${params.toString()}`,
  );
}

export function decideG07(
  runId: string,
  request: G07DecisionRequest,
  client: ApiClient = apiClient,
): Promise<G07ReviewResponse> {
  return client.post<G07ReviewResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/approvals/G07/decisions`,
    request,
  );
}

export function runBootstrapInstall(
  runId: string,
  stageId: string,
  request: StageBootstrapInstallRequest,
  client: ApiClient = apiClient,
): Promise<StageBootstrapInstallResponse> {
  return client.post<StageBootstrapInstallResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageId)}/bootstrap-install`,
    request,
  );
}

export function getBootstrapInstallStatus(
  runId: string,
  stageId: string,
  client: ApiClient = apiClient,
): Promise<StageBootstrapStatusResponse> {
  return client.get<StageBootstrapStatusResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageId)}/steps/bootstrap-install`,
  );
}
