import { apiClient, type createApiClient } from "./client";
import type { HealthResponse, MigrationRunDto, VersionResponse } from "@/types/generated/api";

type ApiClient = ReturnType<typeof createApiClient>;

export function getHealth(client: ApiClient = apiClient): Promise<HealthResponse> {
  return client.get<HealthResponse>("/health");
}

export function getVersion(client: ApiClient = apiClient): Promise<VersionResponse> {
  return client.get<VersionResponse>("/version");
}

export function getMockMigrationState(client: ApiClient = apiClient): Promise<MigrationRunDto> {
  return client.get<MigrationRunDto>("/migrations/mock-state");
}