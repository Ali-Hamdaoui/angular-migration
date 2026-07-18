import { apiClient, type createApiClient } from "./client";
import type { ExecutionProfileResolveRequest, ExecutionProfileResponse, ExecutionProfileSelectRequest } from "@/types/generated/api";
type ApiClient = ReturnType<typeof createApiClient>;
export function getExecutionProfiles(runId: string, client: ApiClient = apiClient): Promise<ExecutionProfileResponse> { return client.get<ExecutionProfileResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/execution-profiles`); }
export function resolveExecutionProfiles(runId: string, request: ExecutionProfileResolveRequest, client: ApiClient = apiClient): Promise<ExecutionProfileResponse> { return client.post<ExecutionProfileResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/execution-profiles/resolve`, request); }
export function selectExecutionProfile(runId: string, profileId: string, request: ExecutionProfileSelectRequest, client: ApiClient = apiClient): Promise<ExecutionProfileResponse> { return client.post<ExecutionProfileResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/execution-profiles/${encodeURIComponent(profileId)}/select`, request); }
