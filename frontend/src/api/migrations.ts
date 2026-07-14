import { apiClient, type createApiClient } from "./client";
import type {
  CreateMockMigrationRequestDto,
  DiagnosticsSummaryDto,
  ArtifactRefDto,
  HealthResponse,
  MigrationRunDto,
  PreflightRequestDto,
  PreflightResultDto,
  VersionResponse,
  PathValidationRequest,
  PathValidationResult
} from "@/types/generated/api";

type ApiClient = ReturnType<typeof createApiClient>;

export type ArtifactContentResponse = { artifact: ArtifactRefDto; content: string; created_by: string | null };

export function getHealth(client: ApiClient = apiClient): Promise<HealthResponse> {
  return client.get<HealthResponse>("/health");
}

export function getVersion(client: ApiClient = apiClient): Promise<VersionResponse> {
  return client.get<VersionResponse>("/version");
}

export function validatePreflight(request: PreflightRequestDto, client: ApiClient = apiClient): Promise<PreflightResultDto> {
  return client.post<PreflightResultDto>("/migrations/preflight", request);
}

export function createMockMigration(request: CreateMockMigrationRequestDto, client: ApiClient = apiClient): Promise<MigrationRunDto> {
  return client.post<MigrationRunDto>("/migrations/mock", request);
}

export function getMockMigrationState(client: ApiClient = apiClient): Promise<MigrationRunDto> {
  return client.get<MigrationRunDto>("/migrations/mock-state");
}

export function getMigrationState(runId: string, client: ApiClient = apiClient): Promise<MigrationRunDto> {
  return client.get<MigrationRunDto>(`/migrations/${runId}/state`);
}

export function getArtifactById(artifactId: string, client: ApiClient = apiClient): Promise<ArtifactContentResponse> {
  return client.get<ArtifactContentResponse>(`/artifacts/${artifactId}`);
}
export function getMigrationDiagnostics(runId: string, stageId?: string, client: ApiClient = apiClient): Promise<DiagnosticsSummaryDto> {
  const suffix = stageId ? `?stage_id=${encodeURIComponent(stageId)}` : "";
  return client.get<DiagnosticsSummaryDto>(`/migrations/${runId}/diagnostics${suffix}`);
}
export function validatePaths(
  request: PathValidationRequest,
  client: ApiClient = apiClient,
): Promise<PathValidationResult> {
  return client.post<PathValidationResult>("/sources/validate-paths", request);
}

export function getPathValidation(
  validationId: string,
  client: ApiClient = apiClient,
): Promise<PathValidationResult> {
  return client.get<PathValidationResult>("/sources/path-validations/" + encodeURIComponent(validationId));
}
