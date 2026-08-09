import { apiClient, type createApiClient } from "./client";
import type {
  BaselineInstallAuthorizationRequest,
  BaselineInstallCancelRequest,
  BaselineInstallRequest,
  BaselineInstallResponse,
  BaselinePrequalifyRequest,
  BaselineResponse,
  BaselineWorkspaceRequest,
} from "@/types/generated/api";

type ApiClient = ReturnType<typeof createApiClient>;

function normalizeBaseline(value: BaselineResponse): BaselineResponse {
  return {
    ...value,
    sources: Array.isArray(value.sources) ? value.sources : [],
    scripts: Array.isArray(value.scripts) ? value.scripts : [],
    blockers: Array.isArray(value.blockers) ? value.blockers : [],
    warnings: Array.isArray(value.warnings) ? value.warnings : [],
    artifact_ids: Array.isArray(value.artifact_ids) ? value.artifact_ids : [],
  };
}

function normalizeInstallation(value: BaselineInstallResponse): BaselineInstallResponse {
  return {
    ...value,
    blockers: Array.isArray(value.blockers) ? value.blockers : [],
    artifact_ids: Array.isArray(value.artifact_ids) ? value.artifact_ids : [],
  };
}

export async function getBaseline(runId: string, client: ApiClient = apiClient): Promise<BaselineResponse> {
  return normalizeBaseline(await client.get<BaselineResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/baseline`));
}

export async function createBaselineWorkspace(runId: string, request: BaselineWorkspaceRequest, client: ApiClient = apiClient): Promise<BaselineResponse> {
  return normalizeBaseline(await client.post<BaselineResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/baseline/workspace`, request));
}

export async function prequalifyBaseline(runId: string, request: BaselinePrequalifyRequest, client: ApiClient = apiClient): Promise<BaselineResponse> {
  return normalizeBaseline(await client.post<BaselineResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/baseline/prequalify`, request));
}

export async function authorizeBaselineInstall(runId: string, request: BaselineInstallAuthorizationRequest, client: ApiClient = apiClient): Promise<BaselineResponse> {
  return normalizeBaseline(await client.post<BaselineResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/baseline/install-authorizations`, request));
}

export async function installBaseline(runId: string, request: BaselineInstallRequest, client: ApiClient = apiClient): Promise<BaselineInstallResponse> {
  return normalizeInstallation(await client.post<BaselineInstallResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/baseline/install`, request));
}

export async function getBaselineCommand(runId: string, executionId: string, client: ApiClient = apiClient): Promise<BaselineInstallResponse> {
  return normalizeInstallation(await client.get<BaselineInstallResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/commands/${encodeURIComponent(executionId)}`));
}
export async function cancelBaseline(runId: string, executionId: string, request: BaselineInstallCancelRequest, client: ApiClient = apiClient): Promise<BaselineInstallResponse> {
  return normalizeInstallation(await client.post<BaselineInstallResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/commands/${encodeURIComponent(executionId)}/cancel`, request));
}
