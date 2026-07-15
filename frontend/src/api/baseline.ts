import { apiClient, type createApiClient } from "./client";
import type {
  BaselineInstallAuthorizationRequest,
  BaselinePrequalifyRequest,
  BaselineResponse,
  BaselineWorkspaceRequest,
} from "@/types/generated/api";

type ApiClient = ReturnType<typeof createApiClient>;

export function getBaseline(runId: string, client: ApiClient = apiClient): Promise<BaselineResponse> {
  return client.get<BaselineResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/baseline`);
}

export function createBaselineWorkspace(runId: string, request: BaselineWorkspaceRequest, client: ApiClient = apiClient): Promise<BaselineResponse> {
  return client.post<BaselineResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/baseline/workspace`, request);
}

export function prequalifyBaseline(runId: string, request: BaselinePrequalifyRequest, client: ApiClient = apiClient): Promise<BaselineResponse> {
  return client.post<BaselineResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/baseline/prequalify`, request);
}

export function authorizeBaselineInstall(runId: string, request: BaselineInstallAuthorizationRequest, client: ApiClient = apiClient): Promise<BaselineResponse> {
  return client.post<BaselineResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/baseline/install-authorizations`, request);
}
