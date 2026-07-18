import { apiClient, type createApiClient } from "./client";
import type { ParityBaselineRequest, ParityBaselineResponse } from "@/types/parityBaseline";
type Client = ReturnType<typeof createApiClient>;
const path = (runId: string) => `/api/v1/runs/${encodeURIComponent(runId)}/discovery/parity-baseline`;
export const captureParityBaseline = (runId: string, request: ParityBaselineRequest, client: Client = apiClient) => client.post<ParityBaselineResponse>(path(runId), request);
export const getParityBaseline = (runId: string, client: Client = apiClient) => client.get<ParityBaselineResponse>(path(runId));
