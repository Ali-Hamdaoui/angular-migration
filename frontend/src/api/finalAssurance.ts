import { apiClient, type createApiClient } from "./client";
import type {
  FinalAssuranceRequest,
  FinalAssuranceResponse,
  G13DecisionRequest,
} from "@/types/assurance";

type Client = ReturnType<typeof createApiClient>;
const runPath = (runId: string) => encodeURIComponent(runId);

export function getFinalAssurance(
  runId: string,
  client: Client = apiClient,
): Promise<FinalAssuranceResponse> {
  return client.get<FinalAssuranceResponse>(
    `/api/v1/runs/${runPath(runId)}/approvals/G13`,
  );
}

export function runFinalAssurance(
  runId: string,
  request: FinalAssuranceRequest,
  client: Client = apiClient,
): Promise<FinalAssuranceResponse> {
  return client.post<FinalAssuranceResponse>(
    `/api/v1/runs/${runPath(runId)}/final-assurance`,
    request,
  );
}

export function decideG13(
  runId: string,
  request: G13DecisionRequest,
  client: Client = apiClient,
): Promise<FinalAssuranceResponse> {
  return client.post<FinalAssuranceResponse>(
    `/api/v1/runs/${runPath(runId)}/approvals/G13/decisions`,
    request,
  );
}
