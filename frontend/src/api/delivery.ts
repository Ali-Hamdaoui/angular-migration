import { apiClient, type createApiClient } from "./client";
import type {
  DeliveryRequest,
  DeliveryResponse,
  G14DecisionRequest,
} from "@/types/assurance";

type Client = ReturnType<typeof createApiClient>;
const runPath = (runId: string) => encodeURIComponent(runId);

export function getDeliveryCandidate(
  runId: string,
  client: Client = apiClient,
): Promise<DeliveryResponse> {
  return client.get<DeliveryResponse>(
    `/api/v1/runs/${runPath(runId)}/delivery-candidate`,
  );
}

export function createDeliveryCandidate(
  runId: string,
  request: DeliveryRequest,
  client: Client = apiClient,
): Promise<DeliveryResponse> {
  return client.post<DeliveryResponse>(
    `/api/v1/runs/${runPath(runId)}/delivery-candidate`,
    request,
  );
}

export function decideG14(
  runId: string,
  request: G14DecisionRequest,
  client: Client = apiClient,
): Promise<DeliveryResponse> {
  return client.post<DeliveryResponse>(
    `/api/v1/runs/${runPath(runId)}/approvals/G14/decisions`,
    request,
  );
}
