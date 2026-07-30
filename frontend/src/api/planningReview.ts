import { apiClient, type createApiClient } from "./client";
import type { G06DecisionRequest, G06DecisionResponse, PlanRevisionRequest, PlanReviewResponse, PlanningExplanationRequest } from "@/types/planning";

type Client = ReturnType<typeof createApiClient>;
const path = (runId: string) => encodeURIComponent(runId);
const record = (value: unknown): Record<string, string> => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, string> : {};
const normalizeReview = (review: PlanReviewResponse): PlanReviewResponse => ({
  ...review,
  artifact_ids: Array.isArray(review.artifact_ids) ? review.artifact_ids.filter((id): id is string => typeof id === "string") : [],
  artifact_checksums: record(review.artifact_checksums),
  artifact_links: record(review.artifact_links),
});

export async function getPlanReview(runId: string, client: Client = apiClient) {
  return normalizeReview(await client.get<PlanReviewResponse>(`/api/v1/runs/${path(runId)}/plan/review`));
}
export async function revisePlan(runId: string, request: PlanRevisionRequest, client: Client = apiClient) {
  return normalizeReview(await client.post<PlanReviewResponse>(`/api/v1/runs/${path(runId)}/plan/revisions`, request));
}
export async function explainPlan(runId: string, request: PlanningExplanationRequest, client: Client = apiClient) {
  return normalizeReview(await client.post<PlanReviewResponse>(`/api/v1/runs/${path(runId)}/plan/explanation`, request));
}
export function decideG06(runId: string, request: G06DecisionRequest, client: Client = apiClient) {
  return client.post<G06DecisionResponse>(`/api/v1/runs/${path(runId)}/approvals/G06/decisions`, request);
}
