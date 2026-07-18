import { apiClient, type createApiClient } from "./client";
import type { DiscoveryEvidence } from "@/types/discovery";

type Client = ReturnType<typeof createApiClient>;
export type DiscoveryCaptureRequest = { expected_state_version: number; idempotency_key: string; actor: string; prerequisite_artifact_ids: string[]; prerequisite_artifact_checksums: Record<string, string> };
export function getDiscovery(runId: string, client: Client = apiClient) { return client.get<DiscoveryEvidence>(`/api/v1/runs/${encodeURIComponent(runId)}/discovery`); }
export function captureDiscovery(runId: string, request: DiscoveryCaptureRequest, client: Client = apiClient) { return client.post<DiscoveryEvidence>(`/api/v1/runs/${encodeURIComponent(runId)}/discovery`, request); }
