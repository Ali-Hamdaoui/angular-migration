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

type RepairDecisionBody = {
  attempt_id: string;
  proposal_id: string;
  base_checksum: string;
  idempotency_key: string;
};

export function requestRepairRevision(
  runId: string,
  attemptId: string,
  body: RepairDecisionBody & { instruction: string },
) {
  return apiClient.post(
    `/api/v1/runs/${encodeURIComponent(runId)}/transformation/repairs/${encodeURIComponent(attemptId)}/revisions`,
    body,
  );
}

export function rejectRepair(
  runId: string,
  attemptId: string,
  body: RepairDecisionBody,
) {
  return apiClient.post(
    `/api/v1/runs/${encodeURIComponent(runId)}/transformation/repairs/${encodeURIComponent(attemptId)}/reject`,
    body,
  );
}
