import { apiClient, type createApiClient } from "./client";
import type { G02DecisionRequest, G02PackageInitializationRequest, G02ReviewResponse } from "@/types/generated/api";

type ApiClient = ReturnType<typeof createApiClient>;

export function getG02Review(runId: string, client: ApiClient = apiClient): Promise<G02ReviewResponse> {
  return client.get<G02ReviewResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/approvals/G02`);
}

export function decideG02(runId: string, request: G02DecisionRequest, client: ApiClient = apiClient): Promise<G02ReviewResponse> {
  return client.post<G02ReviewResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/approvals/G02/decisions`, request);
}

export function initializeG02(runId: string, request: G02PackageInitializationRequest, client: ApiClient = apiClient): Promise<G02ReviewResponse> {
  return client.post<G02ReviewResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/approvals/G02/package`, request);
}
