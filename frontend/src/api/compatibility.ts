import { apiClient, type createApiClient } from "./client";
import type { FeasibilityCreateRequest, FeasibilityResponse, G05DecisionRequest, G05DecisionResponse } from "@/types/compatibility";

type Client = ReturnType<typeof createApiClient>;
const runPath = (runId: string) => encodeURIComponent(runId);

export function getFeasibility(runId: string, client: Client = apiClient) {
  return client.get<FeasibilityResponse>(`/api/v1/runs/${runPath(runId)}/feasibility`);
}

export function resolveFeasibility(runId: string, request: FeasibilityCreateRequest, client: Client = apiClient) {
  return client.post<FeasibilityResponse>(`/api/v1/runs/${runPath(runId)}/feasibility`, request);
}

export function decideG05(runId: string, request: G05DecisionRequest, client: Client = apiClient) {
  return client.post<G05DecisionResponse>(`/api/v1/runs/${runPath(runId)}/approvals/G05/decisions`, request);
}
