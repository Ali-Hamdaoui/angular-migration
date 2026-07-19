import { apiClient, type createApiClient } from "./client";
import type {
  StageBuildRequest,
  StageBuildResponse,
} from "@/types/stageBuild";

type ApiClient = ReturnType<typeof createApiClient>;
function runPath(runId: string) { return `/api/v1/runs/${encodeURIComponent(runId)}`; }

export function getStageBuildMatrix(
  runId: string,
  stageId: string,
  client: ApiClient = apiClient,
): Promise<StageBuildResponse> {
  return client.get<StageBuildResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/build-matrix`,
  );
}

export function startStageBuild(
  runId: string,
  stageId: string,
  request: StageBuildRequest,
  client: ApiClient = apiClient,
): Promise<StageBuildResponse> {
  return client.post<StageBuildResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/build-matrix`,
    request,
  );
}

export function cancelStageBuild(
  runId: string,
  stageId: string,
  client: ApiClient = apiClient,
): Promise<StageBuildResponse> {
  return client.post<StageBuildResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/build-matrix/cancel`,
    {},
  );
}
