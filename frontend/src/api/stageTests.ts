import { apiClient, type createApiClient } from "./client";
import type {
  StageTestRequest,
  StageTestResponse,
} from "@/types/stageTests";

type ApiClient = ReturnType<typeof createApiClient>;
function runPath(runId: string) { return `/api/v1/runs/${encodeURIComponent(runId)}`; }

export function getStageTests(
  runId: string,
  stageId: string,
  client: ApiClient = apiClient,
): Promise<StageTestResponse> {
  return client.get<StageTestResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/tests`,
  );
}

export function startStageTests(
  runId: string,
  stageId: string,
  request: StageTestRequest,
  client: ApiClient = apiClient,
): Promise<StageTestResponse> {
  return client.post<StageTestResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/tests`,
    request,
  );
}

export function cancelStageTests(
  runId: string,
  stageId: string,
  client: ApiClient = apiClient,
): Promise<StageTestResponse> {
  return client.post<StageTestResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/tests/cancel`,
    {},
  );
}

export function getStageTestLogs(
  runId: string,
  stageId: string,
  testId: string,
  client: ApiClient = apiClient,
): Promise<{ logs: string[] }> {
  return client.get<{ logs: string[] }>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/tests/${encodeURIComponent(testId)}/logs`,
  );
}
