import { apiClient } from "./client";
import type { TransformationProjection } from "@/types/transformation";

export function getTransformation(runId: string) {
  return apiClient.get<TransformationProjection>(`/api/v1/runs/${runId}/transformation`);
}

export function cancelTransformation(
  runId: string,
  body: { expected_state_version: number; idempotency_key: string; correlation_id: string },
) {
  return apiClient.post<TransformationProjection>(
    `/api/v1/runs/${runId}/transformation/cancel`,
    body,
  );
}
