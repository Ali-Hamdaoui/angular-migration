import { apiClient, type createApiClient } from "./client";
import type { BaselineRepairRequest, BaselineRepairResponse } from "@/types/baselineRepair";

type ApiClient = ReturnType<typeof createApiClient>;

export function applyBaselineRepair(runId: string, request: BaselineRepairRequest, client: ApiClient = apiClient): Promise<BaselineRepairResponse> {
  return client.post<BaselineRepairResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/baseline/repairs`, request);
}
