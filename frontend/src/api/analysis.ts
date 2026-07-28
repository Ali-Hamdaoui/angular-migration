import { apiClient, type createApiClient } from "./client";
import type { AnalysisArtifactInput, AnalysisResponse, G04Decision, G04DecisionResponse } from "@/types/analysis";

type Client = ReturnType<typeof createApiClient>;

export type AnalysisCreateRequest = {
  expected_state_version: number;
  idempotency_key: string;
  prerequisite_artifacts?: AnalysisArtifactInput[];
  workspace_fingerprint?: string | null;
  plan_version?: string | null;
  correlation_id?: string | null;
};

export type AnalysisRetryRequest = {
  expected_state_version: number;
  failed_analysis_id: string;
  idempotency_key: string;
  reason: string;
};

export type G04DecisionRequest = {
  expected_state_version: number;
  idempotency_key: string;
  gate_version: string;
  package_checksum: string;
  workspace_fingerprint?: string | null;
  plan_version?: string | null;
  decision: G04Decision;
  comment?: string | null;
};

const path = (runId: string) => `/api/v1/runs/${encodeURIComponent(runId)}`;

export function getAnalysis(runId: string, client: Client = apiClient) {
  return client.get<AnalysisResponse>(`${path(runId)}/analysis`);
}

export function generateAnalysis(runId: string, request: AnalysisCreateRequest, client: Client = apiClient) {
  return client.post<AnalysisResponse>(`${path(runId)}/analysis`, request);
}

export function retryAnalysis(runId: string, request: AnalysisRetryRequest, client: Client = apiClient) {
  return client.post<AnalysisResponse>(`${path(runId)}/analysis/retries`, request);
}

export function decideG04(runId: string, request: G04DecisionRequest, client: Client = apiClient) {
  return client.post<G04DecisionResponse>(`${path(runId)}/approvals/G04/decisions`, request);
}
