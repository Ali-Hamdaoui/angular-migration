import { apiClient, type createApiClient } from "./client";
import type { PlanCreateRequest, PlanResponse } from "@/types/planning";

type Client = ReturnType<typeof createApiClient>;
const runPath = (runId: string) => encodeURIComponent(runId);
const stagePath = (stageId: string) => encodeURIComponent(stageId);

export function getPlan(runId: string, client: Client = apiClient) {
  return client.get<PlanResponse>(`/api/v1/runs/${runPath(runId)}/plan`);
}

export function getStagePlan(runId: string, stageId: string, client: Client = apiClient) {
  return client.get<PlanResponse>(`/api/v1/runs/${runPath(runId)}/stages/${stagePath(stageId)}/plan`);
}

export function createPlan(runId: string, request: PlanCreateRequest, client: Client = apiClient) {
  return client.post<PlanResponse>(`/api/v1/runs/${runPath(runId)}/plans`, request);
}
