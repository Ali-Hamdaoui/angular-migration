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

export function decideTransformationGate(
  runId: string,
  gateId: string,
  body: {
    expected_state_version: number;
    idempotency_key: string;
    package_checksum: string;
    workspace_fingerprint: string;
    decision: "approve" | "reject";
    correlation_id: string;
  },
) {
  return apiClient.post(
    `/api/v1/runs/${runId}/transformation/gates/${gateId}/decisions`,
    body,
  );
}

export function decideTransformationPrompt(
  runId: string,
  promptId: string,
  body: {
    expected_state_version: number;
    idempotency_key: string;
    prompt_checksum: string;
    selected_option_id: string;
    correlation_id: string;
  },
) {
  return apiClient.post(
    `/api/v1/runs/${runId}/transformation/prompts/${promptId}/decision`,
    body,
  );
}

export function restartTransformation(
  runId: string,
  body: { expected_state_version: number; idempotency_key: string; correlation_id: string },
) {
  return apiClient.post<TransformationProjection>(
    `/api/v1/runs/${runId}/transformation/restart`,
    body,
  );
}
