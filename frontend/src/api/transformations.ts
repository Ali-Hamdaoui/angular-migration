/** API client for G03 transformation endpoints. */

import { apiClient, type createApiClient } from "./client";
import type {
  AngularUpdateRequest,
  AngularUpdateResponse,
  G08DecisionRequest,
  G08ReviewResponse,
  TargetVersionResponse,
  TransformationEvidenceRequest,
  TransformationEvidenceResponse,
} from "@/types/transformation";

type ApiClient = ReturnType<typeof createApiClient>;

export async function startAngularUpdate(
  runId: string,
  stageId: string,
  request: AngularUpdateRequest,
  client: ApiClient = apiClient,
): Promise<AngularUpdateResponse> {
  return client.post<AngularUpdateResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageId)}/angular-update`,
    request,
  );
}

export async function getAngularUpdate(
  runId: string,
  stageId: string,
  client: ApiClient = apiClient,
): Promise<AngularUpdateResponse> {
  return client.get<AngularUpdateResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageId)}/angular-update`,
  );
}

export async function getTargetVersion(
  runId: string,
  stageId: string,
  client: ApiClient = apiClient,
): Promise<AngularUpdateResponse> {
  return client.get<AngularUpdateResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageId)}/target-version`,
  );
}

export async function generateTransformationEvidence(
  runId: string,
  stageId: string,
  request: TransformationEvidenceRequest,
  client: ApiClient = apiClient,
): Promise<TransformationEvidenceResponse> {
  return client.post<TransformationEvidenceResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageId)}/transformation-evidence`,
    request,
  );
}

export async function getTransformationEvidence(
  runId: string,
  stageId: string,
  client: ApiClient = apiClient,
): Promise<TransformationEvidenceResponse> {
  return client.get<TransformationEvidenceResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageId)}/transformation-evidence`,
  );
}

export async function getG08Approval(
  runId: string,
  stageId: string,
  gateId: string,
  client: ApiClient = apiClient,
): Promise<G08ReviewResponse> {
  return client.get<G08ReviewResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageId)}/approvals/${encodeURIComponent(gateId)}`,
  );
}

export async function decideG08(
  runId: string,
  stageId: string,
  gateId: string,
  request: G08DecisionRequest,
  client: ApiClient = apiClient,
): Promise<G08ReviewResponse> {
  return client.post<G08ReviewResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageId)}/approvals/${encodeURIComponent(gateId)}/decisions`,
    request,
  );
}

export async function completeAngularUpdate(
  runId: string,
  stageId: string,
  request: { expected_state_version: number; idempotency_key: string; actor: string },
  client: ApiClient = apiClient,
): Promise<AngularUpdateResponse> {
  return client.post<AngularUpdateResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageId)}/angular-update/complete`,
    request,
  );
}

export async function verifyTargetVersion(
  runId: string,
  stageId: string,
  request: { expected_state_version: number; idempotency_key: string; actor: string },
  client: ApiClient = apiClient,
): Promise<AngularUpdateResponse> {
  return client.post<AngularUpdateResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageId)}/target-version/verify`,
    request,
  );
}

export async function getTargetVersionTyped(
  runId: string,
  stageId: string,
  client: ApiClient = apiClient,
): Promise<TargetVersionResponse> {
  return client.get<TargetVersionResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageId)}/target-version`,
  );
}

export async function initializeG08(
  runId: string,
  stageId: string,
  gateId: string,
  request: G08DecisionRequest,
  client: ApiClient = apiClient,
): Promise<G08ReviewResponse> {
  return client.post<G08ReviewResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageId)}/approvals/${encodeURIComponent(gateId)}/package`,
    request,
  );
}
