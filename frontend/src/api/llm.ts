import { apiClient, type createApiClient } from "./client";
import type { LlmActivityResponse, LlmInvocationResponse, LlmReadinessResponse, LlmSmokeRequest, LlmUsageResponse } from "@/types/llm";

type ApiClient = ReturnType<typeof createApiClient>;

export function getLlmReadiness(client: ApiClient = apiClient): Promise<LlmReadinessResponse> {
  return client.get<LlmReadinessResponse>("/api/v1/llm/readiness");
}

export function invokeLlmSmoke(request: LlmSmokeRequest, client: ApiClient = apiClient): Promise<LlmInvocationResponse> {
  return client.post<LlmInvocationResponse>("/api/v1/llm/smoke", request);
}

export function getLlmActivity(runId: string, client: ApiClient = apiClient): Promise<LlmActivityResponse> {
  return client.get<LlmActivityResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/llm/activity`);
}

export function getLlmUsage(runId: string, client: ApiClient = apiClient): Promise<LlmUsageResponse> {
  return client.get<LlmUsageResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/usage`);
}
