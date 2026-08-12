import { apiClient, type createApiClient } from "./client";
import type { FeasibilityResponse, G05DecisionRequest, G05DecisionResponse } from "@/types/compatibility";
import type { PlanningCommandResponse } from "@/types/generated/api";

type Client = ReturnType<typeof createApiClient>;
const runPath = (runId: string) => encodeURIComponent(runId);

export function getFeasibility(runId: string, client: Client = apiClient) {
  return client.get<FeasibilityResponse>(`/api/v1/runs/${runPath(runId)}/feasibility`);
}

export function queueFeasibilityResolution(runId: string, request: { expected_state_version: number; idempotency_key: string }, client: Client = apiClient) {
  return client.post<PlanningCommandResponse>(`/api/v1/runs/${runPath(runId)}/feasibility/actions/resolve`, request);
}

export function decideG05(runId: string, request: G05DecisionRequest, client: Client = apiClient) {
  return client.post<G05DecisionResponse>(`/api/v1/runs/${runPath(runId)}/approvals/G05/decisions`, request);
}
