import { apiClient, type createApiClient } from "./client";
import type {
  ProposerInvokeRequest,
  ProposerResponse,
  ReviewerInvokeRequest,
  ReviewerResponse,
  RepairProposalResponse,
  G10DecisionRequest,
  G10DecisionResponse,
} from "@/types/repair";

type ApiClient = ReturnType<typeof createApiClient>;

/**
 * GET the current Proposer result for a repair attempt.
 * Returns the diagnosis, candidate diff, model provenance, and usage.
 */
export function getProposer(
  runId: string,
  repairAttemptId: string,
  client: ApiClient = apiClient,
): Promise<ProposerResponse> {
  return client.get<ProposerResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/repair-attempts/${encodeURIComponent(repairAttemptId)}/proposer`,
  );
}

/**
 * POST to invoke the Proposer LLM for a repair attempt.
 * Idempotent; returns the existing result if already computed.
 */
export function invokeProposer(
  runId: string,
  repairAttemptId: string,
  request: ProposerInvokeRequest,
  client: ApiClient = apiClient,
): Promise<ProposerResponse> {
  return client.post<ProposerResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/repair-attempts/${encodeURIComponent(repairAttemptId)}/proposer`,
    request,
  );
}

/**
 * GET the current Reviewer result for a repair attempt.
 * Returns the review decision, critique, revision timeline, and provenance.
 */
export function getReviewer(
  runId: string,
  repairAttemptId: string,
  client: ApiClient = apiClient,
): Promise<ReviewerResponse> {
  return client.get<ReviewerResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/repair-attempts/${encodeURIComponent(repairAttemptId)}/reviewer`,
  );
}

/**
 * POST to invoke the Reviewer LLM for a repair attempt.
 * Idempotent; returns the existing review if already computed.
 */
export function invokeReviewer(
  runId: string,
  repairAttemptId: string,
  request: ReviewerInvokeRequest,
  client: ApiClient = apiClient,
): Promise<ReviewerResponse> {
  return client.post<ReviewerResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/repair-attempts/${encodeURIComponent(repairAttemptId)}/reviewer`,
    request,
  );
}

/**
 * GET a repair proposal (including G10 gate status).
 */
export function getRepairProposal(
  runId: string,
  proposalId: string,
  client: ApiClient = apiClient,
): Promise<RepairProposalResponse> {
  return client.get<RepairProposalResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/repair-proposals/${encodeURIComponent(proposalId)}`,
  );
}

/**
 * POST a G10 human decision on a repair proposal.
 * Submits identifiers/checksums only — never resends or edits the authoritative diff.
 */
export function decideG10(
  runId: string,
  request: G10DecisionRequest,
  client: ApiClient = apiClient,
): Promise<G10DecisionResponse> {
  return client.post<G10DecisionResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}/approvals/G10/decisions`,
    request,
  );
}
