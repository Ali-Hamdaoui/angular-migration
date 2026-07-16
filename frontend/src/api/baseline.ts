import { apiClient, type createApiClient } from "./client";
import type {
  BaselineInstallAuthorizationRequest,
  BaselineInstallRequest,
  BaselineInstallResponse,
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

export function installBaseline(runId: string, request: BaselineInstallRequest, client: ApiClient = apiClient): Promise<BaselineInstallResponse> {
  return client.post<BaselineInstallResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/baseline/install`, request);
}

export function getBaselineCommand(runId: string, executionId: string, client: ApiClient = apiClient): Promise<BaselineInstallResponse> {
  return client.get<BaselineInstallResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/commands/${encodeURIComponent(executionId)}`);
}