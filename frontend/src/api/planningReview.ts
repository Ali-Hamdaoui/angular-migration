import { apiClient, type createApiClient } from "./client";
import type { G06DecisionRequest, G06DecisionResponse, PlanRevisionRequest, PlanReviewResponse, PlanningExplanationRequest } from "@/types/planning";

type Client = ReturnType<typeof createApiClient>;
const path = (runId: string) => encodeURIComponent(runId);

export function getPlanReview(runId: string, client: Client = apiClient) {
  return client.get<PlanReviewResponse>(`/api/v1/runs/${path(runId)}/plan/review`);
}
export function revisePlan(runId: string, request: PlanRevisionRequest, client: Client = apiClient) {
  return client.post<PlanReviewResponse>(`/api/v1/runs/${path(runId)}/plan/revisions`, request);
}
export function explainPlan(runId: string, request: PlanningExplanationRequest, client: Client = apiClient) {
  return client.post<PlanReviewResponse>(`/api/v1/runs/${path(runId)}/plan/explanation`, request);
}
export function decideG06(runId: string, request: G06DecisionRequest, client: Client = apiClient) {
  return client.post<G06DecisionResponse>(`/api/v1/runs/${path(runId)}/approvals/G06/decisions`, request);
}
