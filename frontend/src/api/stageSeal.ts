import { apiClient, type createApiClient } from "./client";
import type {
  StageSealRequest,
  StageSealResponse,
} from "@/types/stageSeal";

type ApiClient = ReturnType<typeof createApiClient>;
function runPath(runId: string) { return `/api/v1/runs/${encodeURIComponent(runId)}`; }

export function getStageSeal(
  runId: string,
  stageId: string,
  client: ApiClient = apiClient,
): Promise<StageSealResponse> {
  return client.get<StageSealResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/seal`,
  );
}

export function submitStageSealRequest(
  runId: string,
  stageId: string,
  request: StageSealRequest,
  client: ApiClient = apiClient,
): Promise<StageSealResponse> {
  return client.post<StageSealResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/seal`,
    request,
  );
}

export function submitG12Decision(
  runId: string,
  stageId: string,
  request: StageSealRequest,
  client: ApiClient = apiClient,
): Promise<StageSealResponse> {
  return client.post<StageSealResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/seal/g12`,
    request,
  );
}

export function startCopyForward(
  runId: string,
  stageId: string,
  client: ApiClient = apiClient,
): Promise<StageSealResponse> {
  return client.post<StageSealResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/seal/copy-forward`,
    {},
  );
}
