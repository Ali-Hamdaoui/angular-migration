import { apiClient, type createApiClient } from "./client";
import type {
  AuthoritativeRunMutationResultDto,
  AuthoritativeRunStateDto,
  CancelAuthoritativeRunRequestDto,
  CreateAuthoritativeRunRequestDto,
  StartAuthoritativeRunRequestDto,
} from "@/types/generated/api";

type ApiClient = ReturnType<typeof createApiClient>;

export function createAuthoritativeRun(
  request: CreateAuthoritativeRunRequestDto,
  client: ApiClient = apiClient,
): Promise<AuthoritativeRunMutationResultDto> {
  return client.post<AuthoritativeRunMutationResultDto>("/api/v1/runs", request);
}

export function startAuthoritativeRun(
  runId: string,
  request: StartAuthoritativeRunRequestDto,
  client: ApiClient = apiClient,
): Promise<AuthoritativeRunMutationResultDto> {
  return client.post<AuthoritativeRunMutationResultDto>(`/api/v1/runs/${encodeURIComponent(runId)}/start`, request);
}

export function retryAuthoritativeSourceIntake(
  runId: string,
  request: StartAuthoritativeRunRequestDto,
  client: ApiClient = apiClient,
): Promise<AuthoritativeRunMutationResultDto> {
  return client.post<AuthoritativeRunMutationResultDto>(`/api/v1/runs/${encodeURIComponent(runId)}/retry-source-intake`, request);
}

export function cancelAuthoritativeRun(
  runId: string,
  request: CancelAuthoritativeRunRequestDto,
  client: ApiClient = apiClient,
): Promise<AuthoritativeRunMutationResultDto> {
  return client.post<AuthoritativeRunMutationResultDto>(`/api/v1/runs/${encodeURIComponent(runId)}/cancel`, request);
}

export function getAuthoritativeRunState(
  runId: string,
  client: ApiClient = apiClient,
): Promise<AuthoritativeRunStateDto> {
  return client.get<AuthoritativeRunStateDto>(`/api/v1/runs/${encodeURIComponent(runId)}/state`);
}
