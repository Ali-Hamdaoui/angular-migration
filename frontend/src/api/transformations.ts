/** API client for G03 transformation endpoints. */

import type {
  AngularUpdateRequest,
  AngularUpdateResponse,
  G08DecisionRequest,
  G08ReviewResponse,
  TransformationEvidenceRequest,
  TransformationEvidenceResponse,
} from "@/types/transformation";
import { apiClient } from "./client";

const BASE = "/api/v1/runs";

export async function startAngularUpdate(
  runId: string,
  stageId: string,
  request: AngularUpdateRequest,
): Promise<AngularUpdateResponse> {
  return apiClient(`${BASE}/${runId}/stages/${stageId}/angular-update`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function getAngularUpdate(
  runId: string,
  stageId: string,
): Promise<AngularUpdateResponse> {
  return apiClient(`${BASE}/${runId}/stages/${stageId}/angular-update`);
}

export async function getTargetVersion(
  runId: string,
  stageId: string,
): Promise<AngularUpdateResponse> {
  return apiClient(`${BASE}/${runId}/stages/${stageId}/target-version`);
}

export async function generateTransformationEvidence(
  runId: string,
  stageId: string,
  request: TransformationEvidenceRequest,
): Promise<TransformationEvidenceResponse> {
  return apiClient(`${BASE}/${runId}/stages/${stageId}/transformation-evidence`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function getTransformationEvidence(
  runId: string,
  stageId: string,
): Promise<TransformationEvidenceResponse> {
  return apiClient(`${BASE}/${runId}/stages/${stageId}/transformation-evidence`);
}

export async function getG08Approval(
  runId: string,
  stageId: string,
  gateId: string,
): Promise<G08ReviewResponse> {
  return apiClient(`${BASE}/${runId}/stages/${stageId}/approvals/${gateId}`);
}

export async function decideG08(
  runId: string,
  stageId: string,
  gateId: string,
  request: G08DecisionRequest,
): Promise<G08ReviewResponse> {
  return apiClient(`${BASE}/${runId}/stages/${stageId}/approvals/${gateId}/decisions`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function initializeG08(
  runId: string,
  stageId: string,
  gateId: string,
  request: G08DecisionRequest,
): Promise<G08ReviewResponse> {
  return apiClient(`${BASE}/${runId}/stages/${stageId}/approvals/${gateId}/package`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}
