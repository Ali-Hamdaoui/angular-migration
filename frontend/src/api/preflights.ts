import { apiClient, type createApiClient } from "./client";
import type { G01Decision, G01DecisionResponse, ProductionPreflight } from "@/types/preflight";

type ApiClient = ReturnType<typeof createApiClient>;

export function getProductionPreflight(preflightId: string, client: ApiClient = apiClient): Promise<ProductionPreflight> {
  return client.get<ProductionPreflight>(`/api/v1/preflights/${encodeURIComponent(preflightId)}`);
}

export function decideG01(
  preflightId: string,
  request: { gate_id: string; decision: G01Decision; expected_state_version: number; input_checksum: string; artifact_set_checksum: string; idempotency_key: string; actor: string; comment?: string | null },
  client: ApiClient = apiClient,
): Promise<G01DecisionResponse> {
  return client.post<G01DecisionResponse>(`/api/v1/preflights/${encodeURIComponent(preflightId)}/g01/decisions`, request);
}
