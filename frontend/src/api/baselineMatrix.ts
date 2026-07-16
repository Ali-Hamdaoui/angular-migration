import { apiClient, type createApiClient } from "./client";
import type { BaselineMatrixKind, BaselineTargetInventoryResponse, BaselineValidationRequest, BaselineValidationResponse } from "@/types/baselineMatrix";

type ApiClient = ReturnType<typeof createApiClient>;

function runPath(runId: string) { return encodeURIComponent(runId); }

export function getBaselineTargets(runId: string, client: ApiClient = apiClient): Promise<BaselineTargetInventoryResponse> {
  return client.get<BaselineTargetInventoryResponse>(`/api/v1/runs/${runPath(runId)}/baseline/targets`);
}

export function getBaselineValidation(runId: string, kind: BaselineMatrixKind, client: ApiClient = apiClient): Promise<BaselineValidationResponse> {
  return client.get<BaselineValidationResponse>(`/api/v1/runs/${runPath(runId)}/baseline/${kind}`);
}

export function startBaselineValidation(runId: string, kind: BaselineMatrixKind, request: BaselineValidationRequest, client: ApiClient = apiClient): Promise<BaselineValidationResponse> {
  return client.post<BaselineValidationResponse>(`/api/v1/runs/${runPath(runId)}/${kind === "build" ? "baseline/builds" : kind === "test" ? "baseline/tests" : "baseline/lint"}`, request);
}
