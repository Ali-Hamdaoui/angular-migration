import { apiClient, type createApiClient } from "./client";
import type {
  StageAssuranceRequest,
  StageAssuranceResponse,
} from "@/types/stageAssurance";

type ApiClient = ReturnType<typeof createApiClient>;
function runPath(runId: string) { return `/api/v1/runs/${encodeURIComponent(runId)}`; }

export function getStageAssurance(
  runId: string,
  stageId: string,
  client: ApiClient = apiClient,
): Promise<StageAssuranceResponse> {
  return client.get<StageAssuranceResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/assurance`,
  );
}

export function updateStageAssurance(
  runId: string,
  stageId: string,
  request: StageAssuranceRequest,
  client: ApiClient = apiClient,
): Promise<StageAssuranceResponse> {
  return client.post<StageAssuranceResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/assurance`,
    request,
  );
}

export function submitG09Decision(
  runId: string,
  stageId: string,
  request: StageAssuranceRequest,
  client: ApiClient = apiClient,
): Promise<StageAssuranceResponse> {
  return client.post<StageAssuranceResponse>(
    `${runPath(runId)}/stages/${encodeURIComponent(stageId)}/assurance/g09`,
    request,
  );
}
