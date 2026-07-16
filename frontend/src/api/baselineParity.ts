import { apiClient, type createApiClient } from "./client";
import type { BaselineParityCaptureRequest, BaselineParityResponse } from "@/types/baselineParity";

type ApiClient = ReturnType<typeof createApiClient>;
function runPath(runId: string) { return encodeURIComponent(runId); }

export function captureBaselineParity(runId: string, request: BaselineParityCaptureRequest, client: ApiClient = apiClient): Promise<BaselineParityResponse> {
  return client.post<BaselineParityResponse>(`/api/v1/runs/${runPath(runId)}/baseline/parity`, request);
}

export function getBaselineParitySection(runId: string, section: "failures" | "routes" | "backend-integration" | "anchors", client: ApiClient = apiClient): Promise<BaselineParityResponse> {
  return client.get<BaselineParityResponse>(`/api/v1/runs/${runPath(runId)}/baseline/${section}`);
}
