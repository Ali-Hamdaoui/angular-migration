import { apiClient, type createApiClient } from "./client";
import type {
  StageValidationRequest,
  StageValidationResponse,
} from "@/types/stageValidation";

type ApiClient = ReturnType<typeof createApiClient>;
function runPath(runId: string) { return `/api/v1/runs/${encodeURIComponent(runId)}`; }

export function getStageValidation(
  runId: string,
  stageId: string,
  client: ApiClient = apiClient,
): Promise<StageValidationResponse> {
  return client.get<StageValidationResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/validation/install-static`,
  );
}

export function startStageValidation(
  runId: string,
  stageId: string,
  request: StageValidationRequest,
  client: ApiClient = apiClient,
): Promise<StageValidationResponse> {
  return client.post<StageValidationResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/validation/install-static`,
    request,
  );
}

export function cancelStageValidation(
  runId: string,
  stageId: string,
  client: ApiClient = apiClient,
): Promise<StageValidationResponse> {
  return client.post<StageValidationResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/validation/install-static/cancel`,
    {},
  );
}

export function getStageValidationLogs(
  runId: string,
  stageId: string,
  validationId: string,
  client: ApiClient = apiClient,
): Promise<{ logs: string[] }> {
  return client.get<{ logs: string[] }>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/validation/install-static/${encodeURIComponent(validationId)}/logs`,
  );
}
