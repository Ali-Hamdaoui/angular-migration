import { apiClient, type createApiClient } from "./client";
import type {
  ReportRequest,
  ReportResponse,
  G15DecisionRequest,
} from "@/types/assurance";

type Client = ReturnType<typeof createApiClient>;
const runPath = (runId: string) => encodeURIComponent(runId);

export function getReport(
  runId: string,
  client: Client = apiClient,
): Promise<ReportResponse> {
  return client.get<ReportResponse>(
    `/api/v1/runs/${runPath(runId)}/reports`,
  );
}

export function generateReport(
  runId: string,
  request: ReportRequest,
  client: Client = apiClient,
): Promise<ReportResponse> {
  return client.post<ReportResponse>(
    `/api/v1/runs/${runPath(runId)}/reports`,
    request,
  );
}

export function decideG15(
  runId: string,
  request: G15DecisionRequest,
  client: Client = apiClient,
): Promise<ReportResponse> {
  return client.post<ReportResponse>(
    `/api/v1/runs/${runPath(runId)}/approvals/G15/decisions`,
    request,
  );
}
